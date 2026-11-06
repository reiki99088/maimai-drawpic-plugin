from dataclasses import dataclass

from ..routing import ProviderName
from ...domain.models.animation import AnimationOptions


@dataclass(frozen=True, slots=True)
class ImageRequestAttempt:
    """一次图片请求尝试使用的最终路由信息。"""

    model: str
    provider_name: ProviderName
    openai_compatibility_mode: str
    novelai_mode: str = ""
    novelai_artist_tags: str = ""
    is_fallback: bool = False
    animation: AnimationOptions | None = None
