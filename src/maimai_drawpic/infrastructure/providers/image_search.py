"""世界知识网搜取图的搜索服务适配器：OpenAI Responses web_search、Brave 图片搜索、Tavily。

只负责鉴权、传输和把响应规范成 SearchImage；不下载图片、不判断图对不对（由世界知识服务挑选）。
错误统一抛 ImageSearchError，文案只含服务名、HTTP 状态和业务错误码，不含密钥、检索词或签名链接。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import urlsplit
import asyncio
import re

import aiohttp

from ..http import HttpProxySettings, read_response_json, sanitize_provider_text

PROVIDER_NAMES = ("openai", "brave", "tavily")
PROVIDER_LABELS = {"openai": "OpenAI", "brave": "Brave", "tavily": "Tavily"}
_MAX_RESPONSE_BYTES = 4_000_000
_BRAVE_URL = "https://api.search.brave.com/res/v1/images/search"
_TAVILY_URL = "https://api.tavily.com/search"
_CJK = re.compile(r"[぀-ヿ㐀-鿿]")


@dataclass(frozen=True)
class SearchImage:
    url: str
    page_url: str
    thumbnail_url: str
    width: Optional[int]
    height: Optional[int]
    text: str
    provider: str


class ImageSearchError(RuntimeError):
    """搜索服务调用失败。kind：auth / quota / server / request / network / parse。"""

    def __init__(self, provider: str, kind: str, message: str) -> None:
        super().__init__(message)
        self.provider = provider
        self.kind = kind


def _http_url(value: Any) -> str:
    text = str(value or "").strip()
    try:
        parts = urlsplit(text)
    except ValueError:
        return ""
    return text if parts.scheme in {"http", "https"} and parts.hostname else ""


def _size(value: Any) -> Optional[int]:
    return value if type(value) is int and value > 0 else None


def _kind_for_status(status: int) -> str:
    if status in {401, 403}:
        return "auth"
    if status in {402, 429}:
        return "quota"
    if status >= 500:
        return "server"
    return "request"


def _error_code(payload: Any) -> str:
    if not isinstance(payload, Mapping):
        return ""
    error = payload.get("error")
    if isinstance(error, Mapping):
        return str(error.get("code") or error.get("type") or "")
    if isinstance(payload.get("detail"), Mapping):
        return str(payload["detail"].get("error") or "")[:60]
    return ""


class _SearchClient:
    name = ""

    def __init__(self, *, api_key: str, proxy_settings: HttpProxySettings) -> None:
        self.api_key = api_key
        self.proxy_settings = proxy_settings

    @property
    def label(self) -> str:
        return PROVIDER_LABELS[self.name]

    async def _request(
        self, method: str, url: str, *, headers: Dict[str, str], timeout_seconds: float,
        params: Optional[Dict[str, Any]] = None, body: Optional[Dict[str, Any]] = None,
    ) -> Any:
        timeout = aiohttp.ClientTimeout(total=max(1.0, timeout_seconds))
        try:
            async with aiohttp.ClientSession(timeout=timeout, **self.proxy_settings.aiohttp_session_kwargs()) as session:
                async with session.request(
                    method, url, headers=headers, params=params, json=body, allow_redirects=False,
                    **self.proxy_settings.aiohttp_request_kwargs(),
                ) as response:
                    try:
                        payload = await read_response_json(response, max_bytes=_MAX_RESPONSE_BYTES)
                    except RuntimeError:
                        if response.status != 200:
                            raise ImageSearchError(
                                self.name, _kind_for_status(response.status), f"{self.label} 搜图失败：HTTP {response.status}",
                            ) from None
                        raise ImageSearchError(self.name, "parse", f"{self.label} 搜图返回了无效的 JSON") from None
                    if response.status != 200:
                        code = sanitize_provider_text(_error_code(payload), self.api_key, max_chars=60)
                        raise ImageSearchError(
                            self.name, _kind_for_status(response.status),
                            f"{self.label} 搜图失败：HTTP {response.status}" + (f" {code}" if code else ""),
                        )
                    return payload
        except asyncio.CancelledError:
            raise
        except ImageSearchError:
            raise
        except TimeoutError:
            raise ImageSearchError(self.name, "network", f"{self.label} 搜图超时") from None
        except (aiohttp.ClientError, OSError, ValueError) as exc:
            raise ImageSearchError(self.name, "network", f"{self.label} 搜图连接失败（{type(exc).__name__}）") from None

    async def search(self, query: str, *, count: int, timeout_seconds: float) -> List[SearchImage]:
        raise NotImplementedError


class BraveImageSearch(_SearchClient):
    name = "brave"

    async def search(self, query: str, *, count: int, timeout_seconds: float) -> List[SearchImage]:
        params = {
            "q": query, "count": max(1, min(count, 50)), "safesearch": "strict", "country": "ALL",
            "search_lang": "zh-hans" if _CJK.search(query) else "en",
        }
        payload = await self._request(
            "GET", _BRAVE_URL, params=params, timeout_seconds=timeout_seconds,
            headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"},
        )
        results = payload.get("results") if isinstance(payload, Mapping) else None
        images: List[SearchImage] = []
        for item in results if isinstance(results, list) else []:
            if not isinstance(item, Mapping):
                continue
            properties = item.get("properties") if isinstance(item.get("properties"), Mapping) else {}
            thumbnail = item.get("thumbnail") if isinstance(item.get("thumbnail"), Mapping) else {}
            url = _http_url(properties.get("url"))
            if url:
                images.append(SearchImage(
                    url=url, page_url=_http_url(item.get("url")), thumbnail_url=_http_url(thumbnail.get("src")),
                    width=_size(properties.get("width")), height=_size(properties.get("height")),
                    text=" ".join(str(item.get("title") or "").split())[:120], provider=self.name,
                ))
        return images


class TavilyImageSearch(_SearchClient):
    name = "tavily"

    async def search(self, query: str, *, count: int, timeout_seconds: float) -> List[SearchImage]:
        payload = await self._request(
            "POST", _TAVILY_URL, timeout_seconds=timeout_seconds,
            headers={"Authorization": f"Bearer {self.api_key}"},
            body={
                "query": query, "search_depth": "basic", "max_results": 5,
                "include_images": True, "include_image_descriptions": True,
            },
        )
        if not isinstance(payload, Mapping):
            return []
        groups = [("", payload.get("images"))]
        results = payload.get("results")
        for result in results if isinstance(results, list) else []:
            if isinstance(result, Mapping):
                groups.append((_http_url(result.get("url")), result.get("images")))
        images: Dict[str, SearchImage] = {}
        for page_url, items in groups:
            for item in items if isinstance(items, list) else []:
                raw = item.get("url") if isinstance(item, Mapping) else item
                description = item.get("description") if isinstance(item, Mapping) else ""
                url = _http_url(raw)
                if url and url not in images:
                    images[url] = SearchImage(
                        url=url, page_url=page_url, thumbnail_url="", width=None, height=None,
                        text=" ".join(str(description or "").split())[:160], provider=self.name,
                    )
        return list(images.values())[:count]


class OpenAIImageSearch(_SearchClient):
    """Responses API 的 web_search 工具；图片结果在 web_search_call.results 里，与回答分开返回。"""

    name = "openai"

    def __init__(self, *, api_key: str, proxy_settings: HttpProxySettings, base_url: str, model: str) -> None:
        super().__init__(api_key=api_key, proxy_settings=proxy_settings)
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def search(self, query: str, *, count: int, timeout_seconds: float) -> List[SearchImage]:
        payload = await self._request(
            "POST", f"{self.base_url}/responses", timeout_seconds=timeout_seconds,
            headers={"Authorization": f"Bearer {self.api_key}"},
            body={
                "model": self.model,
                "input": f"Search the web for official reference images of: {query}. After searching, reply only: done",
                "tools": [{
                    "type": "web_search", "search_content_types": ["image", "text"],
                    "image_settings": {"max_results": max(1, min(count, 20)), "caption": True},
                    "search_context_size": "low",
                }],
                "tool_choice": "required",
                "include": ["web_search_call.results"],
                "max_output_tokens": 400,
                "store": False,
            },
        )
        output = payload.get("output") if isinstance(payload, Mapping) else None
        images: Dict[str, SearchImage] = {}
        for call in output if isinstance(output, list) else []:
            if not isinstance(call, Mapping) or call.get("type") != "web_search_call":
                continue
            results = call.get("results")
            for item in results if isinstance(results, list) else []:
                if not isinstance(item, Mapping) or item.get("type") != "image_result":
                    continue
                url = _http_url(item.get("image_url"))
                if url and url not in images:
                    images[url] = SearchImage(
                        url=url, page_url=_http_url(item.get("source_website_url")),
                        thumbnail_url=_http_url(item.get("thumbnail_url")), width=None, height=None,
                        text=" ".join(str(item.get("caption") or "").split())[:160], provider=self.name,
                    )
        return list(images.values())[:count]


def build_image_search_clients(config: Any, proxy_settings: HttpProxySettings) -> Dict[str, _SearchClient]:
    """按 [world_search] 配置创建填了密钥的搜索服务；没填密钥的服务不参与。"""
    clients: Dict[str, _SearchClient] = {}
    if config.openai_api_key:
        clients["openai"] = OpenAIImageSearch(
            api_key=config.openai_api_key, proxy_settings=proxy_settings,
            base_url=config.openai_base_url, model=config.openai_model,
        )
    if config.brave_api_key:
        clients["brave"] = BraveImageSearch(api_key=config.brave_api_key, proxy_settings=proxy_settings)
    if config.tavily_api_key:
        clients["tavily"] = TavilyImageSearch(api_key=config.tavily_api_key, proxy_settings=proxy_settings)
    return clients
