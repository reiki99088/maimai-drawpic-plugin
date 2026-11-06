"""OpenAI / New API 兼容模式与聊天绘图请求定义。"""

from typing import Any, Dict, List, Literal, Optional
import re


OpenAICompatibilityMode = Literal["auto", "images_api", "chat_completions", "rinkoai"]
OPENAI_COMPATIBILITY_MODES = {"auto", "images_api", "chat_completions", "rinkoai"}


def normalize_openai_mode(mode: str) -> str:
    """删除的 NovelAI Images 模式迁移到 RinkoAI，聊天模式独立保留。"""

    normalized = mode.strip().lower()
    if normalized in {"novelai_images_api", "rinkoai兼容", "rinkoai 兼容"}:
        return "rinkoai"
    return normalized


def uses_newapi_image_chat(model: str) -> bool:
    """New API 的 Gemini 图片模型自动走聊天协议，其他模型保持 Images API。"""

    normalized = model.strip().lower()
    return normalized.startswith("gemini-") and "image" in normalized


def select_auto_modes(model: str, endpoint_types: Optional[List[str]]) -> List[str]:
    """优先使用 New API 模型元数据；缺少元数据时按已知模型系列排序。"""

    modes = ["chat_completions", "images_api"] if uses_newapi_image_chat(model) else ["images_api", "chat_completions"]
    if endpoint_types:
        supported = set(endpoint_types)
        modes = [
            mode for mode in modes if ("openai" if mode == "chat_completions" else "image-generation") in supported
        ]
        if not modes:
            raise ValueError(
                f"模型 {model} 公布的端点不支持 Images API 或 Chat Completion；请切换模型或使用对应原生平台配置"
            )
    return modes


def is_endpoint_unsupported(status: int, code: str, message: str) -> bool:
    """仅确定的路由错误允许切换端点，模型/鉴权/配额错误不能重试。"""

    normalized_code = code.strip().lower()
    if normalized_code in {"unsupported_endpoint", "route_not_found", "method_not_allowed", "not_implemented"}:
        return status in {400, 404, 405, 501}
    if normalized_code:
        return False
    normalized_message = message.strip().lower()
    if "model" in normalized_message or "模型" in normalized_message:
        return False
    if status in {405, 501}:
        return True
    return status == 404 and (
        normalized_message in {"404 page not found", "not found", "404 not found"}
        or "route not found" in normalized_message
        or "cannot post /" in normalized_message
    )


def build_newapi_chat_payload(
    prompt: str,
    model: str,
    n: int,
    extra_parameters: Dict[str, Any],
    source_image_data_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """使用 New API 的标准 OpenAI 消息协议，不混发 Gemini 原生字段。"""

    content: Any = prompt
    if source_image_data_urls:
        content = [{"type": "text", "text": prompt}]
        content.extend({"type": "image_url", "image_url": {"url": data_url}} for data_url in source_image_data_urls)
    payload = dict(extra_parameters)
    payload.pop("contents", None)
    payload.pop("n", None)
    payload.update(
        {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "stream": False,
        }
    )
    if n > 1:
        payload["n"] = n
    return payload


_GIF_MODEL_PATTERN = re.compile(r"^gpt-image-2\.6(?:$|[-_.])", re.IGNORECASE)
GIF_MODE_UNSUPPORTED_REASON = "GIF 动图需要 Images API 或 Responses 后台模式，聊天绘图/RinkoAI 接口无法输出动图"


def supports_gif_output(upstream_model: str) -> bool:
    """目前只有 gpt-image-2.6 系列支持 output_format=gif。"""

    return bool(_GIF_MODEL_PATTERN.match(upstream_model.strip()))


OpenAIRequestMode = Literal["images", "responses_background"]
RESPONSES_IMAGE_INSTRUCTIONS = (
    "Call image_generation exactly once, passing the user's prompt verbatim; do not rewrite, translate or add text."
)
RESPONSES_PENDING_STATUSES = frozenset({"queued", "in_progress"})
RESPONSES_FAILED_STATUSES = frozenset({"failed", "cancelled", "incomplete"})
# 图片工具只接受图像参数；顶层请求字段与流式参数不得混入 tools[]。
_RESPONSES_TOOL_EXCLUDED = frozenset({"model", "prompt", "n", "response_format", "stream", "partial_images", "user"})


def normalize_openai_request_mode(value: Any) -> str:
    return "responses_background" if str(value or "").strip().lower() == "responses_background" else "images"


def build_responses_image_payload(
    *,
    main_model: str,
    image_model: str,
    prompt: str,
    tool_parameters: Dict[str, Any],
    source_image_data_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """工具内 background 是透明度参数，顶层 background=True 才是后台模式，二者不得混用。"""

    tool = {key: value for key, value in tool_parameters.items() if key not in _RESPONSES_TOOL_EXCLUDED}
    tool.update({"type": "image_generation", "model": image_model})
    content: List[Dict[str, Any]] = [{"type": "input_text", "text": prompt}]
    content.extend({"type": "input_image", "image_url": data_url} for data_url in source_image_data_urls or [])
    return {
        "model": main_model,
        "background": True,
        "store": True,
        "instructions": RESPONSES_IMAGE_INSTRUCTIONS,
        "input": [{"role": "user", "content": content}],
        "tools": [tool],
        "tool_choice": {"type": "image_generation"},
    }
