"""Codex 智能体会话索引：把生成结果映射回会话，用于二次调整时接续原会话。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional
import json
import re
import shutil

from PIL import Image

from .atomic import write_json_atomically

MAX_THREADS = 100
MAX_RESULTS_PER_THREAD = 12
# 64 位差异哈希允许的最大汉明距离；聊天平台重新压缩后的同一张图通常在 0～4 之间。
DHASH_DISTANCE = 6
_THREAD_ID = re.compile(r"[A-Za-z0-9-]{8,80}")
_WORK_KEY = re.compile(r"[a-f0-9]{32}")


def image_fingerprint(raw: bytes) -> Dict[str, Any]:
    """返回精确哈希与对重新压缩鲁棒的差异哈希。"""

    with Image.open(BytesIO(raw)) as image:
        width, height = image.size
        gray = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
        pixels = gray.tobytes()  # 灰度图每像素一个字节，兼容各 Pillow 版本。
    bits = 0
    for row in range(8):
        for column in range(8):
            bits = (bits << 1) | int(pixels[row * 9 + column] > pixels[row * 9 + column + 1])
    return {"sha256": sha256(raw).hexdigest(), "dhash": f"{bits:016x}", "width": width, "height": height}


def _similar(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    if left["sha256"] == right["sha256"]:
        return True
    if not left["height"] or not right["height"]:
        return False
    ratio = (left["width"] / left["height"]) / (right["width"] / right["height"])
    if not 0.9 <= ratio <= 1.1:
        return False
    return bin(int(left["dhash"], 16) ^ int(right["dhash"], 16)).count("1") <= DHASH_DISTANCE


@dataclass(frozen=True, slots=True)
class AgentThread:
    thread_id: str
    instance: str
    session_key: str
    work_dir: Path
    updated_at: datetime


class CodexThreadStore:
    """持久化会话映射；文件损坏时保留原件并停用接续，不以空状态覆盖。"""

    def __init__(self, root: Path, logger: Any = None) -> None:
        self.root = root
        self.path = root / "threads.json"
        self.threads_dir = root / "threads"
        self.logger = logger
        self._lock = RLock()
        self._threads: Dict[str, Dict[str, Any]] = {}
        self._load_failed = False

    @property
    def available(self) -> bool:
        return not self._load_failed

    def load(self) -> None:
        with self._lock:
            if not self.path.exists():
                self._threads, self._load_failed = {}, False
                return
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                threads = payload["threads"]
                if payload.get("schema_version") != 1 or not isinstance(threads, dict):
                    raise ValueError("unsupported")
                for thread_id, record in threads.items():
                    self._validate(thread_id, record)
            except Exception:
                self._load_failed = True
                if self.logger is not None:
                    self.logger.error(
                        "Codex 会话索引无法读取，已保留原文件并停用二次调整接续；修复或移走 %s 后重新加载插件",
                        self.path.name,
                    )
                return
            self._threads, self._load_failed = threads, False

    @staticmethod
    def _validate(thread_id: Any, record: Any) -> None:
        if not isinstance(thread_id, str) or not _THREAD_ID.fullmatch(thread_id) or not isinstance(record, dict):
            raise ValueError("invalid thread")
        if not isinstance(record.get("work_key"), str) or not _WORK_KEY.fullmatch(record["work_key"]):
            raise ValueError("invalid work key")
        for key in ("instance", "session_key", "updated_at"):
            if not isinstance(record.get(key), str):
                raise ValueError("invalid field")
        datetime.fromisoformat(record["updated_at"])
        results = record.get("results")
        if not isinstance(results, list) or not all(
            isinstance(item, dict)
            and isinstance(item.get("sha256"), str)
            and isinstance(item.get("dhash"), str)
            and type(item.get("width")) is int
            and type(item.get("height")) is int
            for item in results
        ):
            raise ValueError("invalid results")

    def new_work_dir(self) -> Path:
        from uuid import uuid4

        return self.threads_dir / uuid4().hex

    def find(
        self, *, instance: str, session_key: str, images: List[bytes], retention_days: int
    ) -> Optional[AgentThread]:
        """按源图匹配同一会话、同一平台实例近期生成的结果；未匹配返回 None。"""

        if not images:
            return None
        fingerprints = []
        for raw in images:
            try:
                fingerprints.append(image_fingerprint(raw))
            except Exception:
                continue
        with self._lock:
            if self._load_failed:
                return None
            cutoff = datetime.now() - timedelta(days=retention_days)
            candidates = sorted(self._threads.items(), key=lambda item: item[1]["updated_at"], reverse=True)
            for thread_id, record in candidates:
                updated = datetime.fromisoformat(record["updated_at"])
                if record["instance"] != instance or record["session_key"] != session_key or updated < cutoff:
                    continue
                work_dir = self.threads_dir / record["work_key"]
                if not work_dir.is_dir():
                    continue
                if any(_similar(source, result) for source in fingerprints for result in record["results"]):
                    return AgentThread(thread_id, instance, session_key, work_dir, updated)
        return None

    def record(
        self,
        *,
        thread_id: str,
        instance: str,
        session_key: str,
        work_dir: Path,
        images: List[bytes],
        retention_days: int,
    ) -> None:
        """记录本轮结果；接续的会话会追加结果并刷新时间。"""

        if not _THREAD_ID.fullmatch(thread_id or "") or not _WORK_KEY.fullmatch(work_dir.name):
            return
        if work_dir.parent.resolve() != self.threads_dir.resolve():
            return
        fingerprints = [image_fingerprint(raw) for raw in images]
        with self._lock:
            if self._load_failed:
                return
            previous = self._threads.get(thread_id, {})
            results = (previous.get("results", []) + fingerprints)[-MAX_RESULTS_PER_THREAD:]
            self._threads[thread_id] = {
                "instance": instance,
                "session_key": session_key,
                "work_key": work_dir.name,
                "updated_at": datetime.now().isoformat(),
                "results": results,
            }
            removed = self._prune_locked(retention_days)
            write_json_atomically(self.path, {"schema_version": 1, "threads": self._threads})
        for key in removed:
            shutil.rmtree(self.threads_dir / key, ignore_errors=True)

    def prune(self, retention_days: int) -> int:
        """清理过期会话及无主的旧工作目录；返回删除的目录数。"""

        with self._lock:
            if self._load_failed:
                return 0
            before = dict(self._threads)
            removed = self._prune_locked(retention_days)
            if self._threads != before:
                write_json_atomically(self.path, {"schema_version": 1, "threads": self._threads})
            owned = {record["work_key"] for record in self._threads.values()}
        cutoff = datetime.now() - timedelta(days=retention_days)
        if self.threads_dir.is_dir():
            for directory in self.threads_dir.iterdir():
                if directory.name in owned or not _WORK_KEY.fullmatch(directory.name):
                    continue
                try:
                    stale = datetime.fromtimestamp(directory.stat().st_mtime) < cutoff
                except OSError:
                    continue
                if stale:
                    removed.append(directory.name)
        for key in dict.fromkeys(removed):
            shutil.rmtree(self.threads_dir / key, ignore_errors=True)
        return len(set(removed))

    def _prune_locked(self, retention_days: int) -> List[str]:
        cutoff = datetime.now() - timedelta(days=retention_days)
        ordered = sorted(self._threads.items(), key=lambda item: item[1]["updated_at"], reverse=True)
        keep = {
            thread_id: record
            for index, (thread_id, record) in enumerate(ordered)
            if index < MAX_THREADS and datetime.fromisoformat(record["updated_at"]) >= cutoff
        }
        removed = [record["work_key"] for thread_id, record in self._threads.items() if thread_id not in keep]
        still_used = {record["work_key"] for record in keep.values()}
        self._threads = keep
        return [key for key in removed if key not in still_used]
