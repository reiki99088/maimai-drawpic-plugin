"""世界知识接入绘图流程：画前补充现实对象的外观描述与参考图。

世界知识只增强绘图：未启用、没有命中词条或检索出错时，请求与原流程逐字一致。
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

from ..knowledge.prompts import compose_world_prompt
from ..knowledge.service import WorldKnowledgeService, WorldResolution
from ...domain.models.animation import AnimationOptions
from .admission import update_task_owned

# 这些平台把多张输入图当作参考图综合使用；NovelAI / ComfyUI 等会把参考图当底图重绘，只注入文字。
WORLD_REFERENCE_PROVIDERS = frozenset({"openai", "google", "codex", "volcengine"})
VERIFY_REFERENCE_IMAGES = 2


@dataclass
class WorldInjection:
    """原始请求加一次检索结果；按模型能保留的参考图张数生成实际请求。"""

    base_prompt: str
    user_images: List[bytes]
    user_urls: List[str]
    resolution: WorldResolution
    kept_images: int = field(default=0)

    def request(self, keep: int) -> Tuple[str, List[bytes], List[str], str]:
        images = self.resolution.images[: max(0, keep)]
        offset = len(self.user_images)
        numbers = {entry_id: offset + index + 1 for index, (entry_id, _data) in enumerate(images)}
        suffix = compose_world_prompt(self.resolution.entries, numbers)
        prompt = f"{self.base_prompt}\n\n{suffix}" if suffix else self.base_prompt
        sources = [*self.user_images, *(data for _entry_id, data in images)]
        urls = [*self.user_urls, *([""] * len(images))]
        return prompt, sources, urls, "edit_image" if sources else "draw"


class WorldKnowledgeMixin:
    world_knowledge_service: Optional[WorldKnowledgeService] = None

    def world_reference_slots(self, model: str, existing: int, animation: AnimationOptions | None) -> int:
        """该模型还能附加几张世界参考图；未知或不支持图生图时为 0。"""
        service = self.world_knowledge_service
        if service is None or animation is not None:
            return 0
        slots = min(int(service.general.world_knowledge_max_reference_images), 2)
        if slots <= 0 or self.router.get_model_provider(model) not in WORLD_REFERENCE_PROVIDERS:
            return 0
        if not self.router.evaluate_model_task_capability(model, "edit_image").allowed:
            return 0
        maximum = self.router.get_max_source_images(model)
        if maximum is not None:
            slots = min(slots, maximum - existing)
        return max(0, slots)

    async def prepare_world_knowledge(
        self,
        *,
        task_id: str,
        prompt: str,
        model: str,
        source_images: List[bytes],
        source_urls: List[str],
        animation: AnimationOptions | None,
        override: Optional[bool],
    ) -> Optional[WorldInjection]:
        service = self.world_knowledge_service
        if service is None or not service.enabled(override):
            return None
        slots = self.world_reference_slots(model, len(source_images), animation)
        load = slots
        if service.general.world_knowledge_verify_enabled and animation is None:
            load = max(load, VERIFY_REFERENCE_IMAGES)  # 校验时即使模型不收参考图，也拿参考图对照

        async def progress(message: str) -> Any:
            return await update_task_owned(self.task_store, task_id, status="running", message=message)

        resolution = await service.prepare(
            prompt, task_id=task_id, want_images=animation is None, max_images=load, progress=progress,
        )
        injection = WorldInjection(prompt, list(source_images), list(source_urls), resolution)
        metadata = resolution.metadata()
        if resolution.entries:
            injection.kept_images = min(slots, len(resolution.images))
            sent = {entry_id for entry_id, _data in resolution.images[: injection.kept_images]}
            for item in metadata["entries"]:
                item["image_used"] = item["id"] in sent
            metadata["reference_images_sent"] = injection.kept_images
        await update_task_owned(
            self.task_store, task_id, status="running", message="世界知识检索完成", world_knowledge=metadata,
        )
        return injection if resolution.entries else None
