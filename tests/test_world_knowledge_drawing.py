"""世界知识接入绘图流程：注入参考图与描述、按模型裁剪、单次覆盖与失败降级；不调用平台或联网。"""

from typing import Any, Dict, List
import asyncio
import json
import pytest

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


class SequenceLlm(FakeLlm):
    """依次返回校验结论；用完后一直返回最后一条。"""

    def __init__(self, verdicts, **kwargs) -> None:
        super().__init__(**kwargs)
        self.verdicts = list(verdicts)

    async def generate(self, prompt, **kwargs):
        response = await super().generate(prompt, **kwargs)
        if self.calls[-1] == "verify":
            response["response"] = self.verdicts.pop(0) if len(self.verdicts) > 1 else self.verdicts[0]
        return response


SEVERE = "结论：SEVERE\n问题：认成了别的角色\n修正：Draw Furina with her top hat."


def verify_setup(plugin, monkeypatch, tmp_path, verdicts, *, redraw=True, fail_redraw=False):
    service = plugin._require_draw_service()
    world, ctx, _store = make_service(tmp_path / "world", llm=SequenceLlm(verdicts))
    world.config.general.world_knowledge_verify_enabled = True
    world.config.general.world_knowledge_redraw_enabled = redraw
    service.world_knowledge_service = world
    calls = capture_attempts(service, monkeypatch)
    if fail_redraw:
        original = service._run_image_request_attempt

        async def run(**kwargs):
            if "[Correction from review]" in kwargs["prompt"]:
                raise module("domain.errors").ProviderRequestError(400, "invalid_request", "redraw rejected")
            return await original(**kwargs)

        monkeypatch.setattr(service, "_run_image_request_attempt", run)
    return service, ctx, calls


def test_pass_verdict_does_not_redraw(make_plugin, monkeypatch, tmp_path):
    async def run():
        plugin = make_plugin(False)
        await plugin.on_load()
        try:
            await add_provider(plugin, "openai", "Primary", models=["primary-image"])
            service, ctx, calls = verify_setup(plugin, monkeypatch, tmp_path, ["结论：PASS"])
            receipt = await draw(plugin, service, "画芙宁娜")
            assert len(calls) == 1 and ctx.llm.calls == ["extract", "card", "verify"]
            record = plugin._task_store.get_task(receipt["task_id"])
            assert record.status == "completed"
            assert record.world_knowledge["verify"] == {
                "verdict": "PASS", "checked": True, "issues": [], "redrawn": False, "kept": "original",
            }
            assert record.world_knowledge["entries"][0]["name"] == "芙宁娜"  # 校验结果与检索元数据合并保存
        finally:
            await plugin.on_unload()

    asyncio.run(run())


def test_severe_verdict_redraws_once_and_keeps_the_better_image(make_plugin, monkeypatch, tmp_path):
    async def run():
        plugin = make_plugin(False)
        await plugin.on_load()
        try:
            await add_provider(plugin, "openai", "Primary", models=["primary-image"])
            service, ctx, calls = verify_setup(plugin, monkeypatch, tmp_path, [SEVERE, "结论：MINOR\n问题：帽檐偏小"])
            receipt = await draw(plugin, service, "画芙宁娜")
            assert len(calls) == 2
            assert calls[1]["prompt"].endswith("[Correction from review] Draw Furina with her top hat.")
            assert calls[1]["sources"] == calls[0]["sources"] == 1
            verify = plugin._task_store.get_task(receipt["task_id"]).world_knowledge["verify"]
            assert verify["redrawn"] and verify["kept"] == "redraw" and verify["redraw_verdict"] == "MINOR"
            assert verify["issues"] == ["认成了别的角色"] and verify["redraw_issues"] == ["帽檐偏小"]
            assert ctx.llm.calls.count("verify") == 2
        finally:
            await plugin.on_unload()

    asyncio.run(run())


def test_worse_redraw_keeps_original_and_redraw_runs_only_once(make_plugin, monkeypatch, tmp_path):
    async def run():
        plugin = make_plugin(False)
        await plugin.on_load()
        try:
            await add_provider(plugin, "openai", "Primary", models=["primary-image"])
            service, _ctx, calls = verify_setup(plugin, monkeypatch, tmp_path, ["结论：MINOR", SEVERE])
            await draw(plugin, service, "画芙宁娜")
            assert len(calls) == 1  # MINOR 不重画

            service2, _ctx2, calls2 = verify_setup(plugin, monkeypatch, tmp_path / "b", [SEVERE, SEVERE])
            receipt = await draw(plugin, service2, "画芙宁娜")
            assert len(calls2) == 2  # 重画后仍 SEVERE 也只重画一次；持平留重画版
            verify = plugin._task_store.get_task(receipt["task_id"]).world_knowledge["verify"]
            assert verify["kept"] == "redraw" and verify["redraw_verdict"] == "SEVERE"
        finally:
            await plugin.on_unload()

    asyncio.run(run())


def test_failed_redraw_keeps_original_and_completes(make_plugin, monkeypatch, tmp_path):
    async def run():
        plugin = make_plugin(False)
        await plugin.on_load()
        try:
            await add_provider(plugin, "openai", "Primary", models=["primary-image"])
            service, _ctx, calls = verify_setup(plugin, monkeypatch, tmp_path, [SEVERE], fail_redraw=True)
            receipt = await draw(plugin, service, "画芙宁娜")
            record = plugin._task_store.get_task(receipt["task_id"])
            assert record.status == "completed" and record.result_count == 1
            verify = record.world_knowledge["verify"]
            assert verify["kept"] == "original" and not verify["redrawn"] and "redraw rejected" in verify["redraw_error"]
        finally:
            await plugin.on_unload()

    asyncio.run(run())


def test_redraw_switch_off_and_unparseable_verdict(make_plugin, monkeypatch, tmp_path):
    async def run():
        plugin = make_plugin(False)
        await plugin.on_load()
        try:
            await add_provider(plugin, "openai", "Primary", models=["primary-image"])
            service, _ctx, calls = verify_setup(plugin, monkeypatch, tmp_path, [SEVERE], redraw=False)
            receipt = await draw(plugin, service, "画芙宁娜")
            assert len(calls) == 1
            assert plugin._task_store.get_task(receipt["task_id"]).world_knowledge["verify"]["verdict"] == "SEVERE"

            service, _ctx, calls = verify_setup(plugin, monkeypatch, tmp_path / "b", ["看起来挺好"])
            receipt = await draw(plugin, service, "画芙宁娜")
            verify = plugin._task_store.get_task(receipt["task_id"]).world_knowledge["verify"]
            assert len(calls) == 1 and verify["verdict"] == "PASS" and verify["checked"] is False
        finally:
            await plugin.on_unload()

    asyncio.run(run())


def test_gif_results_are_not_verified(make_plugin, monkeypatch, tmp_path):
    async def run():
        plugin = make_plugin(False)
        await plugin.on_load()
        try:
            await add_provider(plugin, "openai", "Primary", models=["primary-image"])
            service, ctx, _calls = verify_setup(plugin, monkeypatch, tmp_path, [SEVERE])
            world = await service.prepare_world_knowledge(
                task_id="", prompt="画芙宁娜", model="Primary/primary-image", source_images=[], source_urls=[],
                animation=None, override=None,
            )
            attempt = module("application.drawing.types").ImageRequestAttempt(
                model="Primary/primary-image", provider_name="openai", openai_compatibility_mode="",
                animation=object(),
            )
            images = [b"GIF89a"]
            result = await service.verify_world_result(
                world=world, task_id="", images=images, attempt=attempt, matched_message_id="",
                request_negative_prompt="",
            )
            assert result is images and "verify" not in ctx.llm.calls
        finally:
            await plugin.on_unload()

    asyncio.run(run())


def test_v2_override_signature_and_validation(make_plugin, monkeypatch, tmp_path):
    from hashlib import sha256

    async def run():
        plugin = make_plugin(False)
        await plugin.on_load()
        try:
            await add_provider(plugin, "openai", "Primary", models=["primary-image"])
            service = plugin._require_draw_service()
            world, ctx, _store = make_service(tmp_path / "world")
            world.config.general.world_knowledge_enabled = False
            service.world_knowledge_service = world
            calls = capture_attempts(service, monkeypatch)
            model = "Primary/primary-image"

            forced = await plugin.drawpic_submit_v2("画芙宁娜", model=model, request_id="world-forced-01",
                                                    world_knowledge=True)
            await asyncio.gather(*tuple(service.background_tasks))
            assert forced["accepted"] and "[World references" in calls[-1]["prompt"]
            record = plugin._task_store.get_task(forced["task_id"])
            values = ["画芙宁娜", model, "", "", "draw", "", None, None, {"world_knowledge": True}]
            assert record.submission["signature"] == sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()
            conflict = await plugin.drawpic_submit_v2("画芙宁娜", model=model, request_id="world-forced-01")
            assert conflict["error"]["code"] == "REQUEST_ID_CONFLICT"

            plain = await plugin.drawpic_submit_v2("画芙宁娜", model=model, request_id="world-plain-001")
            await asyncio.gather(*tuple(service.background_tasks))
            assert calls[-1]["prompt"] == "画芙宁娜"
            plain_values = ["画芙宁娜", model, "", "", "draw", "", None, None]
            assert plugin._task_store.get_task(plain["task_id"]).submission["signature"] == sha256(
                json.dumps(plain_values, ensure_ascii=False).encode()).hexdigest()

            invalid = await plugin.drawpic_submit_v2("画芙宁娜", model=model, world_knowledge="yes")
            assert invalid["error"]["code"] == "INVALID_REQUEST" and not invalid["accepted"]

            receipt = await plugin.workspace_submit(json.dumps(
                {"prompt": "画芙宁娜", "model": model, "world_knowledge": False}, ensure_ascii=False))
            await asyncio.gather(*tuple(service.background_tasks))
            assert receipt["task_id"] and calls[-1]["prompt"] == "画芙宁娜"
        finally:
            await plugin.on_unload()

    asyncio.run(run())


def test_client_lookup_and_result_metadata(make_plugin, monkeypatch, tmp_path):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parents[1] / "clients"))
    from maimai_drawing_client import DrawingClient, DrawingError
    from test_drawing_client import LocalAPI

    async def run():
        plugin = make_plugin(False)
        await plugin.on_load()
        try:
            await add_provider(plugin, "openai", "Primary", models=["primary-image"])
            service = plugin._require_draw_service()
            world, ctx, _store = make_service(tmp_path / "world", llm=FakeLlm(delay=0.3))
            service.world_knowledge_service = world
            capture_attempts(service, monkeypatch)
            client = DrawingClient(LocalAPI(plugin), poll_interval=0.001)

            quick = await client.lookup_world("画芙宁娜", wait_seconds=0)
            assert quick["pending"] and quick["entries"] == [] and quick["error"] is None
            await asyncio.gather(*world._background)
            done = await client.lookup_world("画芙宁娜", wait_seconds=5)
            entry = done["entries"][0]
            assert not done["pending"] and entry["name"] == "芙宁娜" and entry["look"] and entry["has_ref"]
            assert "Furina" in entry["aliases"]

            result = await client.generate("画芙宁娜", model="Primary/primary-image", wait_seconds=5)
            assert result.status == "completed" and result.world_knowledge["entries"][0]["name"] == "芙宁娜"

            with pytest.raises(DrawingError) as caught:
                await client.lookup_world("", wait_seconds=1)
            assert caught.value.code == "INVALID_REQUEST"
            world.config.general.world_knowledge_enabled = False
            assert (await client.lookup_world("画芙宁娜", wait_seconds=1))["disabled"] is True
            assert (await client.lookup_world("画芙宁娜", wait_seconds=1, world_knowledge=True))["disabled"] is False
        finally:
            await plugin.on_unload()

    asyncio.run(run())
