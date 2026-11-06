"""OpenAI Responses 后台提交与轮询；全部为内存模拟，不调用真实服务。"""

from io import BytesIO
from typing import Any, Dict, List

from PIL import Image

import asyncio
import base64
import logging
import pytest

from test_config_i18n import _bootstrap_plugin_package

_bootstrap_plugin_package()

from maimai_drawpic_pkg.src.maimai_drawpic.application.routing import ProviderRouter  # noqa: E402
from maimai_drawpic_pkg.src.maimai_drawpic.domain.configuration.models import DrawpicConfig  # noqa: E402
from maimai_drawpic_pkg.src.maimai_drawpic.domain.errors import (  # noqa: E402
    ProviderResultError,
    ProviderSubmittedError,
)
from maimai_drawpic_pkg.src.maimai_drawpic.domain.models.openai_profiles import (  # noqa: E402
    RESPONSES_IMAGE_INSTRUCTIONS,
    build_responses_image_payload,
    normalize_openai_request_mode,
)
from maimai_drawpic_pkg.src.maimai_drawpic.infrastructure.providers.openai import (  # noqa: E402
    OpenAIRequestError,
    OpenaiImage,
)


def png(size=(64, 48), color="#c8788c") -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, "PNG")
    return buffer.getvalue()


def gif(frames: int = 3, size=(32, 32)) -> bytes:
    buffer = BytesIO()
    images = [Image.new("RGB", size, (40 * index, 80, 120)) for index in range(frames)]
    images[0].save(buffer, "GIF", save_all=True, append_images=images[1:], duration=100, loop=0)
    return buffer.getvalue()


def completed(image: bytes, response_id: str = "resp_1", revised: str = "") -> Dict[str, Any]:
    return {
        "id": response_id,
        "status": "completed",
        "output": [
            {
                "type": "image_generation_call",
                "status": "completed",
                "revised_prompt": revised,
                "result": base64.b64encode(image).decode("ascii"),
            },
            {"type": "message", "content": [{"type": "output_text", "text": ""}]},
        ],
    }


class FakeResponses(OpenaiImage):
    """记录提交、查询与取消；队列中的 Exception 会在对应调用时抛出。"""

    def __init__(self, posts: List[Any], gets: List[Any] | None = None, **kwargs: Any) -> None:
        kwargs.setdefault("request_mode", "responses_background")
        kwargs.setdefault("responses_poll_interval_seconds", 0)
        super().__init__(api_key="sk-test-secret", **kwargs)
        self.post_queue, self.get_queue = list(posts), list(gets or [])
        self.posted: List[Dict[str, Any]] = []
        self.post_urls: List[str] = []
        self.get_urls: List[str] = []
        self.cancelled: List[str] = []

    async def _post_json(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.post_urls.append(url)
        self.posted.append(payload)
        item = self.post_queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    async def _get_json(self, url: str) -> Dict[str, Any]:
        self.get_urls.append(url)
        item = self.get_queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        if callable(item):
            return await item()
        return item

    async def _cancel_response(self, response_id: str) -> None:
        self.cancelled.append(response_id)


def test_request_mode_normalization_and_payload_shape() -> None:
    assert normalize_openai_request_mode(" Responses_Background ") == "responses_background"
    assert normalize_openai_request_mode("unknown") == "images"
    payload = build_responses_image_payload(
        main_model="gpt-5.4-mini",
        image_model="gpt-image-2.6-flare",
        prompt="一只猫",
        tool_parameters={
            "model": "x", "prompt": "x", "n": 1, "response_format": "b64_json", "stream": False,
            "partial_images": 2, "user": "u", "size": "1024x1536", "background": "transparent",
            "quality": "low", "output_format": "gif", "frame_count": 4,
        },
        source_image_data_urls=["data:image/png;base64,AAAA"],
    )
    assert payload["model"] == "gpt-5.4-mini"
    assert payload["background"] is True and payload["store"] is True
    assert payload["instructions"] == RESPONSES_IMAGE_INSTRUCTIONS
    assert payload["tool_choice"] == {"type": "image_generation"}
    assert payload["tools"] == [{
        "type": "image_generation", "model": "gpt-image-2.6-flare", "size": "1024x1536",
        "background": "transparent", "quality": "low", "output_format": "gif", "frame_count": 4,
    }]
    assert payload["input"] == [{"role": "user", "content": [
        {"type": "input_text", "text": "一只猫"},
        {"type": "input_image", "image_url": "data:image/png;base64,AAAA"},
    ]}]


def test_generate_polls_same_response_and_logs_status_changes(caplog) -> None:
    result = png()
    logger = logging.getLogger("drawpic.test.responses")
    provider = FakeResponses(
        [{"id": "resp_1", "status": "queued"}],
        [{"id": "resp_1", "status": "queued"}, {"id": "resp_1", "status": "in_progress"},
         {"id": "resp_1", "status": "in_progress"}, completed(result, revised="一只猫")],
        logger=logger, quality="low",
    )
    with caplog.at_level(logging.INFO, logger="drawpic.test.responses"):
        images = asyncio.run(provider.generate_images("一只猫", "gpt-image-2.6-flare"))
    assert images == [result]
    assert provider.post_urls == ["https://api.openai.com/v1/responses"]
    assert provider.get_urls == ["https://api.openai.com/v1/responses/resp_1"] * 4
    assert provider.posted[0]["tools"][0]["quality"] == "low"
    changes = [record.getMessage() for record in caplog.records if "状态变化" in record.getMessage()]
    assert len(changes) == 2 and "to=in_progress" in changes[0] and "to=completed" in changes[1]
    text = caplog.text
    assert base64.b64encode(result).decode("ascii")[:40] not in text
    assert "sk-test-secret" not in text


def test_completed_on_submit_skips_polling() -> None:
    result = png()
    provider = FakeResponses([completed(result)])
    assert asyncio.run(provider.generate_images("cat", "gpt-image-2")) == [result]
    assert provider.get_urls == []


def test_edit_sends_data_urls_and_gif_sources_become_first_frame_png() -> None:
    result = png()
    provider = FakeResponses([completed(result)])
    asyncio.run(provider.edit_images("edit", "gpt-image-2", [png((1536, 1024)), gif()]))
    content = provider.posted[0]["input"][0]["content"]
    assert content[0] == {"type": "input_text", "text": "edit"}
    assert [part["type"] for part in content[1:]] == ["input_image", "input_image"]
    assert content[1]["image_url"].startswith("data:image/png;base64,")
    second = base64.b64decode(content[2]["image_url"].split(",", 1)[1])
    with Image.open(BytesIO(second)) as image:
        assert image.format == "PNG" and getattr(image, "n_frames", 1) == 1
    # 源图横版时首选源图比例尺寸。
    assert provider.posted[0]["tools"][0]["size"] == "1536x1024"


def test_size_rejection_retries_before_acceptance_only() -> None:
    result = png()
    rejection = OpenAIRequestError(400, "invalid_value", "tools[0].size", "bad size")
    provider = FakeResponses([rejection, completed(result)])
    asyncio.run(provider.edit_images("edit", "gpt-image-2", [png((1536, 1024))]))
    assert [payload["tools"][0]["size"] for payload in provider.posted] == ["1536x1024", "1024x1024"]


def test_non_size_rejection_is_not_resubmitted() -> None:
    provider = FakeResponses([OpenAIRequestError(429, "rate_limit_exceeded", "", "slow down")])
    with pytest.raises(OpenAIRequestError):
        asyncio.run(provider.generate_images("cat", "gpt-image-2"))
    assert len(provider.posted) == 1


@pytest.mark.parametrize("status,body", [
    ("failed", {"error": {"code": "server_error", "message": "boom"}}),
    ("incomplete", {"incomplete_details": {"reason": "max_output_tokens"}}),
    ("cancelled", {}),
])
def test_terminal_failure_is_submitted_error_without_resubmit(status: str, body: Dict[str, Any]) -> None:
    provider = FakeResponses([{"id": "resp_9", "status": "queued"}], [{"id": "resp_9", "status": status, **body}])
    with pytest.raises(ProviderSubmittedError) as captured:
        asyncio.run(provider.generate_images("cat", "gpt-image-2"))
    assert captured.value.remote_task_id == "resp_9"
    assert not captured.value.retryable and not captured.value.allow_fallback
    assert len(provider.posted) == 1


def test_moderation_failure_stays_rejected() -> None:
    provider = FakeResponses(
        [{"id": "resp_m", "status": "queued"}],
        [{"id": "resp_m", "status": "failed", "error": {"code": "moderation_blocked", "message": "blocked"}}],
    )
    with pytest.raises(OpenAIRequestError) as captured:
        asyncio.run(provider.generate_images("cat", "gpt-image-2"))
    assert captured.value.rejected and captured.value.remote_task_id == "resp_m"
    assert len(provider.posted) == 1


def test_poll_disconnect_reuses_same_id_then_gives_up_as_unknown() -> None:
    disconnects = [TimeoutError("poll timeout") for _ in range(3)]
    provider = FakeResponses([{"id": "resp_d", "status": "queued"}], disconnects)
    with pytest.raises(ProviderSubmittedError) as captured:
        asyncio.run(provider.generate_images("cat", "gpt-image-2"))
    assert provider.get_urls == ["https://api.openai.com/v1/responses/resp_d"] * 3
    assert captured.value.remote_task_id == "resp_d" and captured.value.outcome_unknown
    assert len(provider.posted) == 1


def test_poll_disconnect_recovers_on_same_id() -> None:
    result = png()
    provider = FakeResponses(
        [{"id": "resp_r", "status": "queued"}],
        [TimeoutError("poll timeout"), completed(result, "resp_r")],
    )
    assert asyncio.run(provider.generate_images("cat", "gpt-image-2")) == [result]
    assert len(provider.posted) == 1 and len(provider.get_urls) == 2


def test_cancellation_and_outer_timeout_send_cancel() -> None:
    async def hang() -> Dict[str, Any]:
        await asyncio.Event().wait()
        return {}

    provider = FakeResponses([{"id": "resp_c", "status": "queued"}], [hang])

    async def run() -> None:
        await asyncio.wait_for(provider.generate_images("cat", "gpt-image-2"), timeout=0.2)

    with pytest.raises(TimeoutError):
        asyncio.run(run())
    assert provider.cancelled == ["resp_c"]
    assert len(provider.posted) == 1


@pytest.mark.parametrize("accepted,gets,message", [
    ({"status": "queued"}, [], "缺少 id"),
    ({"id": "resp_u", "status": "queued"}, [{"id": "resp_u", "status": "weird"}], "未知状态"),
    ({"id": "resp_e", "status": "completed", "output": [
        {"type": "message", "content": [{"type": "output_text", "text": "I can't"}]}]}, [], "没有图片结果"),
])
def test_missing_id_unknown_status_and_empty_output(accepted, gets, message) -> None:
    provider = FakeResponses([accepted], gets)
    with pytest.raises((ProviderResultError, ProviderSubmittedError)) as captured:
        asyncio.run(provider.generate_images("cat", "gpt-image-2"))
    assert message in str(captured.value)
    assert len(provider.posted) == 1


@pytest.mark.parametrize("kwargs,model", [
    ({"compatibility_mode": "chat_completions"}, "gpt-image-2"),
    ({}, "dall-e-3"),
    ({"request_mode": "images"}, "gpt-image-2"),
])
def test_other_modes_and_models_keep_direct_images_api(kwargs, model) -> None:
    provider = FakeResponses([{"data": [{"b64_json": base64.b64encode(png()).decode("ascii")}]}], **kwargs)
    if kwargs.get("compatibility_mode") == "chat_completions":
        provider.post_queue = [{"choices": [{"message": {"content": "![x](data:image/png;base64,"
                                                          + base64.b64encode(png()).decode("ascii") + ")"}}]}]
    asyncio.run(provider.generate_images("cat", model))
    assert all(not url.endswith("/responses") for url in provider.post_urls)


def test_config_reaches_provider_and_interval_is_clamped() -> None:
    config = DrawpicConfig()
    config.openai.models = ["gpt-image-2.6-flare"]
    config.openai.request_mode = "responses_background"
    config.openai.responses_main_model = "gpt-5.4"
    config.openai.responses_poll_interval_seconds = 0.2
    validated = DrawpicConfig.model_validate(config.model_dump(mode="json"))
    assert validated.openai.responses_poll_interval_seconds == 1
    assert DrawpicConfig.model_validate(
        {**config.model_dump(mode="json"), "openai": {**config.openai.model_dump(mode="json"),
                                                       "responses_poll_interval_seconds": 99}}
    ).openai.responses_poll_interval_seconds == 30
    routed = ProviderRouter(validated).create_openai_provider("images_api", "gpt-image-2.6-flare")
    assert routed.provider.request_mode == "responses_background"
    assert routed.provider.responses_main_model == "gpt-5.4"
    assert routed.provider.responses_poll_interval_seconds == 1
    defaults = DrawpicConfig().openai
    assert (defaults.request_mode, defaults.responses_main_model, defaults.responses_poll_interval_seconds) == (
        "images", "gpt-5.4-mini", 3.0,
    )
