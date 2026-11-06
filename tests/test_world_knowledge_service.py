"""世界知识服务：识别、查库、检索、整理词条、取图、注入与校验，全部用模拟的模型与联网能力。"""

from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import Mock
import asyncio
import pytest

from test_review_regressions import module
from test_workspace import DrawpicConfig, image_bytes

service_module = module("application.knowledge.service")
prompts = module("application.knowledge.prompts")
store_module = module("infrastructure.storage.world_knowledge")
FoundImage = module("infrastructure.media.world_sources").FoundImage

EXTRACT = "芙宁娜|game_character|原神|水神;Furina|芙宁娜 官方立绘"
CARD = (
    "词条：芙宁娜\n状态：找到\n作品：原神\n别名：Furina\n外观：白蓝礼服，高礼帽，异色瞳\n"
    "绘图：white and blue dress, top hat, heterochromia eyes\n事实：2023-11-08 4.2 版本上线\n来源：1\n"
)


class FakeLlm:
    def __init__(self, *, extract: str = EXTRACT, card: str = CARD, verify: str = "结论：PASS", delay: float = 0) -> None:
        self.extract, self.card, self.verify, self.delay = extract, card, verify, delay
        self.calls: List[str] = []

    async def generate(self, prompt: Any, **kwargs) -> Dict[str, Any]:
        text = prompt if isinstance(prompt, str) else prompt[0]["content"][0]["text"]
        stage = "extract" if "绘图提示词：" in text else "card" if "整理一张绘图词条" in text else "verify"
        self.calls.append(stage)
        if stage == "card" and self.delay:
            await asyncio.sleep(self.delay)
        return {"success": True, "response": getattr(self, stage)}


class FakeWeb:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.queries: List[str] = []

    async def search(self, query: str, *, max_results: int = 5) -> Dict[str, Any]:
        self.queries.append(query)
        if self.fail:
            raise RuntimeError("web.search 未启用")
        return {"result": {"results": [{
            "title": "芙宁娜 - 原神 Wiki", "url": "https://genshin-impact.fandom.com/wiki/Furina?utm=1",
            "snippet": "芙宁娜是枫丹的水神，身穿白蓝礼服、头戴高礼帽。" * 10, "published_at": "2023-11-08",
        }]}}

    async def fetch(self, url: str) -> Dict[str, Any]:
        return {"url": url, "content": "正文"}


class FakeFinder:
    def __init__(self) -> None:
        self.calls = 0

    async def find(self, **kwargs):
        self.calls += 1
        return FoundImage(data=jpeg(), size=(640, 400), page_url=kwargs["pages"][0], source="mediawiki"), []


def jpeg() -> bytes:
    images = module("infrastructure.media.images")
    return images.normalize_reference_image(image_bytes())[0]


def make_service(tmp_path, *, llm=None, web=None, config=None, finder=None):
    config = config or DrawpicConfig()
    config.general.world_knowledge_enabled = True
    ctx = SimpleNamespace(llm=llm or FakeLlm(), logger=Mock())
    if web is not False:
        ctx.web = web or FakeWeb()
    store = store_module.WorldKnowledgeStore(tmp_path)
    proxy = module("infrastructure.http").HttpProxySettings.disabled()
    service = service_module.WorldKnowledgeService(
        config, ctx, store, proxy_settings=proxy, finder=finder or FakeFinder(),
    )
    return service, ctx, store


def test_parsers_are_strict_and_tolerant() -> None:
    mentions = prompts.parse_entities(
        "1. 芙宁娜|game_character|原神|水神;Furina|芙宁娜 立绘\n乱写的一行\nT1|esports_team||SKT|\n芙宁娜|other", 3,
    )
    assert [(m.name, m.kind, m.aliases) for m in mentions] == [
        ("芙宁娜", "game_character", ("水神", "Furina")), ("T1", "esports_team", ("SKT",)),
    ]
    assert mentions[1].query == "T1"
    assert prompts.parse_entities("无", 3) == []
    cards = prompts.parse_cards(CARD + "\n词条：T1\n状态：未找到\n")
    assert cards["芙宁娜"].found and cards["芙宁娜"].source_numbers == [1]
    assert cards["芙宁娜"].facts == ["2023-11-08 4.2 版本上线"]
    assert not cards["t1"].found
    severe = prompts.parse_verdict("结论：SEVERE\n问题：帽子画成了王冠\n修正：Give her a black top hat.")
    assert severe.level == "SEVERE" and severe.issues == ("帽子画成了王冠",) and severe.score == 3
    assert severe.correction == "Give her a black top hat."
    assert prompts.parse_verdict("看起来不错").checked is False
    assert prompts.parse_verdict("结论：MINOR\n修正：x").correction == ""


def test_full_flow_saves_entry_attaches_image_and_injects(tmp_path) -> None:
    async def run() -> None:
        service, ctx, store = make_service(tmp_path)
        result = await service.prepare("画芙宁娜在海边", task_id="t1", max_images=2)
        assert [entry["name"] for entry in result.entries] == ["芙宁娜"]
        assert ctx.llm.calls == ["extract", "card"]
        assert ctx.web.queries == ["芙宁娜 官方立绘"]
        saved = store.find("Furina")
        assert saved["look"] == "白蓝礼服，高礼帽，异色瞳"
        assert saved["sources"][0]["url"] == "https://genshin-impact.fandom.com/wiki/Furina"
        assert len(saved["refs"]) == 1 and len(result.images) == 1
        suffix = result.prompt_suffix(offset=1)
        assert "芙宁娜" in suffix and "Image 2 is the official design" in suffix
        assert len(suffix) <= prompts.MAX_INJECTION_CHARS
        metadata = result.metadata()
        assert metadata["entries"][0]["sources"] == ["genshin-impact.fandom.com"]
        assert "utm" not in str(metadata) and "base64" not in str(metadata)

        # 第二次：词条未过期，不再联网检索，也不再整理词条
        ctx.llm.calls.clear()
        again = await service.prepare("芙宁娜和水神", max_images=0)
        assert ctx.llm.calls == ["extract"] and ctx.web.queries == ["芙宁娜 官方立绘"]
        assert again.images == [] and again.entries[0]["refs"]

    asyncio.run(run())


def test_nothing_extracted_means_no_search(tmp_path) -> None:
    async def run() -> None:
        service, ctx, _store = make_service(tmp_path, llm=FakeLlm(extract="无"))
        result = await service.prepare("画一只猫")
        assert result.entries == [] and ctx.web.queries == [] and ctx.llm.calls == ["extract"]

    asyncio.run(run())


def test_manual_entries_are_used_without_model_or_network(tmp_path) -> None:
    async def run() -> None:
        config = DrawpicConfig()
        config.general.world_knowledge_max_entities = 0
        service, ctx, store = make_service(tmp_path, config=config)
        store.save_manual(None, {"name": "T1", "kind": "esports_team", "look": "红黑队服"})
        result = await service.prepare("T1 夺冠庆祝")
        assert [entry["name"] for entry in result.entries] == ["T1"]
        assert ctx.llm.calls == [] and ctx.web.queries == []
        assert (await service.prepare("T10 夺冠")).entries == []

    asyncio.run(run())


def test_offline_host_degrades_and_backs_off(tmp_path) -> None:
    async def run() -> None:
        web = FakeWeb(fail=True)
        service, ctx, store = make_service(tmp_path, web=web)
        result = await service.prepare("画芙宁娜")
        assert result.entries == [] and any("联网检索失败" in warning for warning in result.warnings)
        assert store.find("芙宁娜") is None  # 检索出错不写负缓存
        await service.prepare("画芙宁娜")
        assert len(web.queries) == 1  # 10 分钟内不再检索
        assert ctx.llm.calls == ["extract", "extract"]

        no_web, _ctx, _store = make_service(tmp_path / "other", web=False)
        degraded = await no_web.prepare("画芙宁娜")
        assert any("联网检索不可用" in warning for warning in degraded.warnings)

    asyncio.run(run())


def test_timeout_returns_partial_result(tmp_path) -> None:
    async def run() -> None:
        config = DrawpicConfig()
        config.general = config.general.model_copy(update={"world_knowledge_timeout_seconds": 1.5})
        service, ctx, store = make_service(tmp_path, config=config, llm=FakeLlm(delay=5))
        store.save_manual(None, {"name": "T1", "kind": "esports_team", "look": "红黑队服"})
        result = await asyncio.wait_for(service.prepare("芙宁娜和 T1"), 4)
        assert [entry["name"] for entry in result.entries] == ["T1"]
        assert any("超时" in warning for warning in result.warnings)

    asyncio.run(run())


def test_lookup_returns_pending_and_finishes_in_background(tmp_path) -> None:
    async def run() -> None:
        service, ctx, store = make_service(tmp_path, llm=FakeLlm(delay=0.5))
        quick = await service.lookup("画芙宁娜", wait_seconds=0.1)
        assert quick["pending"] and quick["entries"] == []
        await asyncio.gather(*service._background)
        assert store.find("芙宁娜")["look"]
        done = await service.lookup("画芙宁娜", wait_seconds=2)
        assert not done["pending"] and done["entries"][0]["name"] == "芙宁娜"
        await service.close()

        service.config.general.world_knowledge_enabled = False
        ctx.llm.calls.clear()
        assert (await service.lookup("画芙宁娜", wait_seconds=1)) == {"disabled": True, "pending": False, "entries": []}
        assert ctx.llm.calls == []

    asyncio.run(run())


def test_verify_only_checks_with_supplied_references(tmp_path) -> None:
    async def run() -> None:
        llm = FakeLlm(verify="结论：SEVERE\n问题：认成了别的角色\n修正：Draw Furina with a top hat.")
        service, ctx, store = make_service(tmp_path, llm=llm)
        empty = await service.verify(image_bytes(), service_module.WorldResolution())
        assert empty.checked is False and ctx.llm.calls == []
        result = await service.prepare("画芙宁娜", max_images=1)
        verdict = await service.verify(image_bytes(), result, task_id="t1")
        assert verdict.level == "SEVERE" and verdict.correction.startswith("Draw Furina")
        assert ctx.llm.calls[-1] == "verify"

        async def broken(prompt, **kwargs):
            raise RuntimeError("vlm offline")

        ctx.llm.generate = broken
        assert (await service.verify(image_bytes(), result)).checked is False

    asyncio.run(run())
