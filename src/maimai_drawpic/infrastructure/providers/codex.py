"""本机 Codex CLI 智能体适配器：启动受限会话、解析 JSONL 事件并按会话 ID 收取生成图片。"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence
from uuid import uuid4
import asyncio
import glob
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time

from ...domain.errors import (
    ProviderBusyError,
    ProviderConnectionError,
    ProviderError,
    ProviderOutcomeUnknown,
    ProviderRequestError,
    ProviderSubmittedError,
)
from ...domain.models.codex_profiles import (
    CODEX_PROVIDER,
    OUTPUT_SCHEMA,
    CodexReferenceServer,
    build_agent_prompt,
    build_exec_args,
    parse_final_message,
)
from ..concurrency import wait_owned
from ..http import HttpProxySettings, sanitize_provider_text
from ..media.images import detect_image_format, validate_image_bytes

REFERENCE_SERVER_SCRIPT = Path(__file__).with_name("codex_references.py")
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
_AUTH_MARKERS = ("not logged in", "login", "unauthorized", "401", "authentication", "sign in")
_WINDOWS = os.name == "nt"
_CREATE_NO_WINDOW = 0x08000000
_QUEUES: Dict[str, "_CodexQueue"] = {}
_QUEUES_LOCK = threading.Lock()


def discover_codex_executable(configured: str = "") -> Optional[Path]:
    """返回可直接启动的 Codex 可执行文件；Windows 只接受 .exe，避免经 cmd 转义参数。"""

    if configured.strip():
        path = Path(os.path.expandvars(os.path.expanduser(configured.strip())))
        return path if path.is_file() else None
    candidates: List[Path] = []
    found = shutil.which("codex")
    if found and (not _WINDOWS or found.lower().endswith(".exe")):
        candidates.append(Path(found))
    if _WINDOWS:
        local = os.environ.get("LOCALAPPDATA", "")
        roaming = os.environ.get("APPDATA", "")
        patterns = []
        if local:
            patterns.append(os.path.join(local, "OpenAI", "Codex", "bin", "*", "codex.exe"))
        if roaming:
            patterns.append(
                os.path.join(roaming, "npm", "node_modules", "@openai", "codex", "vendor", "*", "codex", "codex.exe")
            )
        desktop = sorted(
            (Path(item) for pattern in patterns for item in glob.glob(pattern)),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        candidates.extend(desktop)
    return next((item for item in candidates if item.is_file()), None)


def resolve_codex_home(configured: str = "") -> Path:
    value = configured.strip() or os.environ.get("CODEX_HOME", "").strip()
    return Path(os.path.expandvars(os.path.expanduser(value))) if value else Path.home() / ".codex"


@dataclass(frozen=True, slots=True)
class CodexAgentSettings:
    codex_path: str = ""
    codex_home: str = ""
    reasoning_effort: str = "medium"
    task_timeout_seconds: int = 900
    max_concurrent_tasks: int = 1
    max_queued_tasks: int = 3
    queue_timeout_seconds: int = 1200
    max_reference_downloads: int = 8
    allow_proxy_fake_ip: bool = True
    resume_enabled: bool = True
    thread_retention_days: int = 7
    deliver_all_images: bool = False
    agent_instructions: str = ""


@dataclass(slots=True)
class CodexRunRequest:
    prompt: str
    model: str
    work_dir: Path
    source_images: List[bytes] = field(default_factory=list)
    resume_thread_id: str = ""


@dataclass(slots=True)
class CodexRunResult:
    images: List[bytes]
    thread_id: str
    status: str = ""
    summary: str = ""
    sources: List[str] = field(default_factory=list)
    timed_out: bool = False


@dataclass(slots=True)
class _ProcessOutcome:
    thread_id: str = ""
    returncode: Optional[int] = None
    timed_out: bool = False
    cancelled: bool = False
    turn_completed: bool = False
    failure: str = ""
    stderr_tail: str = ""
    spawn_error: str = ""


class _Cancelled(Exception):
    pass


@dataclass(eq=False, slots=True)
class _Ticket:
    started: bool = False


@dataclass(frozen=True, slots=True)
class CodexQueueStatus:
    """提交时的队列快照；busy 表示运行与排队名额都已用尽。"""

    running: int
    waiting: int
    max_running: int
    max_waiting: int

    @property
    def busy(self) -> bool:
        return self.running >= self.max_running and self.waiting >= self.max_waiting

    @property
    def ahead(self) -> int:
        """新任务前面的任务数；有空闲运行名额且无人排队时为 0。"""
        if self.running < self.max_running and not self.waiting:
            return 0
        return self.running + self.waiting


class _CodexQueue:
    """同一 CODEX_HOME 的先进先出队列；运行与排队名额由调用时的配置决定。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.running = 0
        self.waiting: List[_Ticket] = []

    def status(self, max_running: int, max_waiting: int) -> CodexQueueStatus:
        with self._lock:
            return CodexQueueStatus(self.running, len(self.waiting), max_running, max_waiting)

    def join(self, max_running: int, max_waiting: int) -> _Ticket:
        ticket = _Ticket()
        with self._lock:
            if self.running < max_running and not self.waiting:
                self.running += 1
                ticket.started = True
                return ticket
            if len(self.waiting) >= max_waiting:
                raise ProviderBusyError(
                    f"Codex 智能体正忙：{self.running} 个任务运行中、{len(self.waiting)} 个排队，已达上限，请求尚未发出，请稍后再试"
                )
            self.waiting.append(ticket)
            return ticket

    def try_start(self, ticket: _Ticket, max_running: int) -> bool:
        with self._lock:
            if ticket.started:
                return True
            if self.waiting and self.waiting[0] is ticket and self.running < max_running:
                self.waiting.pop(0)
                self.running += 1
                ticket.started = True
                return True
            return False

    def ahead(self, ticket: _Ticket) -> int:
        with self._lock:
            if ticket.started or ticket not in self.waiting:
                return 0
            return self.running + self.waiting.index(ticket)

    def leave(self, ticket: _Ticket) -> None:
        with self._lock:
            if ticket.started:
                self.running = max(0, self.running - 1)
                ticket.started = False
            elif ticket in self.waiting:
                self.waiting.remove(ticket)


def _queue_for(home: Path) -> _CodexQueue:
    key = str(home.resolve()).casefold() if _WINDOWS else str(home.resolve())
    with _QUEUES_LOCK:
        if key not in _QUEUES:
            _QUEUES[key] = _CodexQueue()
        return _QUEUES[key]


def _kill_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        if _WINDOWS:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_CREATE_NO_WINDOW,
                timeout=15,
                check=False,
            )
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        process.kill()
    except OSError:
        pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


class CodexAgentImage:
    """调用本机 Codex 完成检索、参考与生图；同一 CODEX_HOME 的并发受限。"""

    def __init__(
        self,
        settings: CodexAgentSettings,
        *,
        work_root: Path,
        proxy_settings: Optional[HttpProxySettings] = None,
        logger: Any = None,
        python_executable: str = "",
        runner: Optional[Callable[..., _ProcessOutcome]] = None,
    ) -> None:
        self.settings = settings
        self.work_root = work_root
        self.proxy_settings = proxy_settings or HttpProxySettings.disabled()
        self.logger = logger
        self.python_executable = python_executable or sys.executable
        # 测试可注入进程执行函数；生产使用真实子进程。
        self._runner = runner or self._run_process

    @property
    def agent_settings(self) -> CodexAgentSettings:
        return self.settings

    # ---- 通用适配器接口（无会话接续） -------------------------------------------------
    async def generate_images(self, prompt: str, model: str, n: int = 1) -> List[bytes]:
        del n
        return (await self.run_agent(CodexRunRequest(prompt, model, self.new_work_dir()))).images

    async def edit_images(self, prompt: str, model: str, image_bytes_list: List[bytes], n: int = 1) -> List[bytes]:
        del n
        request = CodexRunRequest(prompt, model, self.new_work_dir(), list(image_bytes_list))
        return (await self.run_agent(request)).images

    def new_work_dir(self) -> Path:
        return self.work_root / "threads" / uuid4().hex

    # ---- 排队 ---------------------------------------------------------------------
    def queue_status(self) -> CodexQueueStatus:
        """当前 CODEX_HOME 的队列快照，供提交前判断是否已满及排队位置。"""
        settings = self.settings
        home = resolve_codex_home(settings.codex_home)
        return _queue_for(home).status(settings.max_concurrent_tasks, settings.max_queued_tasks)

    async def _wait_turn(
        self, queue: _CodexQueue, ticket: _Ticket, on_queue: Optional[Callable[[int], Awaitable[None]]]
    ) -> None:
        """异步等待运行名额；排队时间单独计时，不占用任务运行时间。"""
        settings = self.settings
        deadline = time.monotonic() + settings.queue_timeout_seconds
        reported: Optional[int] = None
        while not queue.try_start(ticket, settings.max_concurrent_tasks):
            ahead = queue.ahead(ticket)
            if ahead != reported:
                reported = ahead
                await self._report_queue(on_queue, ahead)
            if time.monotonic() >= deadline:
                raise ProviderBusyError(
                    f"Codex 智能体排队超过 {settings.queue_timeout_seconds} 秒仍未轮到，请求尚未发出"
                )
            await asyncio.sleep(0.5)
        await self._report_queue(on_queue, 0)

    async def _report_queue(self, on_queue: Optional[Callable[[int], Awaitable[None]]], ahead: int) -> None:
        if on_queue is None:
            return
        try:
            await on_queue(ahead)
        except Exception as exc:  # 状态通知失败不影响排队与执行。
            self._log("warning", "Codex 排队状态更新失败: error_type=%s", type(exc).__name__)

    # ---- 智能体执行 ----------------------------------------------------------------
    async def run_agent(
        self, request: CodexRunRequest, on_queue: Optional[Callable[[int], Awaitable[None]]] = None
    ) -> CodexRunResult:
        """排队取得运行名额后执行；on_queue(ahead) 报告前面任务数，0 表示开始运行。"""
        executable, home = self._preflight()
        settings = self.settings
        queue = _queue_for(home)
        ticket = queue.join(settings.max_concurrent_tasks, settings.max_queued_tasks)
        try:
            await self._wait_turn(queue, ticket, on_queue)
            cancel = threading.Event()
            pending = asyncio.create_task(asyncio.to_thread(self._run_blocking, request, cancel, executable, home))
            try:
                return await asyncio.shield(pending)
            except asyncio.CancelledError:
                # 取消必须终止 Codex 进程树并等工作线程退出，不能留下继续消耗额度的会话。
                cancel.set()
                try:
                    await wait_owned(pending)
                except BaseException:
                    pass
                raise
        finally:
            # 工作线程结束后才释放名额，排队中取消则直接出队。
            queue.leave(ticket)

    def _preflight(self) -> tuple:
        settings = self.settings
        executable = discover_codex_executable(settings.codex_path)
        if executable is None:
            raise ProviderConnectionError(
                "未找到 Codex CLI 可执行文件；请安装 Codex 或在平台配置中填写 codex.exe 路径，请求尚未发出"
            )
        home = resolve_codex_home(settings.codex_home)
        if not home.is_dir():
            raise ProviderConnectionError(f"CODEX_HOME 目录不存在，请先在本机登录 Codex：{home.name}，请求尚未发出")
        return executable, home

    def _log(self, level: str, message: str, *args: Any) -> None:
        if self.logger is not None:
            getattr(self.logger, level)(message, *args)

    def _run_blocking(
        self, request: CodexRunRequest, cancel: threading.Event, executable: Path, home: Path
    ) -> CodexRunResult:
        # 任务计时从取得运行名额后开始，排队时间不占用运行时间。
        started = time.monotonic()
        deadline = started + self.settings.task_timeout_seconds
        control = self.work_root / "control" / uuid4().hex
        try:
            return self._run_locked(request, cancel, executable, home, control, deadline, started)
        finally:
            shutil.rmtree(control, ignore_errors=True)

    def _prepare_inputs(self, request: CodexRunRequest) -> List[str]:
        inputs = request.work_dir / "inputs"
        inputs.mkdir(parents=True, exist_ok=True)
        turn = uuid4().hex[:8]
        paths = []
        for index, raw in enumerate(request.source_images, 1):
            validate_image_bytes(raw)
            suffix = detect_image_format(raw)
            path = inputs / f"source-{turn}-{index}.{'jpg' if suffix == 'jpeg' else suffix}"
            path.write_bytes(raw)
            paths.append(str(path.resolve()))
        return paths

    def _reference_server(self, request: CodexRunRequest, control: Path) -> Optional[CodexReferenceServer]:
        if self.settings.max_reference_downloads <= 0:
            return None
        proxy = self.proxy_settings
        config = {
            "output_dir": str((request.work_dir / "references").resolve()),
            "max_downloads": self.settings.max_reference_downloads,
            "allow_fake_ip": self.settings.allow_proxy_fake_ip,
            "timeout_seconds": 45,
            "proxy": {
                "enabled": proxy.enabled,
                "use_system_proxy": proxy.use_system_proxy,
                "scheme": proxy.scheme,
                "host": proxy.host,
                "port": proxy.port,
                "username": proxy.username,
                "password": proxy.password,
            },
        }
        # 代理凭据写在会话工作目录之外的私有控制目录，任务结束即删除，不经命令行传递。
        path = control / "references.json"
        path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        return CodexReferenceServer(self.python_executable, str(REFERENCE_SERVER_SCRIPT), str(path))

    def _run_locked(
        self,
        request: CodexRunRequest,
        cancel: threading.Event,
        executable: Path,
        home: Path,
        control: Path,
        deadline: float,
        started: float,
    ) -> CodexRunResult:
        settings = self.settings
        control.mkdir(parents=True, exist_ok=True)
        request.work_dir.mkdir(parents=True, exist_ok=True)
        (request.work_dir / "references").mkdir(exist_ok=True)
        image_paths = self._prepare_inputs(request)
        schema_path = control / "output-schema.json"
        schema_path.write_text(json.dumps(OUTPUT_SCHEMA), encoding="utf-8")
        last_message = control / "last-message.json"
        reference_server = self._reference_server(request, control)
        args = build_exec_args(
            str(executable),
            model=request.model,
            reasoning_effort=settings.reasoning_effort,
            output_schema_path=str(schema_path),
            last_message_path=str(last_message),
            image_paths=image_paths,
            resume_thread_id=request.resume_thread_id,
            reference_server=reference_server,
        )
        prompt = build_agent_prompt(
            instructions=settings.agent_instructions,
            user_prompt=request.prompt,
            source_image_paths=image_paths,
            references_dir=str((request.work_dir / "references").resolve()),
            reference_downloads_enabled=reference_server is not None,
            resume=bool(request.resume_thread_id),
        )
        before = self._existing_images(home, request.resume_thread_id) if request.resume_thread_id else set()
        env = dict(os.environ)
        if settings.codex_home.strip():
            env["CODEX_HOME"] = str(home)
        self._log(
            "info",
            "Codex 智能体任务开始: model=%s resume=%s source_image_count=%s reference_downloads=%s timeout=%ss",
            request.model,
            bool(request.resume_thread_id),
            len(image_paths),
            settings.max_reference_downloads if reference_server is not None else 0,
            settings.task_timeout_seconds,
        )
        outcome = self._runner(
            args,
            cwd=request.work_dir,
            stdin=prompt.encode("utf-8"),
            env=env,
            deadline=deadline,
            cancel=cancel,
            stderr_path=control / "stderr.log",
        )
        if outcome.cancelled:
            raise _Cancelled()
        thread_id = outcome.thread_id or request.resume_thread_id
        if outcome.spawn_error:
            raise ProviderConnectionError(f"Codex 进程无法启动（{outcome.spawn_error}），请求尚未发出")
        final = parse_final_message(_read_text(last_message))
        if not thread_id:
            return self._raise_unstarted(outcome)
        images = self._collect_images(home, thread_id, before, final["final_images"])
        elapsed = int(time.monotonic() - started)
        if final["status"] == "refused":
            raise ProviderRequestError(
                400, "content_policy_refused", "Codex 拒绝了该绘图请求：" + _short(final["summary"] or outcome.failure)
            )
        if images:
            if outcome.timed_out:
                self._log("warning", "Codex 任务超时但已生成图片，交付已有结果: thread_id=%s elapsed=%ss", thread_id, elapsed)
            self._log(
                "info",
                "Codex 智能体任务完成: thread_id=%s model=%s image_count=%s sources=%s elapsed=%ss",
                thread_id,
                request.model,
                len(images),
                len(final["sources"]),
                elapsed,
            )
            return CodexRunResult(
                images=images,
                thread_id=thread_id,
                status=final["status"] or "completed",
                summary=final["summary"],
                sources=final["sources"],
                timed_out=outcome.timed_out,
            )
        if outcome.timed_out:
            raise ProviderSubmittedError(
                CODEX_PROVIDER,
                thread_id,
                f"等待超过 {settings.task_timeout_seconds} 秒仍未生成图片，已终止 Codex 进程",
                outcome_unknown=True,
            )
        reason = final["summary"] or outcome.failure or outcome.stderr_tail or "智能体结束但没有生成图片"
        raise ProviderSubmittedError(CODEX_PROVIDER, thread_id, "未取得生成图片：" + _short(reason))

    def _raise_unstarted(self, outcome: _ProcessOutcome) -> CodexRunResult:
        detail = _short(outcome.failure or outcome.stderr_tail or f"退出码 {outcome.returncode}")
        if outcome.timed_out:
            raise ProviderOutcomeUnknown("Codex 启动后等待超时且未取得会话 ID，远端受理状态不确定，未自动重试")
        lowered = detail.casefold()
        if any(marker in lowered for marker in _AUTH_MARKERS):
            raise ProviderRequestError(401, "codex_auth", f"Codex 未登录或登录已失效：{detail}")
        raise ProviderRequestError(400, "codex_startup_failed", f"Codex 未能开始会话：{detail}")

    @staticmethod
    def _thread_dir(home: Path, thread_id: str) -> Path:
        return home / "generated_images" / thread_id

    def _existing_images(self, home: Path, thread_id: str) -> set:
        directory = self._thread_dir(home, thread_id)
        if not directory.is_dir():
            return set()
        return {path.name for path in directory.iterdir() if path.suffix.lower() in _IMAGE_SUFFIXES}

    def _collect_images(self, home: Path, thread_id: str, before: set, selected: Sequence[str]) -> List[bytes]:
        if not thread_id or any(char in thread_id for char in "/\\:") or thread_id in {".", ".."}:
            return []
        directory = self._thread_dir(home, thread_id)
        if not directory.is_dir():
            return []
        produced = sorted(
            (
                path
                for path in directory.iterdir()
                if path.is_file() and path.suffix.lower() in _IMAGE_SUFFIXES and path.name not in before
            ),
            key=lambda path: path.stat().st_mtime,
        )
        if not produced:
            return []
        chosen = produced
        if not self.settings.deliver_all_images:
            resolved = {path.resolve(): path for path in produced}
            picked = []
            for item in selected:
                try:
                    candidate = Path(item).resolve()
                except (OSError, ValueError):
                    continue
                if candidate in resolved and resolved[candidate] not in picked:
                    picked.append(resolved[candidate])
            chosen = picked or [produced[-1]]
        images = []
        for path in chosen:
            raw = path.read_bytes()
            validate_image_bytes(raw)
            images.append(raw)
        return images

    # ---- 进程管理 ------------------------------------------------------------------
    def _run_process(
        self,
        args: List[str],
        *,
        cwd: Path,
        stdin: bytes,
        env: Dict[str, str],
        deadline: float,
        cancel: threading.Event,
        stderr_path: Path,
    ) -> _ProcessOutcome:
        outcome = _ProcessOutcome()
        kwargs: Dict[str, Any] = {}
        if _WINDOWS:
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | _CREATE_NO_WINDOW
        else:
            kwargs["start_new_session"] = True
        with stderr_path.open("wb") as stderr:
            try:
                process = subprocess.Popen(
                    args,
                    cwd=str(cwd),
                    env=env,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=stderr,
                    **kwargs,
                )
            except OSError as exc:
                outcome.spawn_error = type(exc).__name__
                return outcome
            reader = threading.Thread(target=self._read_events, args=(process, outcome), daemon=True)
            reader.start()
            try:
                assert process.stdin is not None
                process.stdin.write(stdin)
                process.stdin.close()
            except OSError:
                pass
            while process.poll() is None:
                if cancel.is_set():
                    outcome.cancelled = True
                    _kill_tree(process)
                    break
                if time.monotonic() >= deadline:
                    outcome.timed_out = True
                    _kill_tree(process)
                    break
                time.sleep(0.5)
            reader.join(timeout=10)
            outcome.returncode = process.poll()
        outcome.stderr_tail = sanitize_provider_text(_tail(stderr_path), max_chars=400)
        return outcome

    @staticmethod
    def _read_events(process: subprocess.Popen, outcome: _ProcessOutcome) -> None:
        assert process.stdout is not None
        for raw in process.stdout:
            try:
                event = json.loads(raw.decode("utf-8", errors="replace"))
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            kind = event.get("type")
            if kind == "thread.started" and isinstance(event.get("thread_id"), str):
                outcome.thread_id = event["thread_id"]
            elif kind == "turn.completed":
                outcome.turn_completed = True
            elif kind in {"turn.failed", "error"}:
                error = event.get("error") if isinstance(event.get("error"), dict) else event
                message = error.get("message") if isinstance(error, dict) else ""
                if isinstance(message, str) and message:
                    outcome.failure = sanitize_provider_text(message, max_chars=400)


def with_model(request: CodexRunRequest, model: str) -> CodexRunRequest:
    return replace(request, model=model)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return ""


def _tail(path: Path, limit: int = 4000) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _short(text: str) -> str:
    return sanitize_provider_text(text or "", max_chars=300)


__all__ = [
    "CodexAgentImage",
    "CodexAgentSettings",
    "CodexQueueStatus",
    "CodexRunRequest",
    "CodexRunResult",
    "ProviderError",
    "discover_codex_executable",
    "resolve_codex_home",
    "with_model",
]
