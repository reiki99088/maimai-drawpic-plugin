"""公开资料抓取（世界知识用）的地址校验回归，只访问本机测试服务。"""

from aiohttp import web
from typing import List
from yarl import URL
import asyncio
import pytest

from test_review_regressions import module, serve


def _proxy_to(base: str):
    proxy_type = module("infrastructure.http").HttpProxySettings
    return proxy_type(enabled=True, use_system_proxy=False, host="127.0.0.1", port=int(URL(base).port))


def test_text_fetch_follows_checked_redirects_and_decodes_charset() -> None:
    async def run() -> None:
        downloads = module("infrastructure.media.downloads")
        hits: List[dict] = []

        async def handler(request):
            hits.append({"target": request.raw_path, "ua": request.headers.get("User-Agent")})
            if len(hits) == 1:
                raise web.HTTPFound("http://wiki.invalid/page?token=secret")
            return web.Response(body="芙宁娜".encode("gbk"), headers={"Content-Type": "text/html; charset=GBK"})

        runner, base = await serve(handler)
        try:
            text, final = await downloads.fetch_public_text(
                "http://search.invalid/start", proxy_settings=_proxy_to(base), timeout_seconds=3,
                headers={"User-Agent": "fixture-agent"},
            )
            assert text == "芙宁娜"
            assert final == "http://wiki.invalid/page"
            assert [hit["target"] for hit in hits] == [
                "http://search.invalid/start", "http://wiki.invalid/page?token=secret",
            ]
            assert all(hit["ua"] == "fixture-agent" for hit in hits)
        finally:
            await runner.cleanup()

    asyncio.run(run())


@pytest.mark.parametrize("url, reason", [
    ("http://127.0.0.1/private", "非公网"),
    ("http://169.254.169.254/latest", "非公网"),
    ("http://localhost/x", "非公网"),
    ("http://user:pw@example.invalid/x", "URL"),
    ("file:///etc/passwd", "URL"),
])
def test_text_fetch_refuses_private_or_credentialed_targets(url: str, reason: str) -> None:
    async def run() -> None:
        downloads = module("infrastructure.media.downloads")
        proxy = module("infrastructure.http").HttpProxySettings(
            enabled=True, use_system_proxy=False, host="127.0.0.1", port=9,
        )
        with pytest.raises(downloads.PublicFetchError, match=reason):
            await downloads.fetch_public_text(url, proxy_settings=proxy, timeout_seconds=3)

    asyncio.run(run())


def test_text_fetch_rechecks_redirect_into_private_network() -> None:
    async def run() -> None:
        downloads = module("infrastructure.media.downloads")
        hits: List[str] = []

        async def handler(request):
            hits.append(request.raw_path)
            raise web.HTTPFound("http://10.0.0.8/admin")

        runner, base = await serve(handler)
        try:
            with pytest.raises(downloads.PublicFetchError, match="非公网"):
                await downloads.fetch_public_text(
                    "http://public.invalid/start", proxy_settings=_proxy_to(base), timeout_seconds=3,
                )
            assert hits == ["http://public.invalid/start"]
        finally:
            await runner.cleanup()

    asyncio.run(run())


def test_text_fetch_bounds_response_size_and_hides_query_in_errors() -> None:
    async def run() -> None:
        downloads = module("infrastructure.media.downloads")

        async def handler(request):
            if request.path.endswith("missing"):
                return web.Response(status=404)
            return web.Response(body=b"x" * 2048)

        runner, base = await serve(handler)
        try:
            with pytest.raises(downloads.PublicFetchError, match="大小限制"):
                await downloads.fetch_public_text(
                    "http://big.invalid/page", proxy_settings=_proxy_to(base), timeout_seconds=3, max_bytes=1024,
                )
            with pytest.raises(downloads.PublicFetchError) as caught:
                await downloads.fetch_public_text(
                    "http://big.invalid/missing?sig=secret", proxy_settings=_proxy_to(base), timeout_seconds=3,
                )
            assert "HTTP 404" in str(caught.value) and "secret" not in str(caught.value)
        finally:
            await runner.cleanup()

    asyncio.run(run())
