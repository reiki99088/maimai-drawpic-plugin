"""世界知识词条库：游戏角色、电竞战队、赛事、新产品等「画错会被认出来」的现实对象。

- 词条存 `data_dir/world_knowledge/entries.json`（可读的 UTF-8 JSON），参考图在同目录 `images/`；
- 每条词条有一句外观短语（look）、英文绘图提示（draw_hint）、带日期的少量事实、≤2 张参考图和来源；
- 自动检索的词条按种类设有效期（赛事几天就变，游戏角色几个月不变），过期再查；
  用户在工作台改过的字段记进 locked_fields，重新检索时不覆盖；手工词条永不过期；
- 名称匹配：NFKC + casefold 后比对名称与别名；短 ASCII 名（T1、G2）按词边界匹配，T1 不命中 T10；
- 文件损坏时保留原件并拒绝读写，不用空库覆盖。
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit
import hashlib
import re
import unicodedata

from .atomic import write_json_atomically
from .settings import read_json_file
from ..concurrency import synchronized

SCHEMA_VERSION = 1
MAX_ENTRIES = 500
MAX_NAME_CHARS = 24
MAX_ALIASES = 8
MAX_LOOK_CHARS = 40
MAX_DRAW_HINT_CHARS = 200
MAX_FACTS = 3
MAX_FACT_CHARS = 60
MAX_FRANCHISE_CHARS = 24
MAX_SOURCES = 4
MAX_REFS = 2

#: 种类 → (中文名, 有效期天数, 是否默认自动取图)
KINDS: Dict[str, Tuple[str, int, bool]] = {
    "game_character": ("游戏角色", 90, True),
    "game": ("游戏", 30, True),
    "esports_team": ("电竞战队", 14, True),
    "esports_player": ("电竞选手", 14, False),
    "esports_event": ("赛事", 3, True),
    "product": ("产品", 30, True),
    "brand": ("品牌", 180, True),
    "public_figure": ("公众人物", 30, False),
    "meme": ("网络梗", 60, True),
    "place": ("地点", 30, True),
    "other": ("其他", 14, True),
}
#: 查不到 / 出错的负缓存天数：避免对同一个词反复检索
NEGATIVE_TTL_DAYS = 3
#: 允许在工作台手改并锁定的字段
EDITABLE_FIELDS = ("name", "aliases", "kind", "franchise", "look", "draw_hint", "facts")
STATUSES = ("ok", "not_found", "error", "manual")
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


class WorldKnowledgeStoreError(ValueError):
    """词条库文件无法读取或写入；原件保留，调用方应降级为不使用世界知识。"""


def kind_label(kind: str) -> str:
    return KINDS.get(kind, KINDS["other"])[0]


def kind_allows_auto_image(kind: str) -> bool:
    return KINDS.get(kind, KINDS["other"])[2]


def normalize_key(text: Any) -> str:
    """匹配用的归一化：全半角统一、大小写不敏感、去空白与标点。"""
    folded = unicodedata.normalize("NFKC", str(text or "")).casefold()
    return "".join(ch for ch in folded if not (ch.isspace() or unicodedata.category(ch)[0] in "PSZ"))


def entry_id_for(kind: str, name: str) -> str:
    return "w_" + hashlib.sha1(f"{kind}|{normalize_key(name)}".encode("utf-8")).hexdigest()[:10]


def _now() -> datetime:
    return datetime.now().astimezone().replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _parse_time(value: Any) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else parsed.astimezone()


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _line(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


# ---------------------------------------------------------------------------- 字段清洗


def clean_name(name: Any) -> str:
    value = " ".join(str(name or "").split())
    if not value:
        raise ValueError("词条名称不能为空")
    if len(value) > MAX_NAME_CHARS:
        raise ValueError(f"词条名称最多 {MAX_NAME_CHARS} 个字")
    if any(ch in value for ch in "「」\"\\"):
        raise ValueError("词条名称不能包含「」、引号或反斜杠")
    return value


def clean_aliases(aliases: Any, name: str = "") -> List[str]:
    result: List[str] = []
    seen = {normalize_key(name)} if name else set()
    for raw in aliases if isinstance(aliases, (list, tuple)) else []:
        alias = _line(raw, MAX_NAME_CHARS)
        for ch in "「」\"\\":
            alias = alias.replace(ch, "")
        key = normalize_key(alias)
        if key and key not in seen:
            seen.add(key)
            result.append(alias)
    return result[:MAX_ALIASES]


def clean_look(look: Any) -> str:
    """外观短语只留可见特征的一句话：去掉括号引号并截断，不因 LLM 多写而报错。"""
    value = " ".join(str(look or "").split())
    for ch in "「」\"“”()（）\\":
        value = value.replace(ch, "")
    return value[:MAX_LOOK_CHARS]


def clean_draw_hint(hint: Any) -> str:
    return _line(hint, MAX_DRAW_HINT_CHARS).replace("\\", "")


def clean_facts(facts: Any) -> List[str]:
    result = []
    for raw in facts if isinstance(facts, (list, tuple)) else []:
        fact = _line(raw, MAX_FACT_CHARS)
        if fact:
            result.append(fact)
    return result[:MAX_FACTS]


def strip_url_query(url: Any) -> str:
    """来源链接只留 scheme + host + path：不存签名参数、追踪参数与凭据。"""
    raw = str(url or "").strip()
    try:
        parts = urlsplit(raw)
        host = parts.hostname or ""
        port = parts.port
    except ValueError:
        return ""
    if parts.scheme not in ("http", "https") or not host:
        return ""
    netloc = f"[{host}]" if ":" in host else host
    if port is not None:
        netloc += f":{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))[:300]


def source_domain(url: Any) -> str:
    try:
        return (urlsplit(str(url or "")).hostname or "")[:80]
    except ValueError:
        return ""


def clean_sources(sources: Any) -> List[Dict[str, str]]:
    result: List[Dict[str, str]] = []
    for raw in sources if isinstance(sources, (list, tuple)) else []:
        if not isinstance(raw, dict):
            continue
        url = strip_url_query(raw.get("url"))
        if url and all(item["url"] != url for item in result):
            result.append({
                "title": _line(raw.get("title"), 80),
                "url": url,
                "published_at": _line(raw.get("published_at"), 32),
            })
    return result[:MAX_SOURCES]


def clean_kind(kind: Any) -> str:
    value = str(kind or "").strip()
    return value if value in KINDS else "other"


# ---------------------------------------------------------------------------- 名称匹配


_SHORT_ASCII = re.compile(r"^[a-z0-9]{1,3}$")


def mention_position(text: str, name: str) -> int:
    """name 在 text 里第一次出现的位置（只用于排序）；没出现返回 -1。"""
    key = normalize_key(name)
    if _SHORT_ASCII.match(key):
        folded = unicodedata.normalize("NFKC", text or "").casefold()
        match = re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", folded)
        return match.start() if match else -1
    if len(key) < 2:
        return -1
    return normalize_key(text).find(key)


def entry_names(entry: Dict[str, Any]) -> List[str]:
    return [entry["name"], *entry.get("aliases", [])]


def entry_mention(text: str, entry: Dict[str, Any]) -> int:
    hits = [position for position in (mention_position(text, name) for name in entry_names(entry)) if position >= 0]
    return min(hits) if hits else -1


def _keys(names: Iterable[Any]) -> set:
    return {key for key in (normalize_key(name) for name in names) if key}


# ---------------------------------------------------------------------------- 记录规范化


def _normalize_ref(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    file_name = Path(str(raw.get("file") or "")).name
    if not file_name or Path(file_name).suffix.lower() not in _IMAGE_SUFFIXES:
        return None
    return {
        "file": file_name,
        "page_url": strip_url_query(raw.get("page_url")),
        "source": _line(raw.get("source"), 32),
        "width": raw.get("width") if isinstance(raw.get("width"), int) else None,
        "height": raw.get("height") if isinstance(raw.get("height"), int) else None,
        "manual": bool(raw.get("manual")),
        "added_at": _line(raw.get("added_at"), 32),
    }


def _normalize_entry(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict) or not str(raw.get("id") or "").startswith("w_"):
        return None
    try:
        name = clean_name(raw.get("name"))
    except ValueError:
        return None
    status = str(raw.get("status") or "ok")
    return {
        "id": str(raw["id"])[:16],
        "name": name,
        "aliases": clean_aliases(raw.get("aliases"), name),
        "kind": clean_kind(raw.get("kind")),
        "franchise": _line(raw.get("franchise"), MAX_FRANCHISE_CHARS),
        "look": clean_look(raw.get("look")),
        "draw_hint": clean_draw_hint(raw.get("draw_hint")),
        "facts": clean_facts(raw.get("facts")),
        "refs": [ref for ref in (_normalize_ref(item) for item in raw.get("refs") or []) if ref][:MAX_REFS],
        "sources": clean_sources(raw.get("sources")),
        "status": status if status in STATUSES else "ok",
        "fetched_at": _line(raw.get("fetched_at"), 32),
        "expires_at": _line(raw.get("expires_at"), 32),
        "locked_fields": [field for field in raw.get("locked_fields") or [] if field in EDITABLE_FIELDS],
        "disabled": bool(raw.get("disabled")),
        "created_at": _line(raw.get("created_at"), 32),
        "updated_at": _line(raw.get("updated_at"), 32),
        "last_used_at": _line(raw.get("last_used_at"), 32),
        "use_count": _int(raw.get("use_count")),
    }


def is_expired(entry: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    """自动词条是否该重新检索；手工词条、禁用词条永不过期。"""
    if entry.get("disabled") or entry.get("status") == "manual":
        return False
    expires = _parse_time(entry.get("expires_at"))
    return expires is None or expires <= (now or _now())


def is_usable(entry: Dict[str, Any]) -> bool:
    """能注入绘图：启用、查到了（或手工建的）、并且有内容。"""
    return (
        not entry.get("disabled")
        and entry.get("status") in ("ok", "manual")
        and bool(entry.get("look") or entry.get("facts") or entry.get("refs") or entry.get("draw_hint"))
    )


class WorldKnowledgeStore:
    """线程安全的词条库；读写均为同步文件 IO，异步调用方应放到工作线程。"""

    def __init__(self, data_dir: Path) -> None:
        self.root = Path(data_dir) / "world_knowledge"
        self.path = self.root / "entries.json"
        self.images_dir = self.root / "images"
        self._lock = RLock()
        self._entries: Optional[List[Dict[str, Any]]] = None

    # ------------------------------------------------------------------ 读写

    def _load(self) -> List[Dict[str, Any]]:
        if self._entries is not None:
            return self._entries
        if not self.path.is_file():
            self._entries = []
            return self._entries
        try:
            raw = read_json_file(self.path)
        except (OSError, ValueError) as exc:
            raise WorldKnowledgeStoreError("世界知识词条库无法读取，已保留原件，请修复或删除后重试") from exc
        items = raw.get("entries") if isinstance(raw, dict) else None
        if not isinstance(items, list):
            raise WorldKnowledgeStoreError("世界知识词条库格式不正确，已保留原件")
        entries: List[Dict[str, Any]] = []
        for item in items:
            entry = _normalize_entry(item)
            if entry and all(existing["id"] != entry["id"] for existing in entries):
                entries.append(entry)
        self._entries = entries
        return entries

    def _save(self, entries: List[Dict[str, Any]]) -> None:
        try:
            write_json_atomically(self.path, {"schema_version": SCHEMA_VERSION, "entries": entries})
        except OSError as exc:
            # 写盘失败时丢弃内存快照，下次从磁盘重读，避免内存与文件不一致。
            self._entries = None
            raise WorldKnowledgeStoreError("世界知识词条库写入失败") from exc
        self._entries = entries

    def _working_copy(self) -> List[Dict[str, Any]]:
        return deepcopy(self._load())

    @synchronized
    def list(self) -> List[Dict[str, Any]]:
        return deepcopy(self._load())

    @synchronized
    def get(self, entry_id: str) -> Optional[Dict[str, Any]]:
        entry = next((item for item in self._load() if item["id"] == entry_id), None)
        return deepcopy(entry) if entry else None

    @synchronized
    def find(self, name: str, kind: Optional[str] = None, aliases: Iterable[str] = ()) -> Optional[Dict[str, Any]]:
        """按名称或别名找词条（归一化比较）；kind 给定时优先同种类。"""
        match = self._match(self._load(), name, aliases, kind)
        return deepcopy(match) if match else None

    @synchronized
    def mentioned(self, text: str) -> List[Dict[str, Any]]:
        """文本里提到的、手工或锁定过的可用词条，按首次出现位置排序（补 LLM 漏抽）。"""
        hits = []
        for entry in self._load():
            if not is_usable(entry) or not (entry["status"] == "manual" or entry["locked_fields"]):
                continue
            position = entry_mention(text, entry)
            if position >= 0:
                hits.append((position, entry))
        return [deepcopy(entry) for _, entry in sorted(hits, key=lambda item: item[0])]

    def image_path(self, file_name: str) -> Path:
        return self.images_dir / Path(file_name).name

    @staticmethod
    def _match(
        entries: List[Dict[str, Any]], name: Any, aliases: Iterable[Any], kind: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        keys = _keys([name, *(aliases or [])])
        if not keys:
            return None
        hits = [entry for entry in entries if keys & _keys(entry_names(entry))]
        same = [entry for entry in hits if entry["kind"] == kind] if kind else []
        return (same or hits or [None])[0]

    # ------------------------------------------------------------------ 自动检索写入

    @synchronized
    def upsert_auto(self, card: Dict[str, Any], *, now: Optional[datetime] = None) -> Dict[str, Any]:
        """写入一张检索得到的词条卡；用户锁定的字段保留原值，禁用词条不改。

        card 含 name、kind，可含 aliases / franchise / look / draw_hint / facts / sources；
        found=False 表示没查到（负缓存），error=True 表示检索出错。参考图另由 add_image 写入。
        """
        now = now or _now()
        name = clean_name(card.get("name"))
        kind = clean_kind(card.get("kind"))
        entries = self._working_copy()
        entry = self._match(entries, name, card.get("aliases") or [], kind)
        if entry is None:
            entry = _normalize_entry({"id": entry_id_for(kind, name), "name": name, "kind": kind,
                                      "created_at": _iso(now)})
            assert entry is not None
            entries.append(entry)
        if entry["disabled"]:
            return deepcopy(entry)
        found = card.get("found", True) is not False
        if found:
            fresh = {
                "name": name,
                "aliases": clean_aliases([*entry["aliases"], *(card.get("aliases") or [])], name),
                "kind": kind,
                "franchise": _line(card.get("franchise"), MAX_FRANCHISE_CHARS),
                "look": clean_look(card.get("look")),
                "draw_hint": clean_draw_hint(card.get("draw_hint")),
                "facts": clean_facts(card.get("facts")),
            }
            for field, value in fresh.items():
                if field not in entry["locked_fields"]:
                    entry[field] = value
            entry["sources"] = clean_sources(card.get("sources")) or entry["sources"]
        if entry["status"] != "manual":
            entry["status"] = "ok" if found else ("error" if card.get("error") else "not_found")
        ttl = KINDS[entry["kind"]][1] if found else NEGATIVE_TTL_DAYS
        entry.update(fetched_at=_iso(now), expires_at=_iso(now + timedelta(days=ttl)), updated_at=_iso(now))
        dropped = self._prune(entries)
        self._save(entries)
        self._remove_unused_images(dropped, entries)
        return deepcopy(entry)

    @staticmethod
    def _prune(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if len(entries) <= MAX_ENTRIES:
            return []

        def last_used(entry: Dict[str, Any]) -> float:
            moment = _parse_time(entry.get("last_used_at")) or _parse_time(entry.get("created_at"))
            return moment.timestamp() if moment else 0.0

        # 库满时只清理没手改、没手工图的自动词条，最久没用的先删
        candidates = sorted(
            (entry for entry in entries
             if entry["status"] != "manual" and not entry["locked_fields"]
             and not any(ref["manual"] for ref in entry["refs"])),
            key=last_used,
        )
        dropped = candidates[: len(entries) - MAX_ENTRIES]
        for entry in dropped:
            entries.remove(entry)
        return dropped

    # ------------------------------------------------------------------ 手工编辑

    @synchronized
    def save_manual(self, entry_id: Optional[str], fields: Dict[str, Any]) -> Dict[str, Any]:
        """工作台保存词条：新建（entry_id 为空）或修改；改过的字段自动锁定。

        fields 可含 EDITABLE_FIELDS、disabled，以及 locked_fields（显式给出时以它为准，用于解锁）。
        """
        now = _now()
        entries = self._working_copy()
        if entry_id:
            entry = next((item for item in entries if item["id"] == entry_id), None)
            if entry is None:
                raise ValueError("词条不存在或已被删除")
        else:
            if len(entries) >= MAX_ENTRIES:
                raise ValueError(f"词条库最多 {MAX_ENTRIES} 条")
            name = clean_name(fields.get("name"))
            kind = clean_kind(fields.get("kind"))
            entry = _normalize_entry({"id": entry_id_for(kind, name), "name": name, "kind": kind,
                                      "status": "manual", "created_at": _iso(now)})
            assert entry is not None
            entries.append(entry)
        changed: set = set()
        for field in EDITABLE_FIELDS:
            if field in fields:
                value = self._clean_field(field, fields[field], entry)
                if value != entry[field]:
                    entry[field] = value
                    changed.add(field)
        own = _keys(entry_names(entry))
        for other in entries:
            if other is not entry and own & _keys(entry_names(other)):
                raise ValueError(f"名称或别名与词条「{other['name']}」重复")
        if "disabled" in fields:
            entry["disabled"] = bool(fields["disabled"])
        locked = fields.get("locked_fields")
        base = {field for field in locked if field in EDITABLE_FIELDS} if isinstance(locked, list) else set(
            entry["locked_fields"]
        )
        entry["locked_fields"] = sorted(base | changed)
        entry["updated_at"] = _iso(now)
        self._save(entries)
        return deepcopy(entry)

    @staticmethod
    def _clean_field(field: str, value: Any, entry: Dict[str, Any]) -> Any:
        if field == "name":
            return clean_name(value)
        if field == "aliases":
            return clean_aliases(value, entry["name"])
        if field == "kind":
            if str(value or "") not in KINDS:
                raise ValueError("词条种类不合法")
            return str(value)
        if field == "franchise":
            return _line(value, MAX_FRANCHISE_CHARS)
        if field == "look":
            return clean_look(value)
        if field == "draw_hint":
            return clean_draw_hint(value)
        return clean_facts(value)

    @synchronized
    def delete(self, entry_id: str) -> bool:
        entries = self._working_copy()
        entry = next((item for item in entries if item["id"] == entry_id), None)
        if entry is None:
            return False
        entries.remove(entry)
        self._save(entries)
        self._remove_unused_images([entry], entries)
        return True

    @synchronized
    def expire(self, entry_id: str) -> Dict[str, Any]:
        """标记为立即过期（工作台「重新检索」），下次用到或后台刷新时重查。"""
        entries = self._working_copy()
        entry = next((item for item in entries if item["id"] == entry_id), None)
        if entry is None:
            raise ValueError("词条不存在或已被删除")
        entry["expires_at"] = ""
        self._save(entries)
        return deepcopy(entry)

    # ------------------------------------------------------------------ 参考图

    @synchronized
    def add_image(
        self,
        entry_id: str,
        data: bytes,
        *,
        manual: bool,
        suffix: str = ".jpg",
        page_url: str = "",
        source: str = "",
        size: Optional[Tuple[int, int]] = None,
    ) -> Optional[Dict[str, Any]]:
        """给词条加一张已校验、已规范化的参考图。

        自动图每条只留 1 张（新的替换旧的）；手工图优先，合计 ≤2，满了先挤掉自动图。
        手工图已占满时不再收自动图，返回 None。
        """
        suffix = suffix if suffix.startswith(".") else "." + suffix
        if suffix.lower() not in _IMAGE_SUFFIXES:
            raise ValueError("参考图格式不受支持")
        entries = self._working_copy()
        entry = next((item for item in entries if item["id"] == entry_id), None)
        if entry is None:
            raise ValueError("词条不存在或已被删除")
        manual_refs = [ref for ref in entry["refs"] if ref["manual"]]
        auto_refs = [ref for ref in entry["refs"] if not ref["manual"]]
        if not manual and len(manual_refs) >= MAX_REFS:
            return None
        file_name = f"{entry_id}_{hashlib.sha256(data).hexdigest()[:10]}{suffix.lower()}"
        existing = next((ref for ref in entry["refs"] if ref["file"] == file_name), None)
        if existing is not None:
            return deepcopy(existing)
        path = self.image_path(file_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        try:
            temporary.write_bytes(data)
            temporary.replace(path)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise WorldKnowledgeStoreError("世界知识参考图写入失败") from exc
        ref = _normalize_ref({
            "file": file_name, "page_url": page_url, "source": source,
            "width": size[0] if size else None, "height": size[1] if size else None,
            "manual": manual, "added_at": _iso(_now()),
        })
        assert ref is not None
        dropped: List[Dict[str, Any]] = []
        if manual:
            manual_refs.insert(0, ref)
            while len(manual_refs) + len(auto_refs) > MAX_REFS:
                dropped.append(auto_refs.pop() if auto_refs else manual_refs.pop())
        else:
            dropped, auto_refs = auto_refs, [ref]
        entry["refs"] = manual_refs + auto_refs
        entry["updated_at"] = _iso(_now())
        try:
            self._save(entries)
        except WorldKnowledgeStoreError:
            path.unlink(missing_ok=True)
            raise
        self._unlink_unused([item["file"] for item in dropped], entries)
        return deepcopy(ref)

    @synchronized
    def drop_image(self, entry_id: str, file_name: str) -> bool:
        entries = self._working_copy()
        entry = next((item for item in entries if item["id"] == entry_id), None)
        if entry is None or all(ref["file"] != file_name for ref in entry["refs"]):
            return False
        entry["refs"] = [ref for ref in entry["refs"] if ref["file"] != file_name]
        entry["updated_at"] = _iso(_now())
        self._save(entries)
        self._unlink_unused([file_name], entries)
        return True

    @synchronized
    def read_image(self, entry_id: str, file_name: str) -> Optional[bytes]:
        entry = next((item for item in self._load() if item["id"] == entry_id), None)
        if entry is None or all(ref["file"] != file_name for ref in entry["refs"]):
            return None
        try:
            return self.image_path(file_name).read_bytes()
        except OSError:
            return None

    def _remove_unused_images(self, removed: List[Dict[str, Any]], remaining: List[Dict[str, Any]]) -> None:
        self._unlink_unused([ref["file"] for entry in removed for ref in entry.get("refs", [])], remaining)

    def _unlink_unused(self, files: List[str], entries: List[Dict[str, Any]]) -> None:
        used = {ref["file"] for entry in entries for ref in entry["refs"]}
        for file_name in files:
            if file_name not in used:
                try:
                    self.image_path(file_name).unlink(missing_ok=True)
                except OSError:
                    pass  # 残留文件不影响词条库；下次删除同名图时再试。

    # ------------------------------------------------------------------ 使用记录

    @synchronized
    def touch_used(self, entry_ids: Iterable[str]) -> None:
        ids = set(entry_ids)
        if not ids:
            return
        entries = self._working_copy()
        moment = _iso(_now())
        hit = False
        for entry in entries:
            if entry["id"] in ids:
                entry["last_used_at"] = moment
                entry["use_count"] += 1
                hit = True
        if hit:
            self._save(entries)
