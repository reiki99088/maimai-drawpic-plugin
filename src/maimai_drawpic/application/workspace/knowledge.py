"""工作台「世界知识」页：浏览、手改、删除词条，换参考图，触发重新检索。"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import asyncio
import base64
import re

from ...infrastructure.concurrency import run_owned_thread
from ...infrastructure.media.images import normalize_reference_image
from ...infrastructure.storage.platforms import parse_json_object
from ...infrastructure.storage.results import ImageResultStore
from ...infrastructure.storage.world_knowledge import (
    EDITABLE_FIELDS, KINDS, WorldKnowledgeStore, entry_names, is_expired, kind_label, normalize_key,
)

PAGE_SIZE = 30
THUMBNAIL_EDGE = 200
_ENTRY_ID = re.compile(r"w_[0-9a-f]{10}")
_SAVE_FIELDS = {"id", *EDITABLE_FIELDS, "disabled", "auto_image", "locked_fields"}
_SHOWN_FIELDS = (
    "id", "name", "aliases", "kind", "franchise", "look", "draw_hint", "facts", "status", "locked_fields",
    "disabled", "auto_image", "fetched_at", "expires_at", "updated_at", "last_used_at", "use_count",
)


def _entry_id(value: Any) -> str:
    if not isinstance(value, str) or not _ENTRY_ID.fullmatch(value):
        raise ValueError("词条 ID 无效")
    return value


def _string_list(value: Any, label: str) -> List[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label}应为文字列表")
    return value


class WorkspaceKnowledgeService:
    def __init__(
        self,
        *,
        ctx: Any,
        data_dir: Path,
        get_store: Callable[[], Optional[WorldKnowledgeStore]],
        get_service: Callable[[], Any],
        get_config: Callable[[], Any],
    ) -> None:
        self.ctx, self.data_dir = ctx, Path(data_dir)
        self.get_store, self.get_service, self.get_config = get_store, get_service, get_config

    def _store(self) -> WorldKnowledgeStore:
        store = self.get_store()
        if store is None:
            raise ValueError("世界知识词条库尚未就绪")
        return store

    def _present(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """页面用的词条快照：参考图换成小缩略图，不回传原图或本地路径。"""
        store = self._store()
        refs = []
        for ref in entry["refs"]:
            preview = ""
            raw = store.read_image(entry["id"], ref["file"])
            if raw:
                try:
                    thumbnail = ImageResultStore._preview(raw, THUMBNAIL_EDGE, 24000)
                    preview = "data:image/webp;base64," + base64.b64encode(thumbnail).decode("ascii")
                except (OSError, ValueError):
                    preview = ""
            refs.append({
                "file": ref["file"], "manual": ref["manual"], "source": ref["source"], "page_url": ref["page_url"],
                "width": ref["width"], "height": ref["height"], "preview": preview,
            })
        return {
            **{key: entry[key] for key in _SHOWN_FIELDS},
            "kind_label": kind_label(entry["kind"]),
            "expired": is_expired(entry),
            "sources": [dict(source) for source in entry["sources"]],
            "refs": refs,
        }

    async def list(self, page: int = 1, search: str = "") -> Dict[str, Any]:
        if type(page) is not int or not 1 <= page <= 100:
            raise ValueError("页码应为 1～100")
        if not isinstance(search, str) or len(search) > 100:
            raise ValueError("搜索词最多 100 个字符")
        store = self._store()
        entries = await asyncio.to_thread(store.list)
        needle = normalize_key(search)
        if needle:
            entries = [
                entry for entry in entries
                if any(needle in normalize_key(name) for name in [*entry_names(entry), entry["franchise"]])
            ]
        entries.sort(key=lambda entry: entry["updated_at"] or entry["created_at"], reverse=True)
        chunk = entries[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
        general = self.get_config().general
        return {
            "enabled": general.world_knowledge_enabled,
            "verify_enabled": general.world_knowledge_verify_enabled,
            "online": getattr(self.ctx, "web", None) is not None,
            "kinds": [{"value": key, "label": value[0]} for key, value in KINDS.items()],
            "items": await asyncio.to_thread(lambda: [self._present(entry) for entry in chunk]),
            "total": len(entries),
            "page_size": PAGE_SIZE,
        }

    async def save(self, entry_json: str) -> Dict[str, Any]:
        values = parse_json_object(entry_json)
        if values.keys() - _SAVE_FIELDS:
            raise ValueError("词条包含未知字段")
        entry_id = values.pop("id", "") or None
        if entry_id is not None:
            _entry_id(entry_id)
        for field in ("aliases", "facts", "locked_fields"):
            if field in values:
                _string_list(values[field], {"aliases": "别名", "facts": "近期事实", "locked_fields": "锁定字段"}[field])
        for field in ("name", "kind", "franchise", "look", "draw_hint"):
            if field in values and not isinstance(values[field], str):
                raise ValueError("词条字段应为文字")
        for field in ("disabled", "auto_image"):
            if field in values and type(values[field]) is not bool:
                raise ValueError(f"{field} 只能是布尔值")
        store = self._store()
        entry = await run_owned_thread(store.save_manual, entry_id, values)
        return {"entry": await asyncio.to_thread(self._present, entry)}

    async def delete(self, entry_id: str) -> Dict[str, Any]:
        deleted = await run_owned_thread(self._store().delete, _entry_id(entry_id))
        return {"deleted": deleted}

    async def refresh(self, entry_id: str) -> Dict[str, Any]:
        """标记过期并在后台重查；联网不可用时只标记过期，下次出图再查。"""
        store = self._store()
        entry = await asyncio.to_thread(store.get, _entry_id(entry_id))
        if entry is None:
            raise ValueError("词条不存在或已被删除")
        if entry["disabled"]:
            raise ValueError("已禁用的词条不会检索，先取消禁用")
        entry = await run_owned_thread(store.expire, entry_id)
        service = self.get_service()
        started = service is not None and service.refresh_entry(entry)
        return {
            "started": started,
            "message": "已开始后台重新检索，稍后刷新查看" if started
            else "宿主联网检索暂不可用或后台检索已满，已标记过期，下次用到时重新检索",
        }

    async def add_image(self, upload_id: str, entry_id: str) -> Dict[str, Any]:
        """领取工作台上传的图作为手工参考图；手工图优先，满 2 张时先挤掉自动图。"""
        _entry_id(entry_id)
        claimed = await self.ctx.webui.claim_upload(upload_id)
        path = Path(claimed["path"])
        root = (self.data_dir / "uploads").resolve()
        if path.is_symlink() or path.resolve().parent != root:
            raise ValueError("上传文件不属于当前插件")

        def read() -> bytes:
            try:
                raw = path.read_bytes()
            except FileNotFoundError:
                raise ValueError("上传图片已过期或被清理，请重新上传") from None
            finally:
                path.unlink(missing_ok=True)
            if len(raw) > 20 * 1024 * 1024 or sha256(raw).hexdigest() != claimed["sha256"]:
                raise ValueError("上传图片大小或校验值异常")
            return raw

        raw = await asyncio.to_thread(read)
        data, size = await asyncio.to_thread(normalize_reference_image, raw)
        store = self._store()
        await run_owned_thread(store.add_image, entry_id, data, manual=True, suffix=".jpg", source="manual", size=size)
        entry = await asyncio.to_thread(store.get, entry_id)
        if entry is None:
            raise ValueError("词条不存在或已被删除")
        return {"entry": await asyncio.to_thread(self._present, entry)}

    async def drop_image(self, entry_id: str, file_name: str) -> Dict[str, Any]:
        if not isinstance(file_name, str) or not file_name or len(file_name) > 64:
            raise ValueError("参考图文件名无效")
        store = self._store()
        if not await run_owned_thread(store.drop_image, _entry_id(entry_id), file_name):
            raise ValueError("参考图不存在或已删除")
        entry = await asyncio.to_thread(store.get, entry_id)
        if entry is None:
            raise ValueError("词条不存在或已被删除")
        return {"entry": await asyncio.to_thread(self._present, entry)}
