"""世界知识服务：识别提示词里的现实对象 → 查词条库或联网检索 → 整理词条 → 找参考图（固定图源，
找不到再网搜并由图片模型挑选）；出图后对照校验。

所有失败都只降级为 warning：绘图照常进行，取消（CancelledError）照常向上传播。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Set, Tuple
import asyncio
import base64
import re

from ...domain.configuration.models import DrawpicConfig
from ...infrastructure.concurrency import run_owned_thread
from ...infrastructure.http import HttpProxySettings, sanitize_provider_text
from ...infrastructure.media.downloads import FAKE_IP_NETWORK, PublicFetchError
from ...infrastructure.media.images import shrink_image_jpeg
from ...infrastructure.media.world_sources import FoundImage, ImageCandidate, WorldImageFinder, search_candidates
from ...infrastructure.providers.image_search import ImageSearchError, SearchImage, build_image_search_clients
from ...infrastructure.storage.world_knowledge import (
    WorldKnowledgeStore, WorldKnowledgeStoreError, entry_mention, is_expired, is_usable, kind_allows_auto_image,
    source_domain,
)
from .prompts import (
    CARD_PROMPT, EXTRACT_PROMPT, MAX_MATERIAL_CHARS, VERIFY_PROMPT, EntityMention, Verdict, compose_world_prompt,
    parse_cards, parse_entities, parse_pick, parse_verdict, render_checklist, render_materials, render_pick_prompt,
)
from .search_pool import ImageSearchPool

SEARCH_TIMEOUT_SECONDS = 20
SEARCH_CONCURRENCY = 2
FETCH_TEXT_CHARS = 3000
THIN_MATERIAL_CHARS = 200
OFFLINE_BACKOFF_SECONDS = 600
IMAGE_RETRY_SECONDS = 6 * 3600
VERIFY_TIMEOUT_SECONDS = 90
MAX_BACKGROUND_LOOKUPS = 4
IMAGE_SEARCH_TIMEOUT_SECONDS = 40
IMAGE_SEARCH_MIN_SECONDS = 12
PREVIEW_CONCURRENCY = 4
PREVIEW_TIMEOUT_SECONDS = 10
PICK_TIMEOUT_SECONDS = 45
# 识别窗口：调用方常把参考图说明、版式写在前面，剧情和对白在后面，只看开头会漏掉真正的对象
EXTRACT_TEXT_CHARS = 8000
# 各步骤的输出上限。宿主模型多为思考模型，思考过程也计入输出 token，预算要给够，
# 否则思考没结束就被截断，正文为空（11 月线上识别全部为空就是 400 太小）
EXTRACT_MAX_TOKENS = 2000
CARD_MAX_TOKENS = 4000
PICK_MAX_TOKENS = 1000
SCREEN_MAX_TOKENS = 1000
VERIFY_MAX_TOKENS = 2000
_RESULT_IMAGE_EDGE = 1280
_REFERENCE_EDGE = 768
_PICK_EDGE = 384
# 网搜取图时附加在名称后面的词，让结果偏向官方设计图而不是新闻配图。
_IMAGE_QUERY_WORDS = {
    "game_character": "角色 立绘",
    "game": "游戏 主视觉",
    "esports_team": "战队 队标 logo",
    "esports_event": "赛事 主视觉 logo",
    "product": "产品 外观 官方图",
    "brand": "品牌 logo",
    "meme": "表情包 原图",
    "place": "实景 照片",
}


class _LlmError(RuntimeError):
    pass


@dataclass
class WorldResolution:
    """一次检索的结果快照：用到的词条、可附加的参考图（词条 id, JPEG）、过程记录。"""

    entries: List[Dict[str, Any]] = field(default_factory=list)
    images: List[Tuple[str, bytes]] = field(default_factory=list)
    searched: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    duration_ms: int = 0
    cards_ready: asyncio.Event = field(default_factory=asyncio.Event)

    def add(self, entry: Dict[str, Any]) -> None:
        if not is_usable(entry):
            return
        for index, existing in enumerate(self.entries):
            if existing["id"] == entry["id"]:
                self.entries[index] = entry
                return
        self.entries.append(entry)

    def warn(self, message: str) -> None:
        if len(self.warnings) < 8:
            self.warnings.append(sanitize_provider_text(message)[:160])

    def image_numbers(self, offset: int) -> Dict[str, int]:
        """参考图接在调用方已有源图之后，按 1 起编号。"""
        return {entry_id: offset + index + 1 for index, (entry_id, _data) in enumerate(self.images)}

    def prompt_suffix(self, offset: int) -> str:
        return compose_world_prompt(self.entries, self.image_numbers(offset))

    def summary(self) -> List[Dict[str, Any]]:
        with_image = {entry_id for entry_id, _data in self.images}
        return [
            {
                "id": entry["id"], "name": entry["name"], "kind": entry["kind"], "franchise": entry["franchise"],
                "aliases": list(entry["aliases"]), "look": entry["look"], "facts": list(entry["facts"]), "has_ref": bool(entry["refs"]),
                "image_used": entry["id"] in with_image, "status": entry["status"],
                "sources": sorted({domain for domain in (source_domain(s["url"]) for s in entry["sources"]) if domain}),
            }
            for entry in self.entries
        ]

    def metadata(self) -> Dict[str, Any]:
        """写进任务记录的脱敏元数据：不含图片字节、检索词或完整链接。"""
        return {
            "entries": [
                {key: item[key] for key in ("id", "name", "kind", "image_used", "sources")} for item in self.summary()
            ],
            "searched": list(self.searched),
            "image_count": len(self.images),
            "warnings": list(self.warnings),
            "duration_ms": self.duration_ms,
        }


class WorldKnowledgeService:
    def __init__(
        self,
        config: DrawpicConfig,
        ctx: Any,
        store: WorldKnowledgeStore,
        *,
        proxy_settings: HttpProxySettings,
        finder: Optional[WorldImageFinder] = None,
        search_clients: Optional[Mapping[str, Any]] = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.config = config
        self.ctx = ctx
        self.store = store
        self._custom_finder = finder is not None
        self.finder = finder or self._make_finder(proxy_settings)
        self._clock = clock
        self._offline_until = 0.0
        self._image_tried: Dict[str, float] = {}
        self._background: Set[asyncio.Task] = set()
        self._search_clients = search_clients
        self.search_pool = ImageSearchPool(self._now)
        self._configure_search(proxy_settings)

    def _configure_search(self, proxy_settings: HttpProxySettings) -> None:
        search = self.config.world_search
        clients = self._search_clients
        if clients is None:
            clients = build_image_search_clients(search, proxy_settings)
        self.search_pool.configure(clients, search.order, search.strategy)

    def _make_finder(self, proxy_settings: HttpProxySettings) -> WorldImageFinder:
        return WorldImageFinder(
            proxy_settings=proxy_settings,
            cache_dir=self.store.root,
            timeout_seconds=SEARCH_TIMEOUT_SECONDS,
            extra_allowed_networks=(FAKE_IP_NETWORK,) if self.general.world_knowledge_allow_fake_ip else (),
        )

    def reconfigure(self, config: DrawpicConfig, *, proxy_settings: HttpProxySettings) -> None:
        """配置刷新时沿用词条库、联网退避与后台检索，只换配置和取图代理。"""
        self.config = config
        if not self._custom_finder:
            self.finder = self._make_finder(proxy_settings)
        self._configure_search(proxy_settings)

    # ------------------------------------------------------------------ 开关

    @property
    def general(self):
        return self.config.general

    def enabled(self, override: Optional[bool] = None) -> bool:
        return bool(self.general.world_knowledge_enabled if override is None else override)

    def _now(self) -> float:
        return self._clock() if self._clock else asyncio.get_running_loop().time()

    def _online(self) -> bool:
        return getattr(self.ctx, "web", None) is not None and self._now() >= self._offline_until

    async def close(self) -> None:
        for task in list(self._background):
            task.cancel()
        if self._background:
            await asyncio.gather(*self._background, return_exceptions=True)
        self._background.clear()

    # ------------------------------------------------------------------ 画前

    async def prepare(
        self,
        text: str,
        *,
        task_id: str = "",
        allow_search: bool = True,
        want_images: bool = True,
        max_images: int = 0,
        progress: Optional[Callable[[str], Any]] = None,
        into: Optional[WorldResolution] = None,
    ) -> WorldResolution:
        """在总时限内尽量收集词条；超时返回已拿到的部分。"""
        result = into or WorldResolution()
        loop = asyncio.get_running_loop()
        started = loop.time()
        deadline = started + self.general.world_knowledge_timeout_seconds
        try:
            await self._prepare(text, result, deadline, task_id=task_id, allow_search=allow_search,
                                want_images=want_images, max_images=max_images, progress=progress)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            result.warn("世界知识检索超时，使用已经拿到的词条")
        except WorldKnowledgeStoreError as exc:
            result.warn(str(exc))
        except Exception as exc:  # 世界知识只增强绘图，任何意外都不能让任务失败
            result.warn(f"世界知识检索出错（{type(exc).__name__}）")
        finally:
            result.cards_ready.set()
            result.duration_ms = round((loop.time() - started) * 1000)
            result.entries.sort(key=lambda entry: _mention_order(text, entry))
        self.ctx.logger.info(
            "世界知识检索完成: task_id=%s entries=%s searched=%s images=%s warnings=%s duration_ms=%s",
            task_id, [entry["name"] for entry in result.entries], len(result.searched), len(result.images),
            len(result.warnings), result.duration_ms,
        )
        return result

    async def _prepare(
        self, text: str, result: WorldResolution, deadline: float, *, task_id: str, allow_search: bool,
        want_images: bool, max_images: int, progress: Optional[Callable[[str], Any]],
    ) -> None:
        mentions: List[EntityMention] = []
        if self.general.world_knowledge_max_entities > 0:
            mentions = await self._extract(text, deadline, result)
        plan: List[Tuple[Optional[EntityMention], Optional[Dict[str, Any]]]] = []
        for mention in mentions:
            plan.append((mention, await asyncio.to_thread(self.store.find, mention.name, mention.kind, mention.aliases)))
        known = {entry["id"] for _mention, entry in plan if entry}
        for entry in await asyncio.to_thread(self.store.mentioned, text):
            if entry["id"] not in known:
                plan.append((None, entry))

        to_search: List[Tuple[EntityMention, Optional[Dict[str, Any]]]] = []
        for mention, entry in plan:
            if entry is not None and entry["disabled"]:
                continue
            if entry is not None and not is_expired(entry):
                result.add(entry)
            elif mention is not None and allow_search and len(to_search) < self.general.world_knowledge_max_searches:
                to_search.append((mention, entry))
            elif entry is not None:
                result.add(entry)  # 过期但还能用：这次不查，先用旧词条
        if to_search and self._online():
            if progress is not None:
                await _maybe_await(progress("正在检索世界知识：" + "、".join(m.name for m, _e in to_search)))
            for entry in await self._search_and_card(to_search, deadline, result, task_id):
                result.add(entry)
        elif to_search:
            result.warn("宿主联网检索不可用，只使用词条库")
            for _mention, entry in to_search:
                if entry is not None:
                    result.add(entry)
        result.cards_ready.set()

        if want_images and self.general.world_knowledge_auto_images:
            for index, entry in enumerate(list(result.entries)):
                if _left(deadline) < 3:
                    break
                if not self._wants_auto_image(entry):
                    continue
                tried = self._image_tried.get(entry["id"])
                if tried is not None and self._now() - tried < IMAGE_RETRY_SECONDS:
                    continue
                self._image_tried[entry["id"]] = self._now()
                updated = await self._attach_image(entry, deadline, result)
                if updated is not None:
                    result.entries[index] = updated
        if max_images > 0:
            for entry in result.entries:
                if len(result.images) >= max_images:
                    break
                for ref in entry["refs"][:1]:
                    data = await asyncio.to_thread(self.store.read_image, entry["id"], ref["file"])
                    if data:
                        result.images.append((entry["id"], data))
        if result.entries:
            await run_owned_thread(self.store.touch_used, [entry["id"] for entry in result.entries])

    @staticmethod
    def _wants_auto_image(entry: Dict[str, Any]) -> bool:
        return (
            not entry["refs"] and entry.get("auto_image", True) and entry["status"] == "ok"
            and kind_allows_auto_image(entry["kind"])
        )

    async def _extract(self, text: str, deadline: float, result: WorldResolution) -> List[EntityMention]:
        prompt = EXTRACT_PROMPT.format(max_entities=self.general.world_knowledge_max_entities, text=text[:EXTRACT_TEXT_CHARS])
        try:
            response = await self._generate(
                prompt, timeout_seconds=min(30.0, _left(deadline)), max_tokens=EXTRACT_MAX_TOKENS,
            )
        except (_LlmError, TimeoutError) as exc:
            result.warn(f"识别现实对象失败：{str(exc) or '超时'}")
            return []
        mentions = parse_entities(response, self.general.world_knowledge_max_entities)
        if not mentions and not _says_none(response):
            result.warn("识别现实对象失败：模型回复格式不对")
        return mentions

    async def _search_and_card(
        self, items: Sequence[Tuple[EntityMention, Optional[Dict[str, Any]]]], deadline: float,
        result: WorldResolution, task_id: str,
    ) -> List[Dict[str, Any]]:
        web = self.ctx.web
        semaphore = asyncio.Semaphore(SEARCH_CONCURRENCY)

        async def search(mention: EntityMention) -> Optional[List[Dict[str, str]]]:
            async with semaphore:
                try:
                    async with asyncio.timeout(min(SEARCH_TIMEOUT_SECONDS, max(1.0, _left(deadline)))):
                        payload = await web.search(mention.query, max_results=5)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    result.warn(f"联网检索失败：{mention.name}（{type(exc).__name__}）")
                    return None
            return _search_hits(payload)

        searched = await asyncio.gather(*(search(mention) for mention, _entry in items))
        result.searched.extend(mention.name for mention, _entry in items)
        if all(hits is None for hits in searched):
            self._offline_until = self._now() + OFFLINE_BACKOFF_SECONDS
            self.ctx.logger.warning("世界知识联网检索全部失败，10 分钟内只用词条库: task_id=%s", task_id)
            return [entry for _mention, entry in items if entry is not None]

        # 摘要太薄时补读一个网页正文（每次最多 1 次）
        fetched = False
        for hits in searched:
            if fetched or not hits or sum(len(hit["text"]) for hit in hits) >= THIN_MATERIAL_CHARS:
                continue
            fetched = True
            try:
                async with asyncio.timeout(min(SEARCH_TIMEOUT_SECONDS, max(1.0, _left(deadline)))):
                    page = _unwrap(await web.fetch(hits[0]["url"]))
                content = " ".join(str(page.get("content") or "").split())[:FETCH_TEXT_CHARS]
                if content:
                    hits[0]["text"] = content
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                result.warn(f"读取网页失败（{type(exc).__name__}）")

        materials: Dict[str, List[Tuple[int, str, str]]] = {}
        numbered: Dict[int, Dict[str, str]] = {}
        entities = [mention for mention, _entry in items]
        number = 0
        for mention, hits in zip(entities, searched):
            for hit in hits or []:
                number += 1
                numbered[number] = hit
                materials.setdefault(mention.name, []).append((number, hit["title"], hit["text"][:MAX_MATERIAL_CHARS]))
        prompt = CARD_PROMPT.format(today=date.today().isoformat(), materials=render_materials(entities, materials))
        try:
            response = await self._generate(prompt, timeout_seconds=min(45.0, _left(deadline)), max_tokens=CARD_MAX_TOKENS)
        except (_LlmError, TimeoutError) as exc:
            result.warn(f"整理词条失败：{str(exc) or '超时'}")
            return [entry for _mention, entry in items if entry is not None]
        cards = parse_cards(response)

        saved: List[Dict[str, Any]] = []
        for (mention, entry), hits in zip(items, searched):
            if hits is None:  # 检索出错不写负缓存，避免一次网络故障把词条标成查不到
                if entry is not None:
                    saved.append(entry)
                continue
            card = cards.get(mention.name.casefold())
            if card is None and hits:
                if entry is not None:
                    saved.append(entry)
                continue
            payload: Dict[str, Any] = {"name": mention.name, "kind": mention.kind, "aliases": list(mention.aliases),
                                       "franchise": mention.franchise, "found": False}
            if card is not None and card.found and hits:
                payload.update(
                    found=True,
                    franchise=card.franchise or mention.franchise,
                    aliases=[*mention.aliases, *card.aliases],
                    look=card.look, draw_hint=card.draw_hint, facts=card.facts,
                    sources=[_source(numbered[n]) for n in card.source_numbers if n in numbered]
                    or [_source(hit) for hit in hits[:2]],
                )
            saved.append(await run_owned_thread(self.store.upsert_auto, payload))
        return saved

    async def _attach_image(
        self, entry: Dict[str, Any], deadline: float, result: WorldResolution,
    ) -> Optional[Dict[str, Any]]:
        accept = None
        if self.general.world_knowledge_screen_images:
            async def accept(image: FoundImage) -> bool:
                return await self._screen(image, entry, deadline)
        try:
            async with asyncio.timeout(max(1.0, _left(deadline))):
                image, reasons = await self.finder.find(
                    name=entry["name"], aliases=entry["aliases"], kind=entry["kind"], franchise=entry["franchise"],
                    pages=[source["url"] for source in entry["sources"]], accept=accept,
                )
        except TimeoutError:
            result.warn(f"查找参考图超时：{entry['name']}")
            return None
        if image is None and self.search_pool.configured:
            image = await self._search_image(entry, deadline, result)
            if image is None:
                return None
        if image is None:
            if reasons:
                result.warn(f"没有找到可用参考图：{entry['name']}（{reasons[-1]}）")
            return None
        ref = await run_owned_thread(
            self.store.add_image, entry["id"], image.data, manual=False, suffix=".jpg",
            page_url=image.page_url, source=image.source, size=image.size,
        )
        if ref is None:
            return None
        return await asyncio.to_thread(self.store.get, entry["id"])

    async def _search_image(
        self, entry: Dict[str, Any], deadline: float, result: WorldResolution,
    ) -> Optional[FoundImage]:
        """固定图源没有图时网搜：硬过滤 → 下缩略图 → 图片模型挑一张；挑不出就换下一个服务（最多 2 个）。"""
        query = _image_query(entry)
        limit = self.config.world_search.max_candidates
        for client in self.search_pool.sequence():
            if _left(deadline) < IMAGE_SEARCH_MIN_SECONDS:
                break
            started = asyncio.get_running_loop().time()
            try:
                found = await client.search(
                    query, count=limit * 2,
                    timeout_seconds=min(IMAGE_SEARCH_TIMEOUT_SECONDS, _left(deadline) - IMAGE_SEARCH_MIN_SECONDS / 2),
                )
            except ImageSearchError as exc:
                self.search_pool.failed(client.name, exc.kind)
                result.warn(str(exc))
                self.ctx.logger.warning(
                    "世界知识搜图失败: entry_id=%s provider=%s kind=%s", entry["id"], client.name, exc.kind,
                )
                continue
            self.search_pool.succeeded(client.name)
            candidates = search_candidates(found, entry["kind"], limit)
            previews = await self._previews(candidates, deadline)
            picked = await self._pick(entry, previews, deadline) if previews else None
            self.ctx.logger.info(
                "世界知识搜图: entry_id=%s provider=%s results=%s candidates=%s previews=%s picked=%s duration_ms=%s",
                entry["id"], client.name, len(found), len(candidates), len(previews), picked or 0,
                round((asyncio.get_running_loop().time() - started) * 1000),
            )
            if picked is None:
                result.warn(f"{client.label} 搜图没有挑出合适的图：{entry['name']}")
                continue
            image = await self._fetch_picked(previews[picked - 1][0], f"{client.label} 搜图", result)
            if image is not None:
                return image
        return None

    async def _previews(
        self, candidates: Sequence[SearchImage], deadline: float,
    ) -> List[Tuple[SearchImage, bytes]]:
        semaphore = asyncio.Semaphore(PREVIEW_CONCURRENCY)

        async def one(candidate: SearchImage) -> Optional[bytes]:
            async with semaphore:
                try:
                    return await self.finder.preview(
                        candidate.thumbnail_url or candidate.url,
                        timeout_seconds=min(PREVIEW_TIMEOUT_SECONDS, max(1.0, _left(deadline))),
                    )
                except PublicFetchError:
                    return None

        try:
            async with asyncio.timeout(max(1.0, _left(deadline) - 5)):
                data = await asyncio.gather(*(one(candidate) for candidate in candidates))
        except TimeoutError:
            return []
        return [(candidate, item) for candidate, item in zip(candidates, data) if item]

    async def _pick(
        self, entry: Dict[str, Any], previews: Sequence[Tuple[SearchImage, bytes]], deadline: float,
    ) -> Optional[int]:
        prompt = render_pick_prompt(entry, len(previews))
        messages = await asyncio.to_thread(_pick_messages, prompt, previews)
        try:
            response = await self._generate(
                messages, timeout_seconds=min(PICK_TIMEOUT_SECONDS, _left(deadline)), max_tokens=PICK_MAX_TOKENS,
                model=self.general.world_knowledge_verify_model,
            )
        except (_LlmError, TimeoutError):
            return None
        return parse_pick(response, len(previews))

    async def _fetch_picked(self, candidate: SearchImage, source: str, result: WorldResolution) -> Optional[FoundImage]:
        """优先下载原图；原图下不了或太小，再试服务给的缩略图。"""
        for url in dict.fromkeys(item for item in (candidate.url, candidate.thumbnail_url) if item):
            try:
                return await self.finder.fetch(ImageCandidate(url, candidate.page_url, source))
            except PublicFetchError as exc:
                result.warn(str(exc))
        return None

    async def _screen(self, image: FoundImage, entry: Dict[str, Any], deadline: float) -> bool:
        prompt = (
            f"这张图是否是「{entry['name']}」（{entry['franchise'] or entry['kind']}）本身的官方形象、标志或产品照片？"
            "如果是别的对象、截图拼图、文字为主的图或无关图片，回答 NO。只回复一行：结论：YES 或 结论：NO"
        )
        messages = await asyncio.to_thread(_image_messages, prompt, [image.data], _REFERENCE_EDGE)
        try:
            response = await self._generate(
                messages, timeout_seconds=min(45.0, _left(deadline)), max_tokens=SCREEN_MAX_TOKENS,
                model=self.general.world_knowledge_verify_model,
            )
        except (_LlmError, TimeoutError):
            return False
        return re.search(r"结论\s*[:：]\s*YES", response, re.IGNORECASE) is not None

    # ------------------------------------------------------------------ 查询 API

    async def lookup(
        self, text: str, *, wait_seconds: float, allow_search: bool = True, override: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """在 wait_seconds 内返回已整理好的词条；没做完的检索留在后台继续写库。"""
        if not self.enabled(override):
            return {"disabled": True, "pending": False, "entries": []}
        result = WorldResolution()
        if len(self._background) >= MAX_BACKGROUND_LOOKUPS:
            allow_search = False
        task = asyncio.create_task(self.prepare(text, allow_search=allow_search, want_images=True, into=result))
        self._background.add(task)
        task.add_done_callback(self._background.discard)
        ready = asyncio.create_task(result.cards_ready.wait())
        try:
            await asyncio.wait({task, ready}, timeout=max(0.0, wait_seconds), return_when=asyncio.FIRST_COMPLETED)
        finally:
            ready.cancel()
        return {
            "disabled": False,
            "pending": not result.cards_ready.is_set(),
            "entries": result.summary(),
            "warnings": list(result.warnings),
        }

    # ------------------------------------------------------------------ 工作台

    def refresh_entry(self, entry: Dict[str, Any]) -> bool:
        """工作台「重新检索」：后台重查一条词条并补自动参考图；联网不可用或后台已满时返回 False。"""
        if not self._online() or len(self._background) >= MAX_BACKGROUND_LOOKUPS:
            return False
        self._image_tried.pop(entry["id"], None)
        task = asyncio.create_task(self._refresh(entry))
        self._background.add(task)
        task.add_done_callback(self._background.discard)
        return True

    async def _refresh(self, entry: Dict[str, Any]) -> None:
        result = WorldResolution()
        deadline = asyncio.get_running_loop().time() + self.general.world_knowledge_timeout_seconds
        query = " ".join(part for part in (entry["franchise"], entry["name"]) if part)[:60]
        mention = EntityMention(
            name=entry["name"], kind=entry["kind"], franchise=entry["franchise"], aliases=tuple(entry["aliases"]),
            query=query,
        )
        try:
            saved = await self._search_and_card([(mention, entry)], deadline, result, "")
            if self.general.world_knowledge_auto_images:
                for item in saved:
                    if self._wants_auto_image(item) and _left(deadline) >= 3:
                        self._image_tried[item["id"]] = self._now()
                        await self._attach_image(item, deadline, result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # 后台任务：只记日志，不影响工作台
            result.warn(f"重新检索出错（{type(exc).__name__}）")
        self.ctx.logger.info(
            "世界知识重新检索完成: entry_id=%s warnings=%s", entry["id"], len(result.warnings),
        )

    # ------------------------------------------------------------------ 画后

    async def verify(self, image_bytes: bytes, resolution: WorldResolution, *, task_id: str = "") -> Verdict:
        """只对照本次提供的参考资料；没有依据、调用失败或超时都按未校验的 PASS 处理。"""
        entries = [entry for entry in resolution.entries if entry["look"] or entry["draw_hint"]
                   or any(entry_id == entry["id"] for entry_id, _data in resolution.images)]
        if not entries:
            return Verdict("PASS", checked=False)
        numbers = resolution.image_numbers(1)
        prompt = VERIFY_PROMPT.format(checklist=render_checklist(entries, numbers))
        references = [data for _entry_id, data in resolution.images]
        loop = asyncio.get_running_loop()
        started = loop.time()
        try:
            messages = await asyncio.to_thread(_verify_messages, prompt, image_bytes, references)
            response = await self._generate(
                messages, timeout_seconds=VERIFY_TIMEOUT_SECONDS, max_tokens=VERIFY_MAX_TOKENS,
                model=self.general.world_knowledge_verify_model,
            )
            verdict = parse_verdict(response)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.ctx.logger.warning("世界知识校验失败，按通过处理: task_id=%s error_type=%s", task_id, type(exc).__name__)
            return Verdict("PASS", checked=False)
        self.ctx.logger.info(
            "世界知识校验完成: task_id=%s verdict=%s checked=%s issues=%s duration_ms=%s",
            task_id, verdict.level, verdict.checked, list(verdict.issues), round((loop.time() - started) * 1000),
        )
        return verdict

    # ------------------------------------------------------------------ LLM

    async def _generate(
        self, prompt: Any, *, timeout_seconds: float, max_tokens: int, model: Optional[str] = None,
    ) -> str:
        if timeout_seconds < 1:
            raise TimeoutError
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        async with asyncio.timeout_at(deadline):
            response = await self.ctx.llm.generate(
                prompt,
                model=model or self.general.world_knowledge_model,
                temperature=0.0,
                max_tokens=max_tokens,
                rpc_timeout_ms=int(timeout_seconds * 1000),
            )
        if not isinstance(response, dict) or not response.get("success", False):
            error = response.get("error") if isinstance(response, dict) else ""
            raise _LlmError(sanitize_provider_text(error or "模型调用失败")[:120])
        content = str(response.get("response") or response.get("content") or "").strip()
        truncated = _int(response.get("completion_tokens")) >= max_tokens
        if truncated:
            self.ctx.logger.warning(
                "世界知识模型输出达到上限: model=%s max_tokens=%s content_chars=%s",
                response.get("model_name") or model or self.general.world_knowledge_model, max_tokens, len(content),
            )
        if not content:  # 空回复不能当成「没有对象」「通过」之类的正常结论
            raise _LlmError("模型输出达到上限，没有给出回答" if truncated else "模型没有给出回答")
        return content


# ---------------------------------------------------------------------------- 工具函数


def _mention_order(text: str, entry: Dict[str, Any]) -> int:
    position = entry_mention(text, entry)
    return position if position >= 0 else 1 << 30


def _says_none(response: str) -> bool:
    return any(line.strip().strip("。.") == "无" for line in response.splitlines())


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _left(deadline: float) -> float:
    return deadline - asyncio.get_running_loop().time()


async def _maybe_await(value: Any) -> None:
    if asyncio.iscoroutine(value) or isinstance(value, asyncio.Future):
        await value


def _unwrap(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
        return payload["result"]
    return payload if isinstance(payload, dict) else {}


def _search_hits(payload: Any) -> List[Dict[str, str]]:
    hits = []
    for item in _unwrap(payload).get("results") or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        text = " ".join(str(item.get("summary") or item.get("snippet") or "").split())
        hits.append({
            "title": " ".join(str(item.get("title") or "").split())[:80],
            "url": url,
            "text": text[:MAX_MATERIAL_CHARS],
            "published_at": str(item.get("published_at") or "")[:32],
        })
    return hits[:5]


def _image_query(entry: Dict[str, Any]) -> str:
    parts = [entry["franchise"], entry["name"], _IMAGE_QUERY_WORDS.get(entry["kind"], "")]
    return " ".join(dict.fromkeys(part for part in parts if part))[:100]


def _source(hit: Dict[str, str]) -> Dict[str, str]:
    return {"title": hit["title"], "url": hit["url"], "published_at": hit.get("published_at", "")}


def _image_part(data: bytes, edge: int) -> Dict[str, Any]:
    return {
        "type": "image",
        "image_format": "jpeg",
        "image_base64": base64.b64encode(shrink_image_jpeg(data, edge)).decode("ascii"),
    }


def _image_messages(prompt: str, images: Sequence[bytes], edge: int) -> List[Dict[str, Any]]:
    return [{"role": "user", "content": [{"type": "text", "text": prompt}, *(_image_part(i, edge) for i in images)]}]


def _pick_messages(prompt: str, previews: Sequence[Tuple[SearchImage, bytes]]) -> List[Dict[str, Any]]:
    content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
    for number, (candidate, data) in enumerate(previews, 1):
        site = source_domain(candidate.page_url or candidate.url) or "未知站点"
        title = " ".join(candidate.text.split())[:60]
        content.append({"type": "text", "text": f"图 {number}：来源 {site}" + (f"；标题：{title}" if title else "")})
        content.append(_image_part(data, _PICK_EDGE))
    return [{"role": "user", "content": content}]


def _verify_messages(prompt: str, result: bytes, references: Sequence[bytes]) -> List[Dict[str, Any]]:
    content = [{"type": "text", "text": prompt}, _image_part(result, _RESULT_IMAGE_EDGE)]
    content.extend(_image_part(reference, _REFERENCE_EDGE) for reference in references)
    return [{"role": "user", "content": content}]
