"""runtime/requests.py 的插件组件。"""

from typing import Any, Dict, Optional
import asyncio

from ..domain.task_errors import ModelAccessError, TaskRequestError
from .drawing.admission import wait_for_admission
from ..domain.models.animation import AnimationOptions


class RequestMixin:
    """runtime/requests.py 对应的插件行为。"""

    async def _start_background_image_request(
        self,
        *,
        prompt: str,
        stream_id: str,
        requested_model: str = "",
        requested_openai_compatibility_mode: str = "",
        request_negative_prompt: str = "",
        requested_novelai_mode: str = "",
        requested_novelai_artist_tags: Optional[str] = None,
        animation: Optional[AnimationOptions] = None,
        source_image_bytes_list: list[bytes] | None = None,
        source_image_urls: list[str] | None = None,
        matched_message_id: str = "",
        user_id: str = "",
        group_id: str = "",
        platform_name: str = "qq",
        notify_start: bool = True,
        defer_prompt_review: bool = False,
        submission: Optional[Dict[str, Any]] = None,
        restricted_models_allowed: Optional[bool] = None,
        announce_queue: bool = False,
    ) -> dict[str, Any]:
        """按当前会话设置启动后台绘图，源图为空时文生图，存在源图时图生图。

        restricted_models_allowed 为 None 时按请求用户的插件权限判断（与模型、次数管理相同的权限规则）；
        工作台等已鉴权入口可显式传入 True。
        """

        draw_service = self._require_draw_service()
        with draw_service.submission_scope():
            live_context = await draw_service.stream_service.resolve_live_stream_context(
                stream_id=stream_id,
                user_id=user_id,
                group_id=group_id,
                platform=platform_name,
            )
            runtime_context = self._merge_resolved_runtime_context(
                live_context,
                user_id=user_id,
                group_id=group_id,
                platform=platform_name,
            )
            resolved_stream_id = runtime_context["stream_id"]
            if not resolved_stream_id:
                raise TaskRequestError("STREAM_UNAVAILABLE", "当前聊天流不可用，无法回传图片")
            resolved_user_id = runtime_context["user_id"]
            resolved_group_id = runtime_context["group_id"]
            resolved_platform = runtime_context["platform"]
            normalized_source_images = source_image_bytes_list or []
            normalized_source_urls = source_image_urls or [""] * len(normalized_source_images)
            if len(normalized_source_urls) != len(normalized_source_images):
                raise ValueError("源图 URL 数量必须与源图数量一致")
            session_preference = self._get_session_preference(
                resolved_stream_id,
                resolved_user_id,
                resolved_group_id,
                resolved_platform,
            )
            resolved_model = draw_service.resolve_model_name(
                requested_model or session_preference["model"],
                allow_unknown_model=False,
            )
            # Preserve explicit overrides; each fallback instance owns its defaults.
            resolved_openai_mode = requested_openai_compatibility_mode or session_preference["openai_compatibility_mode"]
            resolved_novelai_mode = requested_novelai_mode or session_preference.get("novelai_mode", "")
            resolved_novelai_artist_tags = (
                session_preference.get("novelai_artist_tags", "")
                if requested_novelai_artist_tags is None else requested_novelai_artist_tags
            )
            provider_name = draw_service.router.get_model_provider(resolved_model)
            if not provider_name:
                raise ValueError(f"指定模型不可用：{resolved_model}")
            if restricted_models_allowed is None:
                can_manage = getattr(self, "_can_manage_session", None)
                restricted_allowed = bool(can_manage(resolved_user_id)) if can_manage is not None else False
            else:
                restricted_allowed = restricted_models_allowed
            requires_admin = getattr(draw_service.router, "model_requires_admin", None)
            if not restricted_allowed and requires_admin is not None and requires_admin(resolved_model):
                # 在审核与额度预留前拒绝，避免扣次数。
                self.ctx.logger.info(
                    "拒绝非管理员使用受限模型: model=%s provider=%s user_id=%s group_id=%s",
                    resolved_model,
                    provider_name,
                    resolved_user_id,
                    resolved_group_id,
                )
                raise ModelAccessError(f"模型 {resolved_model} 仅限插件管理员使用，请切换到其他模型")
            # 智能体平台队列已满时在审核与扣次数前拒绝；未满时记录排队位置用于回复。
            ensure_capacity = getattr(draw_service.router, "ensure_agent_capacity", None)
            queue_status = ensure_capacity(resolved_model) if ensure_capacity is not None else None
            task_type = "edit_image" if normalized_source_images else "draw"
            # 火山引擎使用统一模型列表，按模型名能力标记和全局黑名单提前校验。
            check_model = resolved_model
            if provider_name == "volcengine":
                try:
                    check_model = draw_service.router.resolve_volcengine_model_for_task(
                        resolved_model,
                        task_type,
                    )
                except ValueError:
                    check_model = resolved_model
            capability = draw_service.router.evaluate_model_task_capability(
                check_model,
                task_type,
            )
            if not capability.allowed:
                self.ctx.logger.warning(
                    "拒绝提交模型不支持的绘图任务: model=%s provider=%s task_type=%s "
                    "capability_source=%s source_image_count=%s reason=%s",
                    check_model,
                    provider_name,
                    task_type,
                    capability.source,
                    len(normalized_source_images),
                    capability.reason,
                )
                task_hint = "图生图" if task_type == "draw" else "文生图"
                raise ValueError(f"{capability.reason}。请改用 /绘图 {task_hint} <prompt>，或切换到支持当前任务的模型")

            animation_capability = draw_service.router.evaluate_model_animation_capability(
                check_model, resolved_openai_mode
            ) if animation is not None else None
            if animation_capability is not None and not animation_capability.allowed:
                self.ctx.logger.warning(
                    "拒绝提交不支持动图的绘图任务: model=%s provider=%s task_type=%s "
                    "capability_source=%s source_image_count=%s reason=%s",
                    check_model,
                    provider_name,
                    task_type,
                    animation_capability.source,
                    len(normalized_source_images),
                    animation_capability.reason,
                )
                raise ValueError(f"{animation_capability.reason}。请切换到支持 GIF 动图的模型，或去掉动图要求")
            draw_service.router.validate_source_image_count(check_model, len(normalized_source_images))
            if not defer_prompt_review:
                await draw_service.review_prompt_or_raise(prompt)
            reservation_task = asyncio.create_task(asyncio.to_thread(
                self._reserve_draw_quota,
                resolved_user_id,
                resolved_group_id,
                resolved_stream_id,
                return_reservation=True,
            ))

            async def settle_quota(operation, *args, **kwargs) -> None:
                async def settle() -> None:
                    for attempt in range(3):
                        try:
                            await asyncio.to_thread(operation, *args, **kwargs)
                            return
                        except OSError as exc:
                            if attempt == 2:
                                raise
                            self.ctx.logger.warning(
                                "绘图额度结算暂时失败，将重试同一凭据: attempt=%s error=%s", attempt + 1, exc
                            )
                            await asyncio.sleep(0.05 * (attempt + 1))

                # Cancellation cannot abandon a settlement, and retries only touch
                # the same idempotent reservation, never the provider request.
                await wait_for_admission(asyncio.create_task(settle()))

            async def refund(reservation, task_id: str = "") -> None:
                if reservation is not None:
                    await settle_quota(
                        self._refund_draw_quota,
                        reservation.quota_key,
                        resolved_group_id,
                        resolved_stream_id,
                        task_id,
                        reservation=reservation,
                    )

            try:
                quota_allowed, quota_message, reservation = await asyncio.shield(reservation_task)
            except asyncio.CancelledError:
                _, _, reservation = await wait_for_admission(reservation_task)
                await refund(reservation)
                raise
            if not quota_allowed:
                raise PermissionError(quota_message)

            async def _handle_task_unsuccessful(task_id: str, status: str, reason: str) -> None:
                await refund(reservation, task_id)
                await self._send_draw_failure_notice(
                    reason=reason,
                    stream_id=resolved_stream_id,
                    user_id=resolved_user_id,
                    group_id=resolved_group_id,
                    platform=resolved_platform,
                    task_id=task_id,
                    status=status,
                )

            async def _handle_task_successful(task_id: str, status: str, reason: str) -> None:
                if reservation is not None:
                    await settle_quota(self._commit_draw_quota, reservation)

            try:
                result = await draw_service.start_background_image_request(
                    prompt=prompt,
                    stream_id=resolved_stream_id,
                    resolved_model=resolved_model,
                    resolved_openai_mode=resolved_openai_mode,
                    provider_name=provider_name,
                    novelai_mode=resolved_novelai_mode,
                    novelai_artist_tags=resolved_novelai_artist_tags,
                    animation=animation,
                    request_negative_prompt=request_negative_prompt.strip(),
                    user_id=resolved_user_id,
                    group_id=resolved_group_id,
                    platform_name=resolved_platform,
                    source_image_bytes_list=normalized_source_images,
                    source_image_urls=normalized_source_urls,
                    matched_message_id=matched_message_id,
                    notify_start=notify_start,
                    prompt_reviewed=not defer_prompt_review,
                    on_task_unsuccessful=_handle_task_unsuccessful,
                    on_task_successful=_handle_task_successful,
                    submission=submission,
                    restricted_models_allowed=restricted_allowed,
                )
            except (Exception, asyncio.CancelledError):
                await refund(reservation)
                raise
        ahead = queue_status.ahead if queue_status is not None else 0
        if ahead > 0:
            result["queue_ahead"] = ahead
            result["message"] = (
                f"{result['message']}Codex 智能体正忙，本任务已排队，前面还有 {ahead} 个任务，"
                "轮到后才开始创作，完成后会自动发送；请告诉用户需要耐心等待。"
            )
            if announce_queue:
                await self._announce_queue(
                    draw_service, ahead, resolved_stream_id, resolved_user_id, resolved_group_id, resolved_platform
                )
        return result

    async def _announce_queue(
        self, draw_service: Any, ahead: int, stream_id: str, user_id: str, group_id: str, platform: str
    ) -> None:
        """聊天命令提交后告知排队位置；发送失败只记录日志，不影响已受理的任务。"""
        try:
            await draw_service.send_text_with_fallback(
                f"Codex 智能体正忙，你的绘图任务已排队（前面还有 {ahead} 个），轮到后开始创作，完成后会自动发送。",
                stream_id,
                user_id,
                group_id,
                platform,
            )
        except Exception as exc:
            self.ctx.logger.warning("排队提示发送失败: stream_id=%s error_type=%s", stream_id, type(exc).__name__)
