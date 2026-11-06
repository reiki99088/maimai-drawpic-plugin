"""世界知识网搜取图：三家搜图适配器、服务轮换与冷却、候选挑图；全部离线模拟，不调用付费服务。"""

from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import Mock
import asyncio
import json

from aiohttp import web
import pytest

from test_review_regressions import module
from test_world_knowledge_service import CARD, EXTRACT, FakeWeb, jpeg
from test_workspace import DrawpicConfig

search_module = module("infrastructure.providers.image_search")
pool_module = module("application.knowledge.search_pool")
service_module = module("application.knowledge.service")
store_module = module("infrastructure.storage.world_knowledge")
sources = module("infrastructure.media.world_sources")
downloads = module("infrastructure.media.downloads")
SearchImage = search_module.SearchImage
ImageSearchError = search_module.ImageSearchError
PROXY = module("infrastructure.http").HttpProxySettings.disabled()


def image(url: str, provider: str = "brave", **kwargs) -> SearchImage:
    values = {"page_url": "", "thumbnail_url": "", "width": None, "height": None, "text": ""}
    values.update(kwargs)
    return SearchImage(url=url, provider=provider, **values)


# ---------------------------------------------------------------------------- 适配器


def test_brave_request_and_parsing(monkeypatch) -> None:
    client = search_module.BraveImageSearch(api_key="brave-secret", proxy_settings=PROXY)
    seen: Dict[str, Any] = {}

    async def request(method, url, **kwargs):
        seen.update(method=method, url=url, **kwargs)
        return {"results": [
            {"title": " 芙宁娜  立绘 ", "url": "https://wiki.invalid/furina",
             "thumbnail": {"src": "https://imgs.search.brave.com/t"},
             "properties": {"url": "https://img.invalid/furina.png", "width": 1200, "height": 900}},
            {"title": "坏的", "properties": {"url": "javascript:alert(1)"}},
            "not-a-dict",
        ]}

    monkeypatch.setattr(client, "_request", request)
    found = asyncio.run(client.search("原神 芙宁娜 角色 立绘", count=99, timeout_seconds=5))
    assert seen["method"] == "GET" and seen["headers"]["X-Subscription-Token"] == "brave-secret"
    assert seen["params"]["count"] == 50 and seen["params"]["search_lang"] == "zh-hans"
    assert seen["params"]["safesearch"] == "strict"
    assert found == [SearchImage(
        url="https://img.invalid/furina.png", page_url="https://wiki.invalid/furina",
        thumbnail_url="https://imgs.search.brave.com/t", width=1200, height=900, text="芙宁娜 立绘", provider="brave",
    )]
    english = {}

    async def capture(method, url, **kwargs):
        english.update(kwargs)
        return {}

    monkeypatch.setattr(client, "_request", capture)
    assert asyncio.run(client.search("T1 logo", count=4, timeout_seconds=5)) == []
    assert english["params"]["search_lang"] == "en"


def test_tavily_merges_top_level_and_result_images(monkeypatch) -> None:
    client = search_module.TavilyImageSearch(api_key="tvly-secret", proxy_settings=PROXY)
    seen: Dict[str, Any] = {}

    async def request(method, url, **kwargs):
        seen.update(method=method, **kwargs)
        return {
            "images": [{"url": "https://img.invalid/a.jpg", "description": "A"}, "https://img.invalid/b.jpg"],
            "results": [{"url": "https://page.invalid/1", "images": [
                {"url": "https://img.invalid/a.jpg", "description": "dup"}, {"url": "https://img.invalid/c.jpg"},
            ]}],
        }

    monkeypatch.setattr(client, "_request", request)
    found = asyncio.run(client.search("BLG 队标", count=3, timeout_seconds=5))
    assert seen["method"] == "POST" and seen["headers"]["Authorization"] == "Bearer tvly-secret"
    assert seen["body"]["include_images"] is True and seen["body"]["search_depth"] == "basic"
    assert [(item.url, item.page_url, item.text) for item in found] == [
        ("https://img.invalid/a.jpg", "", "A"), ("https://img.invalid/b.jpg", "", ""),
        ("https://img.invalid/c.jpg", "https://page.invalid/1", ""),
    ]


def test_openai_web_search_requests_image_results(monkeypatch) -> None:
    client = search_module.OpenAIImageSearch(
        api_key="sk-secret", proxy_settings=PROXY, base_url="https://relay.invalid/v1/", model="gpt-test",
    )
    seen: Dict[str, Any] = {}

    async def request(method, url, **kwargs):
        seen.update(url=url, **kwargs)
        return {"output": [
            {"type": "reasoning"},
            {"type": "web_search_call", "results": [
                {"type": "image_result", "image_url": "https://img.invalid/su7.jpg",
                 "thumbnail_url": "https://thumb.invalid/su7.jpg", "source_website_url": "https://mi.invalid/su7",
                 "caption": "小米 SU7"},
                {"type": "text_result", "url": "https://mi.invalid/news"},
            ]},
            {"type": "message", "content": [{"type": "output_text", "text": "done"}]},
        ]}

    monkeypatch.setattr(client, "_request", request)
    found = asyncio.run(client.search("小米 SU7", count=30, timeout_seconds=5))
    assert seen["url"] == "https://relay.invalid/v1/responses"
    body = seen["body"]
    assert body["model"] == "gpt-test" and body["include"] == ["web_search_call.results"]
    tool = body["tools"][0]
    assert tool["type"] == "web_search" and "image" in tool["search_content_types"]
    assert tool["image_settings"]["max_results"] == 20 and body["store"] is False
    assert [(item.url, item.thumbnail_url, item.page_url, item.text) for item in found] == [
        ("https://img.invalid/su7.jpg", "https://thumb.invalid/su7.jpg", "https://mi.invalid/su7", "小米 SU7"),
    ]


def test_request_errors_are_classified_without_secrets(tmp_path) -> None:
    async def run() -> None:
        async def quota(request):
            return web.json_response({"error": {"code": "RATE_LIMITED", "detail": "key brave-secret"}}, status=429)

        async def denied(request):
            return web.json_response({"error": {"code": "brave-secret"}}, status=401)

        async def broken(request):
            return web.Response(text="<html>", content_type="text/html")

        app = web.Application()
        app.router.add_get("/quota", quota)
        app.router.add_get("/denied", denied)
        app.router.add_get("/broken", broken)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        client = search_module.BraveImageSearch(api_key="brave-secret", proxy_settings=PROXY)
        try:
            results = {}
            for path in ("quota", "denied", "broken"):
                with pytest.raises(ImageSearchError) as caught:
                    await client._request("GET", f"http://127.0.0.1:{port}/{path}", headers={}, timeout_seconds=5)
                results[path] = caught.value
        finally:
            await runner.cleanup()
        assert results["quota"].kind == "quota" and "HTTP 429 RATE_LIMITED" in str(results["quota"])
        assert results["denied"].kind == "auth" and "brave-secret" not in str(results["denied"])
        assert results["broken"].kind == "parse"
        assert all(error.provider == "brave" for error in results.values())

    asyncio.run(run())


def test_only_keyed_providers_are_built() -> None:
    config = DrawpicConfig().world_search
    assert search_module.build_image_search_clients(config, PROXY) == {}
    config.brave_api_key = "b"
    config.openai_api_key = "o"
    clients = search_module.build_image_search_clients(config, PROXY)
    assert set(clients) == {"openai", "brave"}
    assert clients["openai"].base_url == "https://api.openai.com/v1" and clients["openai"].model == config.openai_model


def test_config_order_validation_and_redaction() -> None:
    world_search = module("domain.configuration.world_search")
    validated = world_search.WorldSearchConfig.model_validate({"order": "Tavily，brave, tavily", "openai_base_url": "https://x.invalid/v1/"})
    assert validated.order == ["tavily", "brave"] and validated.openai_base_url == "https://x.invalid/v1"
    with pytest.raises(ValueError):
        world_search.WorldSearchConfig.model_validate({"order": ["bing"]})
    redactor = module("infrastructure.observability.redaction").SecretRedactor()
    redactor.add_config({"world_search": {"brave_api_key": "brave-secret-value", "order": ["brave"]}})
    assert "brave-secret-value" not in redactor.redact("token=brave-secret-value")


# ---------------------------------------------------------------------------- 轮换


class FakeClient:
    label_names = {"openai": "OpenAI", "brave": "Brave", "tavily": "Tavily"}

    def __init__(self, name: str, results: Optional[List[SearchImage]] = None, error: str = "", api_key: str = "k") -> None:
        self.name, self.api_key, self.error = name, api_key, error
        self.results = results if results is not None else []
        self.queries: List[str] = []

    @property
    def label(self) -> str:
        return self.label_names[self.name]

    async def search(self, query: str, *, count: int, timeout_seconds: float) -> List[SearchImage]:
        self.queries.append(query)
        if self.error:
            raise ImageSearchError(self.name, self.error, f"{self.label} 搜图失败：HTTP 429")
        return list(self.results)


def test_pool_order_round_robin_and_cooldown() -> None:
    now = [0.0]
    pool = pool_module.ImageSearchPool(lambda: now[0])
    clients = {name: FakeClient(name) for name in ("openai", "brave", "tavily")}
    pool.configure(clients, ["brave", "openai", "tavily"], "ordered")
    assert [c.name for c in pool.sequence()] == ["brave", "openai"]
    assert [c.name for c in pool.sequence()] == ["brave", "openai"]

    pool.configure(clients, ["openai", "brave", "tavily"], "round_robin")
    starts = [pool.sequence()[0].name for _ in range(6)]
    assert starts == ["openai", "brave", "tavily", "openai", "brave", "tavily"]

    pool.configure(clients, ["openai", "brave", "tavily"], "ordered")
    pool.failed("openai", "quota")
    assert [c.name for c in pool.sequence()] == ["brave", "tavily"] and pool.cooling() == ["openai"]
    now[0] += pool_module.COOLDOWN_SECONDS["quota"] + 1
    assert [c.name for c in pool.sequence()] == ["openai", "brave"]

    pool.failed("brave", "auth")
    pool.configure(clients, ["openai", "brave", "tavily"], "ordered")
    assert pool.cooling() == ["brave"]  # 配置没变，冷却保留
    changed = dict(clients, brave=FakeClient("brave", api_key="new-key"))
    pool.configure(changed, ["openai", "brave", "tavily"], "ordered")
    assert pool.cooling() == []  # 改了密钥，立即可用
    pool.configure({}, ["openai"], "ordered")
    assert not pool.configured and pool.sequence() == []


# ---------------------------------------------------------------------------- 服务


class PickLlm:
    def __init__(self, picks: List[str]) -> None:
        self.picks = list(picks)
        self.calls: List[str] = []
        self.pick_messages: List[Any] = []

    async def generate(self, prompt: Any, **kwargs) -> Dict[str, Any]:
        text = prompt if isinstance(prompt, str) else prompt[0]["content"][0]["text"]
        if "网搜到的" in text:
            self.calls.append("pick")
            self.pick_messages.append(prompt)
            response = self.picks.pop(0) if self.picks else "选择：0"
            if response == "fail":
                return {"success": False, "error": "vlm down"}
            return {"success": True, "response": response}
        stage = "extract" if "绘图提示词：" in text else "card"
        self.calls.append(stage)
        return {"success": True, "response": EXTRACT if stage == "extract" else CARD}


class EmptyFinder:
    """固定图源找不到图；网搜候选的缩略图和原图按表下载。"""

    def __init__(self, broken: tuple = ()) -> None:
        self.broken = set(broken)
        self.previews: List[str] = []
        self.fetched: List[str] = []

    async def find(self, **kwargs):
        return None, ["没有找到候选参考图"]

    async def preview(self, url: str, *, timeout_seconds: float = 10) -> bytes:
        self.previews.append(url)
        if url in self.broken:
            raise downloads.PublicFetchError("候选图下载失败")
        return jpeg()

    async def fetch(self, candidate):
        self.fetched.append(candidate.url)
        if candidate.url in self.broken:
            raise downloads.PublicFetchError("参考图下载失败（ProviderDownloadError）")
        return sources.FoundImage(data=jpeg(), size=(640, 400), page_url=candidate.page_url, source=candidate.source)


def make_service(tmp_path, clients: Dict[str, FakeClient], *, picks: List[str], finder=None, strategy="ordered"):
    config = DrawpicConfig()
    config.general.world_knowledge_enabled = True
    config.world_search.order = list(clients)
    config.world_search.strategy = strategy
    config.world_search.max_candidates = 3
    ctx = SimpleNamespace(llm=PickLlm(picks), logger=Mock(), web=FakeWeb())
    store = store_module.WorldKnowledgeStore(tmp_path)
    service = service_module.WorldKnowledgeService(
        config, ctx, store, proxy_settings=PROXY, finder=finder or EmptyFinder(), search_clients=clients,
    )
    return service, ctx, store


RESULTS = [
    image("https://i.pinimg.com/furina.jpg"),
    image("https://img.invalid/fan-art.jpg", page_url="https://fans.invalid/1", text="同人"),
    image("https://img.invalid/furina.png", page_url="https://wiki.invalid/furina",
          thumbnail_url="https://thumb.invalid/furina.jpg", text="芙宁娜 立绘"),
    image("https://img.invalid/other.jpg"),
    image("https://img.invalid/fourth.jpg"),
]


def logged(ctx) -> str:
    return " ".join(str(call) for call in ctx.logger.method_calls)


def test_search_picks_candidate_and_stores_original(tmp_path) -> None:
    async def run() -> None:
        brave = FakeClient("brave", RESULTS)
        finder = EmptyFinder()
        service, ctx, store = make_service(tmp_path, {"brave": brave}, picks=["选择：2\n理由：官方立绘"], finder=finder)
        result = await service.prepare("画芙宁娜在海边", max_images=1)
        assert brave.queries == ["原神 芙宁娜 角色 立绘"]
        # pinimg 被过滤，候选上限 3 张；缩略图优先用服务给的缩略图地址
        assert finder.previews == [
            "https://img.invalid/fan-art.jpg", "https://thumb.invalid/furina.jpg", "https://img.invalid/other.jpg",
        ]
        assert finder.fetched == ["https://img.invalid/furina.png"]
        content = ctx.llm.pick_messages[0][0]["content"]
        assert sum(part["type"] == "image" for part in content) == 3
        assert any(part.get("text", "").startswith("图 2：来源 wiki.invalid；标题：芙宁娜 立绘") for part in content)
        saved = store.find("芙宁娜")
        assert saved["refs"][0]["source"] == "Brave 搜图"
        assert saved["refs"][0]["page_url"] == "https://wiki.invalid/furina"
        assert len(result.images) == 1
        assert "原神 芙宁娜 角色 立绘" not in logged(ctx) and "brave" in logged(ctx)

    asyncio.run(run())


def test_none_picked_moves_to_next_provider(tmp_path) -> None:
    async def run() -> None:
        openai = FakeClient("openai", RESULTS[1:3], )
        brave = FakeClient("brave", RESULTS[2:4])
        service, ctx, store = make_service(
            tmp_path, {"openai": openai, "brave": brave}, picks=["选择：0\n理由：都不是", "选择：1"],
        )
        await service.prepare("画芙宁娜", max_images=1)
        assert ctx.llm.calls.count("pick") == 2 and len(openai.queries) == len(brave.queries) == 1
        assert store.find("芙宁娜")["refs"][0]["source"] == "Brave 搜图"

    asyncio.run(run())


def test_failed_provider_cools_down_and_is_skipped(tmp_path) -> None:
    async def run() -> None:
        openai = FakeClient("openai", error="quota")
        brave = FakeClient("brave", RESULTS[2:3])
        service, ctx, store = make_service(tmp_path, {"openai": openai, "brave": brave}, picks=["选择：1"])
        result = await service.prepare("画芙宁娜", max_images=1)
        assert len(result.images) == 1 and any("OpenAI 搜图失败" in item for item in result.warnings)
        assert service.search_pool.cooling() == ["openai"]
        assert "sk-" not in logged(ctx)

    asyncio.run(run())


def test_original_failure_falls_back_to_thumbnail_and_vlm_failure_gives_no_image(tmp_path) -> None:
    async def run() -> None:
        brave = FakeClient("brave", RESULTS[2:3])
        finder = EmptyFinder(broken=("https://img.invalid/furina.png",))
        service, _ctx, store = make_service(tmp_path / "a", {"brave": brave}, picks=["选择：1"], finder=finder)
        await service.prepare("画芙宁娜", max_images=1)
        assert finder.fetched == ["https://img.invalid/furina.png", "https://thumb.invalid/furina.jpg"]
        assert store.find("芙宁娜")["refs"]

        service, ctx, store = make_service(tmp_path / "b", {"brave": FakeClient("brave", RESULTS[2:3])}, picks=["fail"])
        result = await service.prepare("画芙宁娜", max_images=1)
        assert result.images == [] and store.find("芙宁娜")["refs"] == []
        assert ctx.llm.calls.count("pick") == 1

    asyncio.run(run())


def test_without_keys_no_search_happens(tmp_path) -> None:
    async def run() -> None:
        service, ctx, store = make_service(tmp_path, {}, picks=[])
        result = await service.prepare("画芙宁娜", max_images=1)
        assert "pick" not in ctx.llm.calls and result.images == []
        assert any("没有找到可用参考图" in item for item in result.warnings)

    asyncio.run(run())


def test_pick_parser_is_strict() -> None:
    prompts = module("application.knowledge.prompts")
    assert prompts.parse_pick("选择：2\n理由：x", 3) == 2
    assert prompts.parse_pick("选择：图 3", 3) == 3
    assert prompts.parse_pick("选择：0", 3) is None
    assert prompts.parse_pick("选择：4", 3) is None
    assert prompts.parse_pick("选择：1\n选择：2", 3) is None
    assert prompts.parse_pick("我觉得第二张", 3) is None
    text = prompts.render_pick_prompt({"name": "T1", "kind": "esports_team", "franchise": "英雄联盟", "look": ""}, 4)
    assert "「T1」（英雄联盟，" in text and "图 1～图 4" in text and json.dumps(text)
