"""世界知识作为参考体系的一个来源：点名对象先查词条库、词条图按原版额度补位；不调用真实模型或联网。"""

from types import SimpleNamespace
import asyncio
import logging

import pytest

from test_references import module
from test_workspace import image_bytes
from test_world_knowledge_service import make_service

world_refs = module("application.references.world")


def _image(seed: int, size: int = 16) -> bytes:
    return bytes([seed]) * size


def _resolution(*names: str):
    entries = [{"id": f"e{index}", "name": name, "aliases": []} for index, name in enumerate(names)]
    images = [(entry["id"], _image(index + 1)) for index, entry in enumerate(entries)]
    return SimpleNamespace(entries=entries, images=images)


def test_selection_fills_only_remaining_budget_and_skips_covered_or_duplicate_images():
    resolution = _resolution("芙宁娜", "T1", "钟离")
    select = world_refs.select_world_images
    assert select(resolution, existing=[], covered=[], slots=0) == []
    assert [entry for entry, _ in select(resolution, existing=[], covered=[], slots=2)] == ["e0", "e1"]
    # 素材已覆盖芙宁娜（归一化后同名），由后面的词条替补
    assert [entry for entry, _ in select(resolution, existing=[], covered=[" 芙宁娜 "], slots=2)] == ["e1", "e2"]
    # 同一张图已在请求里，不重复加
    assert [entry for entry, _ in select(resolution, existing=[_image(1)], covered=[], slots=1)] == ["e1"]
    # 合并后不超过 8 张
    seven = [_image(100 + index) for index in range(7)]
    assert len(select(resolution, existing=seven, covered=[], slots=2)) == 1
    assert select(resolution, existing=[*seven, _image(99)], covered=[], slots=2) == []


def test_selection_respects_total_bytes(monkeypatch):
    monkeypatch.setattr(world_refs, "MAX_SOURCE_BYTES", 40)
    resolution = SimpleNamespace(
        entries=[{"id": "big", "name": "A", "aliases": []}, {"id": "small", "name": "B", "aliases": []}],
        images=[("big", _image(1, 30)), ("small", _image(2, 10))],
    )
    chosen = world_refs.select_world_images(resolution, existing=[_image(3, 20)], covered=[], slots=2)
    assert [entry for entry, _ in chosen] == ["small"]


def test_library_finder_returns_entry_images_only_for_known_subjects(tmp_path):
    async def run():
        service, _ctx, store = make_service(tmp_path / "world")
        await service.prepare("画芙宁娜", max_images=1)  # 建好芙宁娜词条与参考图
        finder = world_refs.world_material_finder(store)
        recognition = module("application.references.recognition")
        need = recognition.MaterialNeed(subject="芙宁娜", mention="Furina", web_search=True, role="identity", query="Furina 官方")
        found = await finder(need)
        assert len(found) == 1 and found[0].source == "world" and found[0].raw
        other = recognition.MaterialNeed(subject="甘雨", mention="甘雨", web_search=True, role="identity", query="甘雨 官方")
        assert await finder(other) == []

    asyncio.run(run())


@pytest.mark.parametrize("library_matches,expected_web,expected_source", [
    (True, 0, "world"), (False, 1, "web"),
])
def test_named_material_tries_library_before_web_search(tmp_path, monkeypatch, library_matches, expected_web, expected_source):
    async def run():
        recognition = module("application.references.recognition")
        service = module("application.references.service")
        references = module("domain.references")
        config = module("domain.configuration.models").DrawpicConfig()
        config.general.references.allow_web_material_search = True
        counts = {"web": 0, "library": 0}

        async def needs(self, original, *, source_count=0):
            return recognition.MaterialNeeds(chat_followup=False, needs=[
                recognition.MaterialNeed(subject="甘雨", mention="甘雨", web_search=True, role="identity", query="甘雨 官方"),
            ])

        async def web(*args, **kwargs):
            counts["web"] += 1
            return [references.ReferenceImage(image_bytes(), "web")]

        async def library(need):
            counts["library"] += 1
            return [references.ReferenceImage(image_bytes(), "world")]

        async def matches(self, image, need):
            return library_matches or image.source != "world"

        monkeypatch.setattr(recognition.ReferenceRecognizer, "needs", needs)
        monkeypatch.setattr(recognition.ReferenceRecognizer, "matches", matches)
        monkeypatch.setattr(module("infrastructure.references.materials").MaterialSource, "web", web)
        prepared = await service.freeze_reference_request(
            ctx=SimpleNamespace(logger=logging.getLogger("world-source-test")), config=config,
            store=module("infrastructure.storage.reference_assets").ReferenceAssetStore(tmp_path),
            streams=SimpleNamespace(), prompt="画甘雨", style="", negative="", stream_id="",
            options=references.ReferenceOptions(user_request="画甘雨", material_sources=["web"]),
            images=[], urls=[],
        )
        result = await prepared.prepare("world-source-test", world_materials=library)
        assert counts == {"web": expected_web, "library": 1}
        assert result.task_type == "edit_image" and len(result.images) == 1
        assert [(image.subject, image.source) for image in result.materials] == [("甘雨", expected_source)]

        # 不传词条库时与原版一致：直接网搜
        counts.update(web=0, library=0)
        again = await prepared.prepare("world-source-test")
        assert counts == {"web": 1, "library": 0} and again.materials[0].source == "web"

    asyncio.run(run())
