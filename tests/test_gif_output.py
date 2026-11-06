"""gpt-image-2.6 GIF 动图：参数、能力、请求、存储、审核与工具透传；全部内存模拟。"""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from PIL import Image

import asyncio
import base64
import json
import pytest

from test_workspace import _PACKAGE, DrawpicConfig, image_bytes, make_plugin as make_plugin
import importlib


def module(name):
    return importlib.import_module(f"{_PACKAGE}.src.maimai_drawpic.{name}")


animation_module = module("domain.models.animation")
AnimationOptions = animation_module.AnimationOptions
parse_animation_options = animation_module.parse_animation_options
OpenaiImage = module("infrastructure.providers.openai").OpenaiImage
OpenAIRequestError = module("infrastructure.providers.openai").OpenAIRequestError
ProviderResultError = module("domain.errors").ProviderResultError
ProviderRouter = module("application.routing").ProviderRouter
supports_gif_output = module("domain.models.openai_profiles").supports_gif_output


def gif(frames: int = 3, size=(48, 32)) -> bytes:
    buffer = BytesIO()
    images = [Image.new("RGB", size, (60 * index, 90, 140)) for index in range(frames)]
    images[0].save(buffer, "GIF", save_all=True, append_images=images[1:], duration=120, loop=0)
    return buffer.getvalue()


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def test_parse_animation_strict_and_lenient() -> None:
    assert parse_animation_options() is None
    assert parse_animation_options(True) == AnimationOptions()
    assert parse_animation_options(True, 4, 100) == AnimationOptions(4, 100)
    assert parse_animation_options("true", "4", "", lenient=True) == AnimationOptions(4, None)
    assert parse_animation_options("false", lenient=True) is None
    for bad in [("true", None, None), (True, "4", None), (True, True, None), (1, None, None)]:
        with pytest.raises(ValueError):
            parse_animation_options(*bad)
    for bad in [(True, 1, None), (True, 17, None), (True, None, 19), (True, None, 2001)]:
        with pytest.raises(ValueError, match="应为"):
            parse_animation_options(*bad)
    with pytest.raises(ValueError, match="animated=true"):
        parse_animation_options(False, 4)
    assert AnimationOptions(4).request_fields() == {"output_format": "gif", "frame_count": 4}
    assert AnimationOptions().signature() == {"animated": True, "frame_count": None, "frame_duration_ms": None}


@pytest.mark.parametrize("model,expected", [
    ("gpt-image-2.6", True), ("gpt-image-2.6-flare", True), ("GPT-Image-2.6-Sunburst", True),
    ("gpt-image-2.6_x", True), ("gpt-image-2.60", False), ("gpt-image-2.5", False),
    ("gpt-image-2", False), ("dall-e-3", False),
])
def test_gif_model_family_prefix(model: str, expected: bool) -> None:
    assert supports_gif_output(model) is expected


def router_for(models, **openai):
    config = DrawpicConfig()
    config.openai.models = models
    for key, value in openai.items():
        setattr(config.openai, key, value)
    return ProviderRouter(config)


def test_animation_capability_by_model_and_mode() -> None:
    router = router_for(["gpt-image-2.6-flare", "gpt-image-2"])
    assert router.evaluate_model_animation_capability("gpt-image-2.6-flare").allowed
    denied = router.evaluate_model_animation_capability("gpt-image-2")
    assert not denied.allowed and "2.6" in denied.reason and denied.source == "openai_gif_registry"
    chat = router.evaluate_model_animation_capability("gpt-image-2.6-flare", "chat_completions")
    assert not chat.allowed and chat.source == "openai_mode"
    assert not router.evaluate_model_animation_capability("unknown-model").allowed


def test_animated_provider_bypasses_cache_and_rejects_non_openai() -> None:
    router = router_for(["gpt-image-2.6-flare"])
    plain, _ = router.require_platform_for_model("gpt-image-2.6-flare")
    assert router.require_platform_for_model("gpt-image-2.6-flare")[0] is plain
    first, _ = router.require_platform_for_model("gpt-image-2.6-flare", animation=AnimationOptions(4))
    second, _ = router.require_platform_for_model("gpt-image-2.6-flare", animation=AnimationOptions(4))
    assert first is not plain and first is not second
    assert first.provider.animation == AnimationOptions(4) and plain.provider.animation is None


def test_generation_payload_carries_frames_and_drops_incompatible_parameters() -> None:
    provider = OpenaiImage(
        api_key="test", animation=AnimationOptions(4, 100), output_format="png",
        extra_parameters={"partial_images": 2, "prompt_rewriter": "auto", "output_compression": 50},
    )
    payload = provider._build_images_generation_payload(prompt="cat", model="gpt-image-2.6-flare", n=1)
    assert payload["output_format"] == "gif"
    assert payload["frame_count"] == 4 and payload["frame_duration_ms"] == 100
    for key in ("partial_images", "prompt_rewriter", "output_compression"):
        assert key not in payload


class GenerationProvider(OpenaiImage):
    def __init__(self, responses, **kwargs):
        super().__init__(api_key="test", **kwargs)
        self.responses, self.payloads = list(responses), []

    async def _post_json(self, url, payload):
        self.payloads.append(dict(payload))
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def test_sheet_rejection_falls_back_to_auto_size_before_acceptance() -> None:
    sheet = OpenAIRequestError(400, "invalid_value", "tools", "No supported sheet fits 2 GIF frames at size '1024x1024'")
    provider = GenerationProvider([sheet, {"data": [{"b64_json": b64(gif())}]}], animation=AnimationOptions(2))
    images = asyncio.run(provider.generate_images("cat", "gpt-image-2.6-flare"))
    assert images == [gif()]
    assert [payload["size"] for payload in provider.payloads] == ["1024x1024", "auto"]


def test_static_result_for_animated_request_fails_without_regenerating() -> None:
    provider = GenerationProvider([{"data": [{"b64_json": b64(image_bytes())}]}], animation=AnimationOptions())
    with pytest.raises(ProviderResultError, match="静态图片"):
        asyncio.run(provider.generate_images("cat", "gpt-image-2.6-flare"))
    assert len(provider.payloads) == 1


def test_chat_mode_rejects_animation_before_any_request() -> None:
    provider = GenerationProvider([], animation=AnimationOptions(), compatibility_mode="chat_completions")
    with pytest.raises(ValueError, match="GIF"):
        asyncio.run(provider.generate_images("cat", "gpt-image-2.6-flare"))
    assert provider.payloads == []


def test_edit_form_carries_frames_and_gif_source_is_first_frame() -> None:
    class Provider(OpenaiImage):
        forms = []

        async def _post_form(self, url, form):
            fields = {field[0]["name"]: field[2] for field in form._fields if not isinstance(field[2], bytes)}
            self.forms.append(fields | {"images": [field[2] for field in form._fields if isinstance(field[2], bytes)]})
            return {"data": [{"b64_json": b64(gif())}]}

    provider = Provider(api_key="test", animation=AnimationOptions(3, 80))
    images = asyncio.run(provider.edit_images("wave", "gpt-image-2.6-flare", [gif(4)]))
    assert images == [gif()]
    form = provider.forms[0]
    assert form["output_format"] == "gif" and str(form["frame_count"]) == "3"
    assert str(form["frame_duration_ms"]) == "80"
    source = form["images"][0]
    with Image.open(BytesIO(source)) as image:
        assert image.format == "PNG"


def test_gif_results_are_stored_with_static_preview(tmp_path) -> None:
    store = module("infrastructure.storage.results").ImageResultStore(tmp_path / "data")
    raw = gif()
    store.save("c" * 12, [raw])
    directory = tmp_path / "data" / "results" / ("c" * 12)
    assert (directory / "0.gif").read_bytes() == raw
    record = store.images("c" * 12)[0]
    assert record["mime"] == "image/gif"
    preview = store.preview("c" * 12)
    assert preview["data_url"].startswith("data:image/webp;base64,")


def test_gif_review_uses_contact_sheet_of_all_frames() -> None:
    config = DrawpicConfig()
    config.general.image_review_enabled = True
    llm = AsyncMock(return_value={"success": True, "response": "结论：PASS\n原因：fixture"})
    service = module("application.moderation").DrawpicModerationService(
        config, SimpleNamespace(llm=SimpleNamespace(generate=llm), logger=Mock())
    )
    result = asyncio.run(service.review_image("cat", gif(5, (40, 30))))
    assert result.passed
    part = llm.await_args.args[0][0]["content"][1]
    sheet = base64.b64decode(part["image_base64"])
    with Image.open(BytesIO(sheet)) as image:
        assert image.format == "PNG" and getattr(image, "n_frames", 1) == 1
        assert image.width == 4 * 40 and image.height == 2 * 30


async def gif_plugin(make_plugin, monkeypatch, models, fallback_models=()):
    plugin = make_plugin()
    await plugin.on_load()
    bootstrap = await plugin.workspace_bootstrap()
    provider = bootstrap["providers"][0]
    provider["config"]["models"] = list(models)
    await plugin.workspace_provider_save(
        json.dumps({key: provider[key] for key in ("id", "kind", "name", "config")}), bootstrap["revision"],
    )
    bootstrap = await plugin.workspace_bootstrap()
    values = bootstrap["settings"]
    values["general"].update(
        prompt_review_enabled=False, image_review_enabled=False, group_quota_enabled=False,
        private_quota_enabled=False, request_retry_count=0,
        fallback_models=[f"{provider['name']}/{model}" for model in fallback_models],
        default_model=f"{provider['name']}/{models[0]}",
    )
    await plugin.workspace_settings_save(json.dumps(values), bootstrap["revision"])
    service = plugin._require_draw_service()
    attempts = []

    async def generate(**kwargs):
        attempts.append(kwargs["attempt"])
        return [gif()]

    monkeypatch.setattr(service, "_run_image_request_attempt", generate)
    live = {"stream_id": "gif-stream", "user_id": "12345", "group_id": "67890", "platform": "qq"}
    monkeypatch.setattr(service.stream_service, "resolve_live_stream_context", AsyncMock(return_value=live))
    monkeypatch.setattr(service.stream_service, "send_text_with_fallback", AsyncMock(return_value=True))
    monkeypatch.setattr(service.stream_service, "send_generated_images_with_fallback", AsyncMock(return_value=1))
    return plugin, service, provider["name"], attempts


def test_v2_animated_submit_end_to_end_and_signature_compatibility(make_plugin, monkeypatch) -> None:
    async def run() -> None:
        plugin, service, name, attempts = await gif_plugin(make_plugin, monkeypatch, ["gpt-image-2.6-flare", "gpt-image-2"])
        try:
            refused = await plugin.drawpic_submit_v2(
                prompt="cat", model=f"{name}/gpt-image-2", animated=True, request_id="gif-refused-01",
            )
            assert refused["accepted"] is False and "GIF" in refused["error"]["message"]
            invalid = await plugin.drawpic_submit_v2(prompt="cat", frame_count=4, request_id="gif-invalid-01")
            assert invalid["accepted"] is False
            assert attempts == []

            plain = await plugin.drawpic_submit_v2(prompt="cat", request_id="gif-plain-0001")
            await asyncio.gather(*tuple(service.background_tasks))
            assert attempts[-1].animation is None and plain["accepted"]
            conflict = await plugin.drawpic_submit_v2(prompt="cat", request_id="gif-plain-0001", animated=True)
            assert conflict["error"]["code"] == "REQUEST_ID_CONFLICT"

            animated = await plugin.drawpic_submit_v2(
                prompt="cat", animated=True, frame_count=4, frame_duration_ms=100, request_id="gif-anim-0001",
            )
            await asyncio.gather(*tuple(service.background_tasks))
            assert attempts[-1].animation == AnimationOptions(4, 100)
            task = await plugin.drawpic_task_v2(animated["task_id"])
            assert task["status"] == "completed"
            assert task["images"][0]["format"] == "gif" and task["images"][0]["mime"] == "image/gif"
            reused = await plugin.drawpic_submit_v2(
                prompt="cat", animated=True, frame_count=4, frame_duration_ms=100, request_id="gif-anim-0001",
            )
            assert reused["reused"] is True
            catalog = {item["name"].rsplit("/", 1)[-1]: item for item in (await plugin.drawpic_models())["models"]}
            assert catalog["gpt-image-2.6-flare"]["animated_gif"] is True
            assert catalog["gpt-image-2"]["animated_gif"] is False and catalog["gpt-image-2"]["animated_gif_reason"]
        finally:
            await plugin.on_unload()

    asyncio.run(run())


def test_fallback_without_gif_support_is_skipped(make_plugin, monkeypatch) -> None:
    async def run() -> None:
        plugin, service, name, attempts = await gif_plugin(
            make_plugin, monkeypatch, ["gpt-image-2.6-flare", "gpt-image-2"], fallback_models=["gpt-image-2"],
        )
        try:
            async def fail(**kwargs):
                attempts.append(kwargs["attempt"])
                raise RuntimeError("primary failed")

            monkeypatch.setattr(service, "_run_image_request_attempt", fail)
            submitted = await plugin.drawpic_submit_v2(prompt="cat", animated=True, request_id="gif-fallback-01")
            await asyncio.gather(*tuple(service.background_tasks))
            task = await plugin.drawpic_task_v2(submitted["task_id"])
            assert task["status"] == "failed"
            assert [attempt.model.rsplit("/", 1)[-1] for attempt in attempts] == ["gpt-image-2.6-flare"]
        finally:
            await plugin.on_unload()

    asyncio.run(run())


def test_chat_tools_pass_animation_through(make_plugin, monkeypatch) -> None:
    async def run() -> None:
        plugin, service, name, attempts = await gif_plugin(make_plugin, monkeypatch, ["gpt-image-2.6-flare", "gpt-image-2"])
        try:
            context = dict(stream_id="gif-stream", user_id="12345", group_id="67890", platform="qq")
            result = await plugin.handle_draw(prompt="blinking cat", animated="true", frame_count="4", **context)
            assert result["success"], result
            await asyncio.gather(*tuple(service.background_tasks))
            assert attempts[-1].animation == AnimationOptions(4, None)

            result = await plugin.handle_styled_draw(prompt="blinking cat", animated=True, **context)
            assert result["success"], result
            await asyncio.gather(*tuple(service.background_tasks))
            assert attempts[-1].animation == AnimationOptions()

            bad = await plugin.handle_draw(prompt="cat", animated=True, frame_count=40, **context)
            assert not bad["success"] and "frame_count" in bad["message"]

            refused = await plugin.handle_edit_image(
                prompt="make it move", model=f"{name}/gpt-image-2", animated=True, **context,
            )
            assert not refused["success"]
            assert "GIF" in refused["message"] and "真实图片" not in refused["message"]
            assert len(attempts) == 2
        finally:
            await plugin.on_unload()

    asyncio.run(run())


def test_client_submits_animation_and_reads_gif_chunks(make_plugin, monkeypatch) -> None:
    from test_drawing_client import DrawingClient, LocalAPI

    async def run() -> None:
        plugin, service, name, attempts = await gif_plugin(make_plugin, monkeypatch, ["gpt-image-2.6-flare"])
        try:
            client = DrawingClient(LocalAPI(plugin), poll_interval=0.001)
            result = await client.generate(
                "cat", request_id="client-gif-0001", wait_seconds=5, animated=True, frame_count=4,
            )
            assert result.status == "completed" and attempts[-1].animation == AnimationOptions(4)
            assert result.images[0].data == gif()
            assert result.image_references[0]["format"] == "gif"
        finally:
            await plugin.on_unload()

    asyncio.run(run())


def test_resolve_animation_model_prefers_fallback_then_catalog() -> None:
    router = router_for(["gpt-image-2", "gpt-image-2.6-sunburst", "gpt-image-2.6-flare"])
    assert router.resolve_animation_model("gpt-image-2.6-sunburst") == "gpt-image-2.6-sunburst"
    assert router.resolve_animation_model("gpt-image-2") == "gpt-image-2.6-sunburst"
    router.config.general.fallback_models = ["gpt-image-2.6-flare"]
    assert router.resolve_animation_model("gpt-image-2") == "gpt-image-2.6-flare"
    assert router.resolve_animation_model("gpt-image-2", "chat_completions") == ""
    assert router_for(["gpt-image-2"]).resolve_animation_model("gpt-image-2") == ""


def test_unspecified_model_switches_to_gif_capable_model(make_plugin, monkeypatch) -> None:
    async def run() -> None:
        plugin, service, name, attempts = await gif_plugin(
            make_plugin, monkeypatch, ["gpt-image-2", "gpt-image-2.6-sunburst", "gpt-image-2.6-flare"],
            fallback_models=["gpt-image-2.6-flare"],
        )
        try:
            context = dict(stream_id="gif-stream", user_id="12345", group_id="67890", platform="qq")
            result = await plugin.handle_draw(prompt="blinking cat", animated=True, **context)
            assert result["success"], result
            await asyncio.gather(*tuple(service.background_tasks))
            assert attempts[-1].model == f"{name}/gpt-image-2.6-flare" and attempts[-1].is_fallback is False

            result = await plugin.handle_edit_image(
                prompt="make it move", source_image_base64=b64(gif(2)), animated=True, **context,
            )
            assert result["success"], result
            await asyncio.gather(*tuple(service.background_tasks))
            assert attempts[-1].model == f"{name}/gpt-image-2.6-flare"

            submitted = await plugin.drawpic_submit_v2(prompt="cat", animated=True, request_id="gif-switch-001")
            await asyncio.gather(*tuple(service.background_tasks))
            assert submitted["accepted"] and attempts[-1].model == f"{name}/gpt-image-2.6-flare"

            plain = await plugin.handle_draw(prompt="still cat", **context)
            assert plain["success"], plain
            await asyncio.gather(*tuple(service.background_tasks))
            assert attempts[-1].model == f"{name}/gpt-image-2" and attempts[-1].animation is None

            explicit = await plugin.handle_draw(prompt="cat", model=f"{name}/gpt-image-2", animated=True, **context)
            assert not explicit["success"] and f"{name}/gpt-image-2 " in explicit["message"]
            refused = await plugin.drawpic_submit_v2(
                prompt="cat", model=f"{name}/gpt-image-2", animated=True, request_id="gif-explicit-01",
            )
            assert refused["accepted"] is False and f"{name}/gpt-image-2 " in refused["error"]["message"]
            assert len(attempts) == 4
        finally:
            await plugin.on_unload()

    asyncio.run(run())


def test_workspace_submit_accepts_animation_fields(make_plugin, monkeypatch) -> None:
    async def run() -> None:
        plugin, service, name, attempts = await gif_plugin(make_plugin, monkeypatch, ["gpt-image-2.6-flare"])
        try:
            request = {"prompt": "blinking cat", "model": f"{name}/gpt-image-2.6-flare", "task_type": "draw",
                       "animated": True, "frame_count": 4, "request_id": "gif-workspace-01"}
            submitted = await plugin.workspace_submit(json.dumps(request))
            await asyncio.gather(*tuple(service.background_tasks))
            assert submitted.get("task_id"), submitted
            assert attempts[-1].animation == AnimationOptions(4, None)
            unknown = await plugin.workspace_submit(json.dumps({**request, "request_id": "gif-workspace-02", "fps": 3}))
            assert "未知参数" in json.dumps(unknown, ensure_ascii=False)
        finally:
            await plugin.on_unload()

    asyncio.run(run())
