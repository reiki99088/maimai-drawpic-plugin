"""世界知识服务：识别提示词里的现实对象 → 查词条库或联网检索 → 整理词条 → 找参考图；出图后对照校验。

所有失败都只降级为 warning：绘图照常进行，取消（CancelledError）照常向上传播。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple
import asyncio
import base64
import re

from ...domain.configuration.models import DrawpicConfig
from ...infrastructure.concurrency import run_owned_thread
from ...infrastructure.http import HttpProxySettings, sanitize_provider_text
from ...infrastructure.media.downloads import FAKE_IP_NETWORK
from ...infrastructure.media.images import shrink_image_jpeg
from ...infrastructure.media.world_sources import FoundImage, WorldImageFinder
from ...infrastructure.storage.world_knowledge import (
    WorldKnowledgeStore, WorldKnowledgeStoreError, entry_mention, is_expired, is_usable, kind_allows_auto_image,
    source_domain,
)
from .prompts import (
    CARD_PROMPT, EXTRACT_PROMPT, MAX_MATERIAL_CHARS, VERIFY_PROMPT, EntityMention, Verdict, compose_world_prompt,
    parse_cards, parse_entities, parse_verdict, render_checklist, render_materials,
)

SEARCH_TIMEOUT_SECONDS = 20
SEARCH_CONCURRENCY = 2
FETCH_TEXT_CHARS = 3000
THIN_MATERIAL_CHARS = 200
OFFLINE_BACKOFF_SECONDS = 600
IMAGE_RETRY_SECONDS = 6 * 3600
VERIFY_TIMEOUT_SECONDS = 90
MAX_BACKGROUND_LOOKUPS = 4
_RESULT_IMAGE_EDGE = 1280
_REFERENCE_EDGE = 768


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
                if entry["refs"] or not kind_allows_auto_image(entry["kind"]) or entry["status"] != "ok":
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

    async def _extract(self, text: str, deadline: float, result: WorldResolution) -> List[EntityMention]:
        prompt = EXTRACT_PROMPT.format(max_entities=self.general.world_knowledge_max_entities, text=text[:2000])
        try:
            response = await self._generate(prompt, timeout_seconds=min(30.0, _left(deadline)), max_tokens=400)
        except (_LlmError, TimeoutError) as exc:
            result.warn(f"识别现实对象失败：{str(exc) or '超时'}")
            return []
        return parse_entities(response, self.general.world_knowledge_max_entities)

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
            response = await self._generate(prompt, timeout_seconds=min(45.0, _left(deadline)), max_tokens=1500)
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

    async def _screen(self, image: FoundImage, entry: Dict[str, Any], deadline: float) -> bool:
        prompt = (
            f"这张图是否是「{entry['name']}」（{entry['franchise'] or entry['kind']}）本身的官方形象、标志或产品照片？"
            "如果是别的对象、截图拼图、文字为主的图或无关图片，回答 NO。只回复一行：结论：YES 或 结论：NO"
        )
        messages = await asyncio.to_thread(_image_messages, prompt, [image.data], _REFERENCE_EDGE)
        try:
            response = await self._generate(
                messages, timeout_seconds=min(45.0, _left(deadline)), max_tokens=20,
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
                messages, timeout_seconds=VERIFY_TIMEOUT_SECONDS, max_tokens=400,
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
        return str(response.get("response") or response.get("content") or "").strip()


# ---------------------------------------------------------------------------- 工具函数


def _mention_order(text: str, entry: Dict[str, Any]) -> int:
    position = entry_mention(text, entry)
    return position if position >= 0 else 1 << 30


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


def _verify_messages(prompt: str, result: bytes, references: Sequence[bytes]) -> List[Dict[str, Any]]:
    content = [{"type": "text", "text": prompt}, _image_part(result, _RESULT_IMAGE_EDGE)]
    content.extend(_image_part(reference, _REFERENCE_EDGE) for reference in references)
    return [{"role": "user", "content": content}]
