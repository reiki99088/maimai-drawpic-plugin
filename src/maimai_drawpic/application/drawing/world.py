"""世界知识接入绘图流程：画前补充现实对象的外观描述与参考图，画后对照校验。

世界知识是参考体系的一个来源（见 references/world.py）：画前检索与原版素材准备并行，素材准备完成后
按原版额度补位加图；未启用、没有命中词条或检索出错时，请求与原流程逐字一致。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple
import asyncio

from ..knowledge.prompts import compose_world_prompt
from ..knowledge.service import WorldKnowledgeService, WorldResolution
from ..references.world import (
    MAX_SOURCE_IMAGES, MaterialFinder, covered_keys, select_world_images, world_material_finder,
)
from ...domain.models.animation import AnimationOptions
from ...domain.references import ReferenceImage
from ...infrastructure.storage.world_knowledge import entry_names
from .admission import update_task_owned
from .types import ImageRequestAttempt

# 这些平台把多张输入图当作参考图综合使用；NovelAI / ComfyUI 等会把参考图当底图重绘，只注入文字。
WORLD_REFERENCE_PROVIDERS = frozenset({"openai", "google", "codex", "volcengine"})
VERIFY_REFERENCE_IMAGES = 2
# 开了素材搜索时多读几张词条图：被素材覆盖的对象会被跳过，留出替补
COVERED_SPARE_IMAGES = 2


@dataclass
class WorldInjection:
    """素材准备后的请求加一次检索结果；按模型能保留的参考图张数生成实际请求。"""

    base_prompt: str
    user_images: List[bytes]
    user_urls: List[str]
    resolution: WorldResolution
    chosen: List[Tuple[str, bytes]] = field(default_factory=list)
    materials: List[ReferenceImage] = field(default_factory=list)
    kept_images: int = field(default=0)

    def request(self, keep: int) -> Tuple[str, List[bytes], List[str], str]:
        images = self.chosen[: max(0, keep)]
        offset = len(self.user_images)
        numbers = {entry_id: offset + index + 1 for index, (entry_id, _data) in enumerate(images)}
        suffix = compose_world_prompt(self.resolution.entries, numbers)
        prompt = f"{self.base_prompt}\n\n{suffix}" if suffix else self.base_prompt
        sources = [*self.user_images, *(data for _entry_id, data in images)]
        urls = [*self.user_urls, *([""] * len(images))]
        return prompt, sources, urls, "edit_image" if sources else "draw"

    def verification(self) -> WorldResolution:
        """校验依据：本次词条，加上原版按点名对象找到的素材（没有对应词条的才加）。"""
        check = WorldResolution(entries=list(self.resolution.entries), images=list(self.resolution.images))
        named = covered_keys(name for entry in check.entries for name in entry_names(entry))
        for index, image in enumerate(self.materials):
            keys = covered_keys([image.subject])
            if not keys or keys & named:
                continue
            entry_id = f"material-{index}"
            check.entries.append({"id": entry_id, "name": image.subject, "kind": "other", "look": "", "draw_hint": ""})
            check.images.append((entry_id, image.raw))
            named |= keys
        return check


class WorldKnowledgeMixin:
    world_knowledge_service: Optional[WorldKnowledgeService] = None

    def world_reference_slots(self, model: str, existing: int, animation: AnimationOptions | None) -> int:
        """该模型还能附加几张世界参考图；未知或不支持图生图时为 0，合并后总数不超过 8 张。"""
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
        slots = min(slots, MAX_SOURCE_IMAGES - existing)
        return max(0, slots)

    def world_material_finder(self, override: Optional[bool]) -> Optional[MaterialFinder]:
        """给原版素材准备用的词条库候选；世界知识未启用时为 None，素材准备与原版一致。"""
        service = self.world_knowledge_service
        if service is None or not service.enabled(override):
            return None
        return world_material_finder(service.store)

    def start_world_knowledge(
        self,
        *,
        task_id: str,
        prompt: str,
        model: str,
        source_count: int,
        animation: AnimationOptions | None,
        override: Optional[bool],
        spare_images: bool = False,
    ) -> Optional["asyncio.Task[WorldResolution]"]:
        """在后台开始画前检索，与素材准备并行；未启用时返回 None。检索本身有总时限，出错只记 warning。"""
        service = self.world_knowledge_service
        if service is None or not service.enabled(override):
            return None
        load = self.world_reference_slots(model, source_count, animation)
        if load and spare_images:
            load += COVERED_SPARE_IMAGES
        if service.general.world_knowledge_verify_enabled and animation is None:
            load = max(load, VERIFY_REFERENCE_IMAGES)  # 校验时即使模型不收参考图，也拿参考图对照

        async def progress(message: str) -> Any:
            return await update_task_owned(self.task_store, task_id, status="running", message=message)

        return asyncio.create_task(service.prepare(
            prompt, task_id=task_id, want_images=animation is None, max_images=load, progress=progress,
        ))

    async def finish_world_knowledge(
        self,
        pending: "asyncio.Task[WorldResolution]",
        *,
        task_id: str,
        prompt: str,
        model: str,
        source_images: List[bytes],
        source_urls: List[str],
        animation: AnimationOptions | None,
        materials: Sequence[ReferenceImage] = (),
        allow_images: bool = True,
    ) -> Optional[WorldInjection]:
        """素材准备完成后按原版额度挑词条图；allow_images=False（调用方要求文生图）时只注入文字。"""
        service = self.world_knowledge_service
        resolution = await pending
        slots = self.world_reference_slots(model, len(source_images), animation) if allow_images else 0
        chosen = select_world_images(
            resolution, existing=source_images, covered=[image.subject for image in materials], slots=slots,
        )
        injection = WorldInjection(
            prompt, list(source_images), list(source_urls), resolution, chosen=chosen, materials=list(materials),
            kept_images=len(chosen),
        )
        metadata = resolution.metadata()
        if resolution.entries:
            sent = {entry_id for entry_id, _data in chosen}
            for item in metadata["entries"]:
                item["image_used"] = item["id"] in sent
            metadata["reference_images_sent"] = len(chosen)
        if materials:
            metadata["material_subjects"] = [image.subject for image in materials][:8]
        await update_task_owned(
            self.task_store, task_id, status="running", message="世界知识检索完成", world_knowledge=metadata,
        )
        verify_materials = (
            bool(materials) and service is not None and service.general.world_knowledge_verify_enabled
            and animation is None
        )
        return injection if resolution.entries or verify_materials else None

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
        allow_images: bool = True,
    ) -> Optional[WorldInjection]:
        """不经过素材准备时的一步到位版本：检索完成后直接挑图。"""
        pending = self.start_world_knowledge(
            task_id=task_id, prompt=prompt, model=model, source_count=len(source_images), animation=animation,
            override=override,
        )
        if pending is None:
            return None
        return await self.finish_world_knowledge(
            pending, task_id=task_id, prompt=prompt, model=model, source_images=source_images,
            source_urls=source_urls, animation=animation, allow_images=allow_images,
        )

    async def verify_world_result(
        self,
        *,
        world: WorldInjection,
        task_id: str,
        images: List[bytes],
        attempt: ImageRequestAttempt,
        matched_message_id: str,
        request_negative_prompt: str,
        style_negative_prompt_template: str = "",
    ) -> List[bytes]:
        """对照本次词条校验成图；严重画错时用同一模型重画一次，留下偏差更小的一张。

        重画是新的生成请求而非失败重试：只做一次、不换模型、不额外扣次数；失败时保留原图。
        """
        service = self.world_knowledge_service
        if (
            service is None
            or not service.general.world_knowledge_verify_enabled
            or attempt.animation is not None
            or not images
        ):
            return images
        await update_task_owned(self.task_store, task_id, status="running", message="正在对照世界知识校验图片")
        check = world.verification()
        first = await service.verify(images[0], check, task_id=task_id)
        report: Dict[str, Any] = {
            "verdict": first.level, "checked": first.checked, "issues": self._clean_issues(first.issues),
            "redrawn": False, "kept": "original",
        }
        result = images
        if first.level == "SEVERE" and service.general.world_knowledge_redraw_enabled:
            keep = world.kept_images
            if attempt.is_fallback and keep:
                keep = min(
                    self.world_reference_slots(attempt.model, len(world.user_images), None),
                    len(world.chosen),
                )
            prompt, sources, urls, task_type = world.request(keep)
            correction = first.correction or "; ".join(first.issues) or "Match the reference designs exactly."
            prompt = f"{prompt}\n\n[Correction from review] {correction}"
            await update_task_owned(
                self.task_store, task_id, status="running", message="校验发现现实对象画错了，正在重画一次",
            )
            try:
                redrawn = await self._run_image_request_attempt(
                    attempt=attempt,
                    prompt=prompt,
                    task_id=task_id,
                    task_type=task_type,
                    source_image_bytes_list=sources,
                    source_image_urls=urls,
                    matched_message_id=matched_message_id,
                    request_negative_prompt=request_negative_prompt,
                    style_negative_prompt_template=style_negative_prompt_template,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                reason = self.task_store.sanitize_message(str(exc) or type(exc).__name__)[:160]
                report["redraw_error"] = reason
                self.ctx.logger.warning("世界知识重画失败，保留原图: task_id=%s reason=%s", task_id, reason)
            else:
                if redrawn:
                    second = await service.verify(redrawn[0], check, task_id=task_id)
                    report.update(
                        redrawn=True, redraw_verdict=second.level, redraw_checked=second.checked,
                        redraw_issues=self._clean_issues(second.issues),
                    )
                    if second.score <= first.score:  # 持平也留重画版：它带着修正说明
                        result = redrawn
                        report["kept"] = "redraw"
        await update_task_owned(
            self.task_store, task_id, status="running", message="世界知识校验完成",
            world_knowledge={"verify": report},
        )
        self.ctx.logger.info(
            "世界知识校验: task_id=%s verdict=%s checked=%s redrawn=%s redraw_verdict=%s kept=%s",
            task_id, report["verdict"], report["checked"], report["redrawn"], report.get("redraw_verdict", ""),
            report["kept"],
        )
        return result

    def _clean_issues(self, issues: Any) -> List[str]:
        return [self.task_store.sanitize_message(str(issue))[:80] for issue in list(issues)[:3]]
