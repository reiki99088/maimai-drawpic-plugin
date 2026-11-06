"""世界知识接入绘图流程：注入参考图与描述、按模型裁剪、单次覆盖与失败降级；不调用平台或联网。"""

from typing import Any, Dict, List
import asyncio
import json

from test_routing_review_fixes import add_provider, make_plugin as make_plugin, module, set_settings  # noqa: F401
from test_world_knowledge_service import FakeLlm, make_service


def capture_attempts(service, monkeypatch, fail_models=()) -> List[Dict[str, Any]]:
    calls: List[Dict[str, Any]] = []
    errors = module("domain.errors")
    sample = module("infrastructure.media.images")

    async def run(*, attempt, prompt, task_id, task_type, source_image_bytes_list, source_image_urls, **kwargs):
        calls.append({
            "model": attempt.model, "prompt": prompt, "task_type": task_type,
            "sources": len(source_image_bytes_list), "urls": list(source_image_urls),
        })
        if attempt.model in fail_models:
            raise errors.ProviderRequestError(400, "invalid_request", "fixture rejected")
        from test_workspace import image_bytes
        return [sample.normalize_reference_image(image_bytes())[0]]

    monkeypatch.setattr(service, "_run_image_request_attempt", run)
    return calls


async def draw(plugin, service, prompt: str, **kwargs) -> Dict[str, Any]:
    receipt = await service.start_background_image_request(
        prompt=prompt, stream_id="", resolved_model=kwargs.pop("model", "Primary/primary-image"),
        resolved_openai_mode="", provider_name="openai", **kwargs,
    )
    await asyncio.gather(*tuple(service.background_tasks))
    return receipt


def test_references_and_description_are_injected_and_recorded(make_plugin, monkeypatch, tmp_path):
    async def run():
        plugin = make_plugin(False)
        await plugin.on_load()
        try:
            await add_provider(plugin, "openai", "Primary", models=["primary-image"])
            service = plugin._require_draw_service()
            world, ctx, _store = make_service(tmp_path / "world")
            service.world_knowledge_service = world
            calls = capture_attempts(service, monkeypatch)
            receipt = await draw(plugin, service, "画芙宁娜在海边")
            assert len(calls) == 1
            call = calls[0]
            assert call["task_type"] == "edit_image" and call["sources"] == 1 and call["urls"] == [""]
            assert call["prompt"].startswith("画芙宁娜在海边\n\n[World references")
            assert "Image 1 is the official design of 芙宁娜" in call["prompt"]
            record = plugin._task_store.get_task(receipt["task_id"])
            assert record.status == "completed" and record.task_type == "draw"
            wk = record.world_knowledge
            assert wk["entries"][0]["name"] == "芙宁娜" and wk["entries"][0]["image_used"]
            assert wk["reference_images_sent"] == 1
            dumped = json.dumps(wk, ensure_ascii=False)
            assert "官方立绘" not in dumped and "utm" not in dumped and "base64" not in dumped
            detail = await plugin.drawpic_task(receipt["task_id"])
            assert detail["world_knowledge"]["entries"][0]["sources"] == ["genshin-impact.fandom.com"]
        finally:
            await plugin.on_unload()

    asyncio.run(run())


def test_override_and_master_switch(make_plugin, monkeypatch, tmp_path):
    async def run():
        plugin = make_plugin(False)
        await plugin.on_load()
        try:
            await add_provider(plugin, "openai", "Primary", models=["primary-image"])
            service = plugin._require_draw_service()
            world, ctx, _store = make_service(tmp_path / "world", llm=FakeLlm(extract="无"))
            service.world_knowledge_service = world
            calls = capture_attempts(service, monkeypatch)

            receipt = await draw(plugin, service, "画芙宁娜", world_knowledge=False)
            assert ctx.llm.calls == [] and calls[-1]["prompt"] == "画芙宁娜" and calls[-1]["task_type"] == "draw"
            assert plugin._task_store.get_task(receipt["task_id"]).world_knowledge == {}

            world.config.general.world_knowledge_enabled = False
            await draw(plugin, service, "画芙宁娜")
            assert ctx.llm.calls == []
            await draw(plugin, service, "画芙宁娜", world_knowledge=True)
            assert ctx.llm.calls == ["extract"]
            assert calls[-1]["prompt"] == "画芙宁娜"  # 没有命中词条时请求与原流程一致
        finally:
            await plugin.on_unload()

    asyncio.run(run())


def test_fallback_without_image_edit_gets_text_only(make_plugin, monkeypatch, tmp_path):
    async def run():
        plugin = make_plugin(False)
        await plugin.on_load()
        try:
            await add_provider(plugin, "openai", "Primary", models=["primary-image"])
            await add_provider(plugin, "openai", "Backup", models=["backup-image"])
            await set_settings(
                plugin, fallback_models=["Backup/backup-image"], image_edit_unsupported_models=["Backup/backup-image"],
            )
            service = plugin._require_draw_service()
            world, _ctx, _store = make_service(tmp_path / "world")
            service.world_knowledge_service = world
            calls = capture_attempts(service, monkeypatch, fail_models={"Primary/primary-image"})
            receipt = await draw(plugin, service, "画芙宁娜")
            assert [(c["model"], c["task_type"], c["sources"]) for c in calls] == [
                ("Primary/primary-image", "edit_image", 1), ("Backup/backup-image", "draw", 0),
            ]
            assert "[World references" in calls[1]["prompt"] and "Image 1" not in calls[1]["prompt"]
            assert plugin._task_store.get_task(receipt["task_id"]).status == "completed"
        finally:
            await plugin.on_unload()

    asyncio.run(run())


def test_reference_slots_follow_model_limits(make_plugin, monkeypatch, tmp_path):
    async def run():
        plugin = make_plugin(False)
        await plugin.on_load()
        try:
            await add_provider(plugin, "openai", "Primary", models=["primary-image"])
            service = plugin._require_draw_service()
            world, _ctx, _store = make_service(tmp_path / "world")
            service.world_knowledge_service = world
            model = "Primary/primary-image"
            assert service.world_reference_slots(model, 0, None) == 2
            monkeypatch.setattr(service.router, "get_max_source_images", lambda name: 2)
            assert service.world_reference_slots(model, 1, None) == 1
            assert service.world_reference_slots(model, 2, None) == 0
            animation = module("domain.models.animation").AnimationOptions
            assert service.world_reference_slots(model, 0, object.__new__(animation)) == 0
            monkeypatch.setattr(service.router, "get_model_provider", lambda name: "novelai")
            assert service.world_reference_slots(model, 0, None) == 0

            # 已有源图占满上限：只注入文字，源图原样保留
            monkeypatch.undo()
            monkeypatch.setattr(service.router, "get_max_source_images", lambda name: 1)
            calls = capture_attempts(service, monkeypatch)
            from test_workspace import image_bytes
            await draw(plugin, service, "把这张图改成芙宁娜", source_image_bytes_list=[image_bytes()],
                       source_image_urls=["https://source.invalid/a.png"])
            assert calls[-1]["sources"] == 1 and calls[-1]["urls"] == ["https://source.invalid/a.png"]
            assert "[World references" in calls[-1]["prompt"] and "Image 2" not in calls[-1]["prompt"]
        finally:
            await plugin.on_unload()

    asyncio.run(run())


def test_world_knowledge_failure_falls_back_to_original_request(make_plugin, monkeypatch, tmp_path):
    async def run():
        plugin = make_plugin(False)
        await plugin.on_load()
        try:
            await add_provider(plugin, "openai", "Primary", models=["primary-image"])
            service = plugin._require_draw_service()
            world, _ctx, _store = make_service(tmp_path / "world")
            service.world_knowledge_service = world

            async def broken(*args, **kwargs):
                raise RuntimeError("store exploded")

            monkeypatch.setattr(world, "prepare", broken)
            calls = capture_attempts(service, monkeypatch)
            receipt = await draw(plugin, service, "画芙宁娜")
            assert calls[-1]["prompt"] == "画芙宁娜" and calls[-1]["task_type"] == "draw"
            assert plugin._task_store.get_task(receipt["task_id"]).status == "completed"
        finally:
            await plugin.on_unload()

    asyncio.run(run())


def test_plugin_wires_one_world_service_across_refreshes(make_plugin):
    async def run():
        plugin = make_plugin()
        await plugin.on_load()
        try:
            world = plugin._world_service
            assert world is not None and plugin._require_draw_service().world_knowledge_service is world
            assert world.enabled() is False
            plugin._refresh_services()
            assert plugin._world_service is world and plugin._require_draw_service().world_knowledge_service is world
        finally:
            await plugin.on_unload()

    asyncio.run(run())


def test_task_record_round_trips_world_metadata(tmp_path):
    tasks = module("infrastructure.storage.tasks")
    store = tasks.DrawTaskStore(path=tmp_path / "draw_tasks.json")
    record = store.create_task(
        session_key="s", stream_id="", task_type="draw", prompt="p", model="m", provider="openai", message="x",
    )
    store.update_task(record.task_id, status="running", message="y", world_knowledge={"image_count": 1})
    store.update_task(record.task_id, status="running", message="z", world_knowledge={"verdict": "PASS"})
    reloaded = tasks.DrawTaskStore(path=tmp_path / "draw_tasks.json")
    reloaded.load()
    assert reloaded.get_task(record.task_id).world_knowledge == {"image_count": 1, "verdict": "PASS"}
