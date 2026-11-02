"""Codex 智能体平台：参数构造、受控参考图下载、进程结果映射、会话接续与权限，不调用真实 Codex。"""

from importlib import import_module
from io import BytesIO
from pathlib import Path
from types import ModuleType, SimpleNamespace
import asyncio
import json
import logging
import sys
import threading
import time

from PIL import Image
import pytest

_PACKAGE = "drawpic_codex_test"
package = ModuleType(_PACKAGE)
package.__path__ = [str(Path(__file__).resolve().parents[1])]
sys.modules[_PACKAGE] = package
profiles = import_module(f"{_PACKAGE}.src.maimai_drawpic.domain.models.codex_profiles")
codex = import_module(f"{_PACKAGE}.src.maimai_drawpic.infrastructure.providers.codex")
references = import_module(f"{_PACKAGE}.src.maimai_drawpic.infrastructure.providers.codex_references")
threads = import_module(f"{_PACKAGE}.src.maimai_drawpic.infrastructure.storage.agent_threads")
downloads = import_module(f"{_PACKAGE}.src.maimai_drawpic.infrastructure.media.downloads")
errors = import_module(f"{_PACKAGE}.src.maimai_drawpic.domain.errors")
models = import_module(f"{_PACKAGE}.src.maimai_drawpic.domain.configuration.models")
platforms = import_module(f"{_PACKAGE}.src.maimai_drawpic.infrastructure.storage.platforms")
instances = import_module(f"{_PACKAGE}.src.maimai_drawpic.application.routing.instances")
drawing = import_module(f"{_PACKAGE}.src.maimai_drawpic.application.drawing")


def png(color: str, size=(64, 48)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, "PNG")
    return buffer.getvalue()


def gradient(size=(96, 64)) -> bytes:
    image = Image.new("RGB", size)
    image.putdata([(x * 2 % 256, y * 3 % 256, (x + y) % 256) for y in range(size[1]) for x in range(size[0])])
    buffer = BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def test_exec_args_lock_down_tools_and_keep_prompt_off_command_line():
    server = profiles.CodexReferenceServer("C:/py/python.exe", "C:/plugin/refs.py", "C:/control/refs.json")
    args = profiles.build_exec_args(
        "codex.exe",
        model="gpt-x",
        reasoning_effort="medium",
        output_schema_path="schema.json",
        last_message_path="last.json",
        image_paths=["C:/work/a.png"],
        reference_server=server,
    )
    assert args[:2] == ["codex.exe", "exec"] and args[-1] == "-"
    assert 'sandbox_mode="read-only"' in args and 'web_search="live"' in args
    disabled = {args[index + 1] for index, value in enumerate(args) if value == "--disable"}
    assert {"shell_tool", "unified_exec", "computer_use", "browser_use", "hooks"} <= disabled
    assert "--ignore-user-config" in args and "--image=C:/work/a.png" in args
    assert 'mcp_servers.drawpic_refs.default_tools_approval_mode="approve"' in args
    assert any(value.startswith("mcp_servers.drawpic_refs.args=") and "refs.json" in value for value in args)
    assert 'model_reasoning_effort="medium"' in args
    resumed = profiles.build_exec_args(
        "codex.exe", model="gpt-x", reasoning_effort="default", output_schema_path="s", last_message_path="l",
        resume_thread_id="thread-1234",
    )
    assert resumed[:4] == ["codex.exe", "exec", "resume", "thread-1234"]
    assert not any(value.startswith("model_reasoning_effort") for value in resumed)
    assert not any(value.startswith("mcp_servers") for value in resumed)


def test_agent_prompt_and_final_message_parsing():
    prompt = profiles.build_agent_prompt(
        instructions="", user_prompt="画祀", source_image_paths=["C:/a.png"], references_dir="C:/refs", resume=True
    )
    assert "画祀" in prompt and "fetch_reference_image" in prompt and "二次调整" in prompt and "C:/a.png" in prompt
    assert profiles.DEFAULT_AGENT_INSTRUCTIONS.splitlines()[0] in prompt
    no_download = profiles.build_agent_prompt(instructions="x", user_prompt="y", reference_downloads_enabled=False)
    assert "fetch_reference_image" not in no_download
    parsed = profiles.parse_final_message(
        json.dumps({"status": "completed", "summary": "ok", "final_images": ["a", 3], "sources": ["u"]})
    )
    assert parsed == {"status": "completed", "summary": "ok", "final_images": ["a"], "sources": ["u"]}
    assert profiles.parse_final_message("not json")["status"] == ""


def test_reference_server_protocol_and_private_address_refusal(tmp_path):
    downloader = references.ReferenceDownloader({"output_dir": str(tmp_path / "refs"), "max_downloads": 1})

    async def run():
        init = await references.handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            downloader,
        )
        assert init["result"]["protocolVersion"] == "2025-06-18"
        assert await references.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}, downloader) is None
        listed = await references.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, downloader)
        assert listed["result"]["tools"][0]["name"] == "fetch_reference_image"
        refused = await references.handle_message(
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "fetch_reference_image", "arguments": {"url": "http://127.0.0.1/a.png"}}},
            downloader,
        )
        assert refused["result"]["isError"] is True and "非公网" in refused["result"]["content"][0]["text"]
        unknown = await references.handle_message({"jsonrpc": "2.0", "id": 4, "method": "nope"}, downloader)
        assert unknown["error"]["code"] == -32601

    asyncio.run(run())
    assert not list((tmp_path / "refs").glob("ref-*"))


def test_fake_ip_range_only_allowed_when_requested():
    assert not downloads._allowed_address("198.18.0.5", ())
    assert downloads._allowed_address("198.18.0.5", (downloads.FAKE_IP_NETWORK,))
    assert not downloads._allowed_address("192.168.1.2", (downloads.FAKE_IP_NETWORK,))
    assert not downloads._allowed_address("127.0.0.1", (downloads.FAKE_IP_NETWORK,))


class FakeRunner:
    """模拟 Codex 进程：写入生成图片与结构化回复，记录收到的参数。"""

    def __init__(self, home: Path, *, thread_id="01a1-thread-test", images=(), final=None, timed_out=False,
                 failure="", stderr=""):
        self.home, self.thread_id, self.images = home, thread_id, list(images)
        self.final, self.timed_out, self.failure, self.stderr = final, timed_out, failure, stderr
        self.calls = []

    def __call__(self, args, *, cwd, stdin, env, deadline, cancel, stderr_path):
        self.calls.append({"args": args, "cwd": cwd, "stdin": stdin.decode("utf-8")})
        outcome = codex._ProcessOutcome(thread_id=self.thread_id, timed_out=self.timed_out,
                                        failure=self.failure, stderr_tail=self.stderr)
        if self.thread_id:
            target = self.home / "generated_images" / self.thread_id
            target.mkdir(parents=True, exist_ok=True)
            paths = []
            for index, raw in enumerate(self.images):
                path = target / f"exec-{len(self.calls)}-{index}.png"
                path.write_bytes(raw)
                time.sleep(0.01)
                paths.append(str(path))
            final = self.final if self.final is not None else {
                "status": "completed", "summary": "done", "final_images": paths[-1:], "sources": ["https://x"]
            }
            last = Path(args[args.index("-o") + 1])
            last.write_text(json.dumps(final), encoding="utf-8")
        return outcome


def make_provider(tmp_path, runner, **settings):
    exe = tmp_path / "codex.exe"
    exe.write_bytes(b"")
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    values = {"codex_path": str(exe), "codex_home": str(home), "task_timeout_seconds": 120}
    values.update(settings)
    return codex.CodexAgentImage(
        codex.CodexAgentSettings(**values), work_root=tmp_path / "agent", runner=runner,
        python_executable=sys.executable,
    )


def test_run_agent_collects_selected_image_and_cleans_private_control(tmp_path):
    first, final = png("red"), png("blue")
    runner = FakeRunner(tmp_path / "home", images=[first, final])
    provider = make_provider(tmp_path, runner)
    request = codex.CodexRunRequest("画猫", "gpt-x", tmp_path / "agent" / "threads" / ("a" * 32), [png("green")])
    result = asyncio.run(provider.run_agent(request))
    assert result.images == [final] and result.thread_id == "01a1-thread-test"
    call = runner.calls[0]
    assert "画猫" in call["stdin"] and "画猫" not in " ".join(call["args"])
    assert any(arg.startswith("--image=") for arg in call["args"])
    assert not (tmp_path / "agent" / "control").exists() or not any((tmp_path / "agent" / "control").iterdir())
    assert list((request.work_dir / "inputs").glob("source-*.png"))

    every = make_provider(tmp_path, FakeRunner(tmp_path / "home", thread_id="01a1-thread-all",
                                               images=[first, final]), deliver_all_images=True)
    request = codex.CodexRunRequest("画猫", "gpt-x", tmp_path / "agent" / "threads" / ("b" * 32))
    assert asyncio.run(every.run_agent(request)).images == [first, final]


def test_resume_only_returns_images_from_the_new_turn(tmp_path):
    runner = FakeRunner(tmp_path / "home", images=[png("red")])
    provider = make_provider(tmp_path, runner)
    work = tmp_path / "agent" / "threads" / ("c" * 32)
    asyncio.run(provider.run_agent(codex.CodexRunRequest("画", "gpt-x", work)))
    runner.images = [png("yellow")]
    runner.final = {"status": "completed", "summary": "", "final_images": [], "sources": []}
    result = asyncio.run(provider.run_agent(
        codex.CodexRunRequest("改成黄色", "gpt-x", work, [png("red")], resume_thread_id=runner.thread_id)
    ))
    assert result.images == [png("yellow")]
    assert runner.calls[1]["args"][2:4] == ["resume", runner.thread_id]


def test_error_semantics_follow_submission_boundary(tmp_path):
    work = tmp_path / "agent" / "threads" / ("d" * 32)

    def run(provider):
        return asyncio.run(provider.run_agent(codex.CodexRunRequest("画", "gpt-x", work)))

    missing = codex.CodexAgentImage(
        codex.CodexAgentSettings(codex_path=str(tmp_path / "missing.exe")), work_root=tmp_path / "agent"
    )
    with pytest.raises(errors.ProviderConnectionError):
        run(missing)

    unstarted = make_provider(tmp_path, FakeRunner(tmp_path / "home", thread_id="", failure="Not logged in"))
    with pytest.raises(errors.ProviderRequestError) as auth:
        run(unstarted)
    assert auth.value.status == 401 and not auth.value.retryable

    refused = make_provider(tmp_path, FakeRunner(tmp_path / "home", thread_id="01a1-refused", images=[],
                                                 final={"status": "refused", "summary": "违规", "final_images": [],
                                                        "sources": []}))
    with pytest.raises(errors.ProviderRequestError) as rejected:
        run(refused)
    assert rejected.value.rejected

    empty = make_provider(tmp_path, FakeRunner(tmp_path / "home", thread_id="01a1-empty", images=[]))
    with pytest.raises(errors.ProviderSubmittedError) as submitted:
        run(empty)
    assert not submitted.value.retryable and not submitted.value.allow_fallback

    slow = make_provider(tmp_path, FakeRunner(tmp_path / "home", thread_id="01a1-slow", images=[], timed_out=True))
    with pytest.raises(errors.ProviderSubmittedError) as unknown:
        run(slow)
    assert unknown.value.outcome_unknown

    partial = make_provider(tmp_path, FakeRunner(tmp_path / "home", thread_id="01a1-partial", images=[png("red")],
                                                 timed_out=True))
    assert run(partial).timed_out


def test_queue_is_fifo_bounded_and_releases_slots():
    queue = codex._CodexQueue()
    first = queue.join(1, 2)
    assert first.started and queue.status(1, 2).ahead == 1
    second, third = queue.join(1, 2), queue.join(1, 2)
    assert not second.started and queue.ahead(second) == 1 and queue.ahead(third) == 2
    assert queue.status(1, 2).busy
    with pytest.raises(errors.ProviderBusyError) as busy:
        queue.join(1, 2)
    assert not busy.value.retryable and busy.value.allow_fallback
    assert not queue.try_start(third, 1), "后来的任务不能插队"
    queue.leave(first)
    assert not queue.try_start(third, 1) and queue.try_start(second, 1)
    queue.leave(third)
    assert queue.status(1, 2).waiting == 0
    queue.leave(second)
    assert queue.status(1, 2).ahead == 0 and not queue.status(1, 0).busy


class BlockingRunner(FakeRunner):
    """第一次运行阻塞到 release 被设置，记录每次拿到的剩余运行时间。"""

    def __init__(self, home):
        super().__init__(home, thread_id="", images=[])
        self.release = threading.Event()
        self.budgets = []
        self.counter = 0

    def __call__(self, args, *, cwd, stdin, env, deadline, cancel, stderr_path):
        self.budgets.append(deadline - time.monotonic())
        self.counter += 1
        self.thread_id = f"01a1-thread-{self.counter}"
        self.images = [png("red")]
        if self.counter == 1:
            self.release.wait(10)
        return super().__call__(args, cwd=cwd, stdin=stdin, env=env, deadline=deadline, cancel=cancel,
                                stderr_path=stderr_path)


def test_queued_task_reports_position_and_gets_full_run_time(tmp_path):
    runner = BlockingRunner(tmp_path / "home")
    provider = make_provider(tmp_path, runner, max_concurrent_tasks=1, max_queued_tasks=1, task_timeout_seconds=300)
    reports = {"a": [], "b": []}

    def request(name):
        return codex.CodexRunRequest("画", "gpt-x", tmp_path / "agent" / "threads" / (name * 32))

    async def run():
        async def record(name, ahead):
            reports[name].append(ahead)

        first = asyncio.create_task(provider.run_agent(request("a"), lambda ahead: record("a", ahead)))
        await asyncio.sleep(0.2)
        second = asyncio.create_task(provider.run_agent(request("b"), lambda ahead: record("b", ahead)))
        await asyncio.sleep(0.2)
        assert provider.queue_status().busy
        with pytest.raises(errors.ProviderBusyError, match="正忙"):
            await provider.run_agent(request("c"))
        await asyncio.sleep(1.5)  # 排队时间不能占用第二个任务的运行时间
        runner.release.set()
        return await asyncio.gather(first, second)

    results = asyncio.run(run())
    assert all(result.images for result in results)
    assert reports["a"] == [0] and reports["b"] == [1, 0]
    assert min(runner.budgets) > 295
    assert provider.queue_status().running == 0 and provider.queue_status().waiting == 0


def test_queue_timeout_gives_up_without_sending(tmp_path):
    runner = BlockingRunner(tmp_path / "home")
    provider = make_provider(tmp_path, runner, max_concurrent_tasks=1, max_queued_tasks=2, queue_timeout_seconds=1)

    async def run():
        first = asyncio.create_task(provider.run_agent(
            codex.CodexRunRequest("画", "gpt-x", tmp_path / "agent" / "threads" / ("a" * 32))
        ))
        await asyncio.sleep(0.2)
        with pytest.raises(errors.ProviderBusyError, match="排队超过"):
            await provider.run_agent(codex.CodexRunRequest("画", "gpt-x", tmp_path / "agent" / "threads" / ("b" * 32)))
        runner.release.set()
        await first

    asyncio.run(run())
    assert runner.counter == 1, "排队超时的任务不能启动 Codex"
    assert provider.queue_status().waiting == 0


def test_router_rejects_full_queue_before_quota(tmp_path):
    exe = tmp_path / "codex.exe"
    exe.write_bytes(b"")
    home = tmp_path / "home"
    home.mkdir()
    router = codex_router(tmp_path, codex_path=str(exe), codex_home=str(home), max_queued_tasks=0)
    status = router.ensure_agent_capacity("codex/gpt-x")
    assert status is not None and status.ahead == 0
    queue = codex._queue_for(home)
    ticket = queue.join(1, 0)
    try:
        with pytest.raises(ValueError, match="正忙") as busy:
            router.ensure_agent_capacity("codex/gpt-x")
        assert busy.value.code == "CONCURRENCY_LIMIT" and busy.value.retry_submit
    finally:
        queue.leave(ticket)
    assert router.resolve_queue_timeout_seconds("codex/gpt-x") == 1200


def test_cancel_kills_the_codex_process(tmp_path):
    provider = codex.CodexAgentImage(codex.CodexAgentSettings(), work_root=tmp_path)
    cancel = threading.Event()
    timer = threading.Timer(0.5, cancel.set)
    timer.start()
    started = time.monotonic()
    outcome = provider._run_process(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        cwd=tmp_path, stdin=b"", env=None, deadline=time.monotonic() + 60, cancel=cancel,
        stderr_path=tmp_path / "stderr.log",
    )
    assert outcome.cancelled and time.monotonic() - started < 30


def test_thread_store_matches_recompressed_results_within_session(tmp_path):
    store = threads.CodexThreadStore(tmp_path / "agent")
    store.load()
    work = store.new_work_dir()
    work.mkdir(parents=True)
    original = gradient()
    store.record(thread_id="01a1-thread-1", instance="codex", session_key="qq:user:1", work_dir=work,
                 images=[original], retention_days=7)
    jpeg = BytesIO()
    Image.open(BytesIO(original)).convert("RGB").save(jpeg, "JPEG", quality=70)
    found = store.find(instance="codex", session_key="qq:user:1", images=[jpeg.getvalue()], retention_days=7)
    assert found is not None and found.thread_id == "01a1-thread-1" and found.work_dir == work
    assert store.find(instance="codex", session_key="qq:user:2", images=[original], retention_days=7) is None
    assert store.find(instance="other", session_key="qq:user:1", images=[original], retention_days=7) is None
    assert store.find(instance="codex", session_key="qq:user:1", images=[png("red")], retention_days=7) is None

    reloaded = threads.CodexThreadStore(tmp_path / "agent")
    reloaded.load()
    assert reloaded.find(instance="codex", session_key="qq:user:1", images=[original], retention_days=7)


def test_corrupt_thread_index_is_preserved_and_disables_resume(tmp_path):
    root = tmp_path / "agent"
    root.mkdir()
    (root / "threads.json").write_text("{broken", encoding="utf-8")
    store = threads.CodexThreadStore(root)
    store.load()
    assert not store.available
    work = store.new_work_dir()
    work.mkdir(parents=True)
    store.record(thread_id="01a1-thread-1", instance="codex", session_key="s", work_dir=work,
                 images=[png("red")], retention_days=7)
    assert (root / "threads.json").read_text(encoding="utf-8") == "{broken"


def codex_router(tmp_path, **codex_values):
    values = {kind: {"enabled": False} for kind in platforms.PLATFORM_NAMES}
    values["codex"] = {"enabled": True, "models": ["gpt-x"], **codex_values}
    config = models.DrawpicConfig.model_validate(values)
    record = {"id": "f" * 32, "name": "codex", "kind": "codex"}
    return instances.InstanceProviderRouter(config, [(record, config)], data_dir=tmp_path)


def test_routing_capabilities_timeout_and_access_scope(tmp_path):
    router = codex_router(tmp_path, task_timeout_seconds=1200)
    assert router.get_all_models() == ["codex/gpt-x"]
    assert router.get_model_provider("codex/gpt-x") == "codex"
    assert router.evaluate_model_task_capability("codex/gpt-x", "edit_image").allowed
    assert router.get_max_source_images("codex/gpt-x") == profiles.MAX_CODEX_SOURCE_IMAGES
    assert router.resolve_task_timeout_seconds("codex/gpt-x") == 1200
    assert router.model_requires_admin("codex/gpt-x")
    assert not router.should_rewrite_prompt_to_english("codex", "codex/gpt-x")
    provider, kind = router.require_platform_for_model("codex/gpt-x")
    assert kind == "codex" and provider.agent_settings.task_timeout_seconds == 1200
    assert not codex_router(tmp_path, access_scope="all").model_requires_admin("codex/gpt-x")


def test_restricted_model_rejected_before_task_creation(tmp_path):
    router = codex_router(tmp_path)

    class Tasks:
        def __getattr__(self, name):
            raise AssertionError("不应创建任务")

    service = drawing.DrawService(
        ctx=SimpleNamespace(logger=logging.getLogger("codex-test")), router=router,
        stream_service=None, moderation_service=None, task_store=Tasks(),
    )

    async def submit():
        return await service.start_background_image_request(
            prompt="画", stream_id="s", resolved_model="codex/gpt-x", resolved_openai_mode="", provider_name="codex",
        )

    with pytest.raises(PermissionError, match="仅限插件管理员"):
        asyncio.run(submit())


def test_platform_catalog_includes_codex_with_valid_defaults():
    assert platforms.PLATFORM_NAMES["codex"]
    defaults = platforms.WorkspaceConfigStore.platform_model("codex")().model_dump(mode="json")
    assert defaults["access_scope"] == "admin" and defaults["max_reference_downloads"] == 8
    assert "codex" in platforms.WorkspaceConfigStore.schema()["sections"]
