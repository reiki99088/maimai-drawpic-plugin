"""GIF 动图输出的任务参数定义。"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

GIF_FRAME_COUNT_RANGE = (2, 16)
GIF_FRAME_DURATION_RANGE = (20, 2000)
# 上游 GIF 输出不接受这些参数；构造请求时移除，stream 仍由通用校验拒绝。
GIF_INCOMPATIBLE_PARAMETERS = ("partial_images", "output_compression", "prompt_rewriter")


@dataclass(frozen=True, slots=True)
class AnimationOptions:
    """未指定的帧参数不发送，交给上游默认值（9 帧、每帧 200 ms）。"""

    frame_count: Optional[int] = None
    frame_duration_ms: Optional[int] = None

    def request_fields(self) -> Dict[str, Any]:
        fields: Dict[str, Any] = {"output_format": "gif"}
        if self.frame_count is not None:
            fields["frame_count"] = self.frame_count
        if self.frame_duration_ms is not None:
            fields["frame_duration_ms"] = self.frame_duration_ms
        return fields

    def signature(self) -> Dict[str, Any]:
        return {"animated": True, "frame_count": self.frame_count, "frame_duration_ms": self.frame_duration_ms}

    def describe(self) -> str:
        frames = self.frame_count if self.frame_count is not None else "default"
        duration = self.frame_duration_ms if self.frame_duration_ms is not None else "default"
        return f"gif frames={frames} duration_ms={duration}"


def _parse_flag(value: Any, *, lenient: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if lenient and isinstance(value, str) and value.strip().lower() in {"true", "false", "1", "0", "yes", "no", ""}:
        return value.strip().lower() in {"true", "1", "yes"}
    raise ValueError("animated 必须是布尔值")


def _parse_int(value: Any, name: str, bounds: tuple[int, int], *, lenient: bool) -> Optional[int]:
    if value is None or (lenient and isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{name} 必须是整数")
    if isinstance(value, int):
        number = value
    elif lenient and isinstance(value, float) and value.is_integer():
        number = int(value)
    elif lenient and isinstance(value, str) and value.strip().lstrip("-").isdigit():
        number = int(value.strip())
    else:
        raise ValueError(f"{name} 必须是整数")
    low, high = bounds
    if not low <= number <= high:
        raise ValueError(f"{name} 应为 {low}～{high}")
    return number


def parse_animation_options(
    animated: Any = False,
    frame_count: Any = None,
    frame_duration_ms: Any = None,
    *,
    lenient: bool = False,
) -> Optional[AnimationOptions]:
    """API 严格校验类型；LLM 工具允许字符串形式的布尔值与数字。"""

    enabled = _parse_flag(animated, lenient=lenient)
    count = _parse_int(frame_count, "frame_count（动图帧数）", GIF_FRAME_COUNT_RANGE, lenient=lenient)
    duration = _parse_int(
        frame_duration_ms, "frame_duration_ms（每帧毫秒）", GIF_FRAME_DURATION_RANGE, lenient=lenient
    )
    if not enabled:
        if count is not None or duration is not None:
            raise ValueError("frame_count / frame_duration_ms 只在 animated=true 时有效")
        return None
    return AnimationOptions(frame_count=count, frame_duration_ms=duration)
