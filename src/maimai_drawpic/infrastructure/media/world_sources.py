"""世界知识参考图来源：Riot Data Dragon → MediaWiki pageimages（固定图源）；网搜候选的过滤与缩略图下载。

所有网络访问都经 downloads.py 的逐跳公网校验；本模块只决定「去哪找图」和「哪些图不要」，
下载结果统一规范成 JPEG。任何来源失败都只是少一个候选，不抛到绘图链路。
不再读任意网页的 og:image：准确率低，还会访问检索结果里的任意域名。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote, unquote, urlencode, urlsplit
import asyncio
import json

from ..http import HttpProxySettings, sanitize_provider_url
from ..storage.atomic import write_json_atomically
from ..storage.world_knowledge import normalize_key
from .downloads import PublicFetchError, download_image, fetch_public_text
from .images import normalize_reference_image, shrink_image_jpeg

USER_AGENT = (
    "MaiMaiDrawpic/2 (world-knowledge reference lookup; "
    "+https://github.com/WhiteCloudOL/maimai-drawpic-plugin)"
)
_UNTRUSTED_BASE = "https://reference.invalid"
_DDRAGON = "https://ddragon.leagueoflegends.com"
_DDRAGON_CACHE_DAYS = 7
_LOL_FRANCHISE_KEYS = {normalize_key(name) for name in ("英雄联盟", "League of Legends", "LoL")}
_REJECT_SUFFIXES = (".svg", ".gif", ".ico")
_ALWAYS_REJECT = (
    "favicon", "apple-touch-icon", "placeholder", "noimage", "no_image", "no-image",
    "default_image", "default-image", "defaultimage",
    "site-community-image", "wiki-wordmark", "wordmark", "sprite", "blank.",
)
_LOGO_WORDS = ("logo", "icon")
_LOGO_KINDS = {"brand", "esports_team"}
MAX_DOWNLOAD_ATTEMPTS = 3
# 这些站点的 pageimages 不可用或给旧图：biligame、Liquipedia 没装 PageImages；
# 英雄联盟 Fandom 返回多年前的选手照和旧队标，宁可不要。
_STALE_PAGEIMAGE_HOSTS = {"leagueoflegends.fandom.com", "lol.fandom.com"}
# 网搜候选里不收的图床：转存图多、来源不明，Pinterest 还常常要登录。
_BLOCKED_SEARCH_HOSTS = ("pinimg.com", "pinterest.", "fbsbx.com")
_MIN_SHORT_EDGE = 256
_MAX_ASPECT = 3.0
PREVIEW_EDGE = 384


@dataclass(frozen=True)
class ImageCandidate:
    url: str
    page_url: str
    source: str


@dataclass(frozen=True)
class FoundImage:
    data: bytes
    size: Tuple[int, int]
    page_url: str
    source: str


def acceptable_image_url(url: str, kind: str) -> bool:
    """丢掉矢量图、动图、站点默认分享图；logo 类只给品牌和战队。"""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return False
    path = unquote(parts.path).casefold()
    # MediaWiki 缩略图地址形如 .../File.svg/1024px-File.svg.png，原始扩展名在中间。
    if any(suffix in path for suffix in _REJECT_SUFFIXES):
        return False
    if any(word in path for word in _ALWAYS_REJECT):
        return False
    return kind in _LOGO_KINDS or not any(word in path for word in _LOGO_WORDS)


def mediawiki_api(page_url: str) -> Optional[Tuple[str, str]]:
    """识别常见 MediaWiki 站点页面，返回 (api.php 地址, 页面标题)。"""
    try:
        parts = urlsplit(page_url)
    except ValueError:
        return None
    host = (parts.hostname or "").casefold()
    segments = [unquote(segment) for segment in parts.path.split("/") if segment]
    if parts.scheme != "https" or not host or not segments:
        return None
    title = ""
    api = ""
    if host.endswith(".wikipedia.org") and len(segments) >= 2 and segments[0] == "wiki":
        api, title = f"https://{host}/w/api.php", "/".join(segments[1:])
    elif host.endswith(".fandom.com") and host not in _STALE_PAGEIMAGE_HOSTS:
        if len(segments) >= 2 and segments[0] == "wiki":
            api, title = f"https://{host}/api.php", "/".join(segments[1:])
        elif len(segments) >= 3 and segments[1] == "wiki":
            api, title = f"https://{host}/{quote(segments[0])}/api.php", "/".join(segments[2:])
    elif host.endswith("moegirl.org.cn") and segments[0] not in {"index.php", "api.php"}:
        api, title = "https://zh.moegirl.org.cn/api.php", "/".join(segments)
    title = title.replace("_", " ").strip()
    if not api or not title or title.casefold().startswith(("special:", "file:", "category:", "特殊:", "文件:")):
        return None
    return api, title


def _host_blocked(url: str) -> bool:
    host = (urlsplit(url).hostname or "").casefold()
    return any(blocked in host for blocked in _BLOCKED_SEARCH_HOSTS)


def search_candidates(images: Sequence[Any], kind: str, limit: int) -> List[Any]:
    """网搜结果的硬过滤：地址与站点、已知尺寸的短边和长宽比、去重，按原顺序取前 limit 张。"""
    result: List[Any] = []
    seen = set()
    for image in images:
        if image.url in seen or not acceptable_image_url(image.url, kind) or _host_blocked(image.url):
            continue
        if image.width and image.height:
            short, long = sorted((image.width, image.height))
            if short < _MIN_SHORT_EDGE or long > _MAX_ASPECT * short:
                continue
        seen.add(image.url)
        result.append(image)
        if len(result) >= limit:
            break
    return result


FetchText = Callable[..., Awaitable[Tuple[str, str]]]
Download = Callable[..., Awaitable[bytes]]


class WorldImageFinder:
    """按来源顺序找一张能用的参考图；网络函数可注入，便于离线测试。"""

    def __init__(
        self,
        *,
        proxy_settings: HttpProxySettings,
        cache_dir: Path,
        timeout_seconds: float = 20,
        extra_allowed_networks: tuple = (),
        fetch_text: Optional[FetchText] = None,
        download: Optional[Download] = None,
    ) -> None:
        self.proxy_settings = proxy_settings
        self.cache_path = Path(cache_dir) / "ddragon_champions.json"
        self.timeout_seconds = timeout_seconds
        self.extra_allowed_networks = extra_allowed_networks
        self._fetch_text = fetch_text or fetch_public_text
        self._download = download or download_image
        self._ddragon_lock = asyncio.Lock()

    async def _text(self, url: str) -> str:
        text, _final = await self._fetch_text(
            url,
            proxy_settings=self.proxy_settings,
            timeout_seconds=self.timeout_seconds,
            headers={"User-Agent": USER_AGENT},
            extra_allowed_networks=self.extra_allowed_networks,
        )
        return text

    async def _json(self, url: str) -> Any:
        try:
            return json.loads(await self._text(url))
        except ValueError:
            raise PublicFetchError("资料抓取失败：返回的不是 JSON") from None

    # ------------------------------------------------------------------ 候选

    async def candidates(
        self, *, name: str, aliases: Iterable[str], kind: str, franchise: str, pages: Iterable[str],
    ) -> List[ImageCandidate]:
        found: List[ImageCandidate] = []
        if kind == "game_character" and self._is_lol(franchise, name):
            found.extend(await self._ddragon_candidates([name, *aliases]))
        pages = list(dict.fromkeys(page for page in pages if page))
        wiki_pages = [(page, api) for page in pages if (api := mediawiki_api(page))]
        for page, (api, title) in wiki_pages[:2]:
            found.extend(await self._mediawiki_candidates(api, title, page))
        unique: Dict[str, ImageCandidate] = {}
        for candidate in found:
            if acceptable_image_url(candidate.url, kind):
                unique.setdefault(candidate.url, candidate)
        return list(unique.values())

    @staticmethod
    def _is_lol(franchise: str, name: str) -> bool:
        key = normalize_key(franchise)
        return key in _LOL_FRANCHISE_KEYS or "英雄联盟" in key or "leagueoflegends" in key

    async def _mediawiki_candidates(self, api: str, title: str, page: str) -> List[ImageCandidate]:
        query = urlencode({
            "action": "query", "format": "json", "formatversion": "2", "redirects": "1",
            "prop": "pageimages", "piprop": "original|thumbnail", "pithumbsize": "1024", "titles": title,
        })
        try:
            payload = await self._json(f"{api}?{query}")
        except PublicFetchError:
            return []
        pages = payload.get("query", {}).get("pages") if isinstance(payload, dict) else None
        result = []
        for item in pages if isinstance(pages, list) else []:
            if not isinstance(item, dict):
                continue
            image = item.get("thumbnail") or item.get("original")
            source = image.get("source") if isinstance(image, dict) else None
            if isinstance(source, str) and source.startswith("https://"):
                result.append(ImageCandidate(source, page, "mediawiki"))
        return result

    async def _ddragon_candidates(self, names: List[str]) -> List[ImageCandidate]:
        try:
            champions = await self._ddragon_champions()
        except PublicFetchError:
            return []
        keys = {normalize_key(name) for name in names if normalize_key(name)}
        for champion in champions:
            if keys & {normalize_key(name) for name in champion.get("names", [])}:
                champion_id = quote(str(champion["id"]))
                return [ImageCandidate(
                    f"{_DDRAGON}/cdn/img/champion/loading/{champion_id}_0.jpg",
                    f"{_DDRAGON}/cdn/img/champion/loading/{champion_id}_0.jpg",
                    "ddragon",
                )]
        return []

    async def _ddragon_champions(self) -> List[Dict[str, Any]]:
        async with self._ddragon_lock:
            cached = await asyncio.to_thread(self._read_ddragon_cache)
            if cached is not None:
                return cached
            versions = await self._json(f"{_DDRAGON}/api/versions.json")
            if not isinstance(versions, list) or not versions or not isinstance(versions[0], str):
                raise PublicFetchError("资料抓取失败：Data Dragon 版本列表异常")
            version = quote(versions[0])
            merged: Dict[str, set] = {}
            for locale in ("zh_CN", "en_US"):
                payload = await self._json(f"{_DDRAGON}/cdn/{version}/data/{locale}/champion.json")
                data = payload.get("data") if isinstance(payload, dict) else None
                for champion in (data or {}).values():
                    if isinstance(champion, dict) and isinstance(champion.get("id"), str):
                        names = merged.setdefault(champion["id"], {champion["id"]})
                        names.update(str(champion.get(key) or "") for key in ("name", "title"))
            champions = [{"id": key, "names": sorted(name for name in names if name)} for key, names in merged.items()]
            if not champions:
                raise PublicFetchError("资料抓取失败：Data Dragon 英雄表为空")
            await asyncio.to_thread(
                write_json_atomically, self.cache_path,
                {"fetched_at": datetime.now(timezone.utc).isoformat(), "version": versions[0], "champions": champions},
            )
            return champions

    def _read_ddragon_cache(self) -> Optional[List[Dict[str, Any]]]:
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
            fetched = datetime.fromisoformat(payload["fetched_at"])
            champions = payload["champions"]
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if datetime.now(timezone.utc) - fetched > timedelta(days=_DDRAGON_CACHE_DAYS) or not isinstance(champions, list):
            return None
        return champions

    # ------------------------------------------------------------------ 下载

    async def fetch(self, candidate: ImageCandidate) -> FoundImage:
        """下载并规范化一张候选图；失败抛 PublicFetchError（不含生成相关文案）。"""
        try:
            raw = await self._download(
                candidate.url,
                base_url=_UNTRUSTED_BASE,
                proxy_settings=self.proxy_settings,
                timeout_seconds=max(1, int(self.timeout_seconds)),
                extra_allowed_networks=self.extra_allowed_networks,
                headers={"User-Agent": USER_AGENT},
            )
            data, size = await asyncio.to_thread(normalize_reference_image, raw)
        except asyncio.CancelledError:
            raise
        except ValueError as exc:
            raise PublicFetchError(f"参考图不可用：{exc}") from None
        except Exception as exc:  # 下载器的异常文案面向生成结果，这里统一改写
            raise PublicFetchError(
                f"参考图下载失败（{type(exc).__name__}） url={sanitize_provider_url(candidate.url)}"
            ) from None
        return FoundImage(data=data, size=size, page_url=candidate.page_url, source=candidate.source)

    async def preview(self, url: str, *, timeout_seconds: float = 10) -> bytes:
        """下载一张网搜候选的缩略图给模型挑选；失败抛 PublicFetchError。"""
        try:
            raw = await self._download(
                url,
                base_url=_UNTRUSTED_BASE,
                proxy_settings=self.proxy_settings,
                timeout_seconds=max(1, int(timeout_seconds)),
                extra_allowed_networks=self.extra_allowed_networks,
                headers={"User-Agent": USER_AGENT},
            )
            return await asyncio.to_thread(shrink_image_jpeg, raw, PREVIEW_EDGE)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise PublicFetchError(
                f"候选图下载失败（{type(exc).__name__}） url={sanitize_provider_url(url)}"
            ) from None

    async def find(
        self, *, name: str, aliases: Iterable[str], kind: str, franchise: str, pages: Iterable[str],
        accept: Optional[Callable[[FoundImage], Awaitable[bool]]] = None,
    ) -> Tuple[Optional[FoundImage], List[str]]:
        """依次尝试候选，返回第一张通过的图和失败原因（已脱敏）；accept 用于可选的模型筛图。"""
        reasons: List[str] = []
        candidates = await self.candidates(name=name, aliases=aliases, kind=kind, franchise=franchise, pages=pages)
        for candidate in candidates[:MAX_DOWNLOAD_ATTEMPTS]:
            try:
                image = await self.fetch(candidate)
            except PublicFetchError as exc:
                reasons.append(str(exc))
                continue
            if accept is not None and not await accept(image):
                reasons.append(f"筛图未通过 source={candidate.source}")
                continue
            return image, reasons
        if not candidates:
            reasons.append("没有找到候选参考图")
        return None, reasons
