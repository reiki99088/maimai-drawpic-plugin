from typing import Any
import asyncio
import inspect

from ...infrastructure.media.collection import validate_result_images
from ...infrastructure.http import sanitize_provider_text
from ...infrastructure.providers.codex import CodexRunRequest
from .admission import update_task_owned, wait_for_admission
from .types import ImageRequestAttempt


class RequestPlanningMixin:
    """RequestPlanningMixin 的独立绘图职责。"""

    async def run_provider_call(self, call: Any, *args: Any, timeout_seconds: int | None = None) -> list[bytes]:
        """执行图片请求，并按插件配置控制后台任务超时。"""

        if timeout_seconds is None:
            timeout_seconds = self.resolve_request_timeout_seconds()

        if inspect.iscoroutinefunction(call):
            image_bytes_list = await asyncio.wait_for(call(*args), timeout=timeout_seconds)
        else:
            # Cancelling the asyncio wrapper cannot stop an SDK thread. Keep this
            # drawing task (and its quota/capacity) alive until the worker exits.
            pending = asyncio.create_task(asyncio.to_thread(call, *args))
            try:
                image_bytes_list = await asyncio.wait_for(asyncio.shield(pending), timeout=timeout_seconds)
            except (asyncio.CancelledError, TimeoutError):
                try:
                    await wait_for_admission(pending)
                except Exception:
                    pass  # Retrieve worker failure, but preserve cancellation/timeout.
                raise
        # 解码大图会占用 CPU，必须在线程中校验，避免阻塞其他会话的任务。
        return await asyncio.to_thread(validate_result_images, image_bytes_list)

    def _build_image_request_attempt(
        self,
        *,
        model: str,
        task_type: str,
        openai_compatibility_mode: str,
        novelai_mode: str = "",
        novelai_artist_tags: str = "",
        is_fallback: bool = False,
    ) -> ImageRequestAttempt:
        """构建一次图片请求尝试的最终模型与提供商信息。"""

        provider_name = self.router.get_model_provider(model)
        if not provider_name:
            raise ValueError(f"指定模型不可用：{model}")

        effective_model = model
        if provider_name == "volcengine":
            effective_model = self.router.resolve_volcengine_model_for_task(model, task_type)
        elif provider_name == "novelai":
            novelai_mode = self.router.resolve_novelai_mode_for_model(model, novelai_mode)
            effective_model = self.router.resolve_novelai_model_for_mode(model, novelai_mode)
            provider_name = self.router.get_model_provider(effective_model)
            if provider_name != "novelai":
                raise ValueError(
                    f"NovelAI {novelai_mode} 模式需要模型 "
                    f"{effective_model}，请先在 novelai.models 中启用该模型"
                )
            if effective_model != model:
                self.ctx.logger.info(
                    "NovelAI V3 模型按 mode 自动切换: original_model=%s effective_model=%s mode=%s is_fallback=%s",
                    model,
                    effective_model,
                    novelai_mode,
                    is_fallback,
                )

        capability = self.router.evaluate_model_task_capability(
            effective_model,
            task_type,
        )
        if not capability.allowed:
            self.ctx.logger.warning(
                "拒绝构建不支持的绘图尝试: model=%s provider=%s task_type=%s "
                "capability_source=%s reason=%s is_fallback=%s",
                effective_model,
                provider_name,
                task_type,
                capability.source,
                capability.reason,
                is_fallback,
            )
            task_hint = "图生图" if task_type == "draw" else "文生图"
            raise ValueError(f"{capability.reason}。请改用{task_hint}，或切换到支持当前任务的模型")

        return ImageRequestAttempt(
            model=effective_model,
            provider_name=provider_name,
            openai_compatibility_mode=self.router.resolve_openai_compatibility_mode(
                openai_compatibility_mode,
                effective_model,
            ),
            novelai_mode=(
                self.router.resolve_novelai_mode_for_model(effective_model, novelai_mode)
                if provider_name == "novelai"
                else ""
            ),
            novelai_artist_tags=(
                self.router.resolve_novelai_artist_tags_for_model(effective_model, novelai_artist_tags)
                if provider_name == "novelai"
                else ""
            ),
            is_fallback=is_fallback,
        )

    def _build_fallback_image_request_attempt(
        self,
        *,
        primary_model: str,
        primary_effective_model: str,
        task_type: str,
        openai_compatibility_mode: str,
        novelai_mode: str = "",
        novelai_artist_tags: str = "",
        fallback_model: str = "",
    ) -> ImageRequestAttempt | None:
        """在首选模型失败后构建备选模型请求。"""

        fallback_model = fallback_model or self.router.resolve_fallback_model(primary_model)
        if not fallback_model:
            return None

        try:
            fallback_attempt = self._build_image_request_attempt(
                model=fallback_model,
                task_type=task_type,
                openai_compatibility_mode=openai_compatibility_mode,
                novelai_mode=novelai_mode,
                novelai_artist_tags=novelai_artist_tags,
                is_fallback=True,
            )
        except Exception as exc:
            self.ctx.logger.warning(
                "生图备选模型解析失败，跳过备选尝试: primary_model=%s fallback_model=%s task_type=%s error=%s",
                primary_model,
                fallback_model,
                task_type,
                exc,
            )
            return None

        if fallback_attempt.model == primary_effective_model:
            self.ctx.logger.warning(
                "生图备选模型与首选模型最终解析结果相同，跳过备选尝试: primary_model=%s fallback_model=%s effective_model=%s",
                primary_model,
                fallback_model,
                fallback_attempt.model,
            )
            return None

        return fallback_attempt

    async def _run_image_request_attempt(
        self,
        *,
        attempt: ImageRequestAttempt,
        prompt: str,
        task_id: str,
        task_type: str,
        source_image_bytes_list: list[bytes],
        source_image_urls: list[str],
        matched_message_id: str,
        request_negative_prompt: str = "",
    ) -> list[bytes]:
        """执行单次图片请求尝试。"""

        provider_name = attempt.provider_name
        if task_type == "edit_image":
            self.router.validate_source_image_count(attempt.model, len(source_image_bytes_list))
        provider_prompt = prompt
        provider_negative_prompt = request_negative_prompt.strip()
        supports_negative_prompt = self.router.supports_separate_negative_prompt(
            attempt.model,
            task_type,
        )
        if provider_negative_prompt and not supports_negative_prompt:
            provider_prompt = self.router.merge_prompt_parts(
                provider_prompt,
                f"Negative prompt: {provider_negative_prompt}",
            )
            provider_negative_prompt = ""
        provider_prompt = await self.rewrite_prompt_to_english_if_needed(
            provider_prompt,
            provider_name,
            attempt.model,
        )
        if provider_negative_prompt:
            provider_negative_prompt = await self.rewrite_prompt_to_english_if_needed(
                provider_negative_prompt,
                provider_name,
                attempt.model,
            )
        image_platform, provider_name = self.router.require_platform_for_model(
            attempt.model,
            attempt.openai_compatibility_mode,
            request_negative_prompt=provider_negative_prompt,
            novelai_mode=attempt.novelai_mode,
            novelai_artist_tags=attempt.novelai_artist_tags,
        )

        if provider_name == "codex":
            return await self._run_codex_attempt(
                attempt=attempt,
                image_platform=image_platform,
                prompt=provider_prompt,
                task_id=task_id,
                task_type=task_type,
                source_image_bytes_list=source_image_bytes_list if task_type == "edit_image" else [],
            )

        if task_type == "edit_image":
            self.ctx.logger.info(
                "开始绘图任务尝试: task_id=%s task_type=%s provider=%s model=%s is_fallback=%s source_image_count=%s source_image_bytes_lengths=%s matched_message_id=%s prompt=%s",
                task_id,
                task_type,
                provider_name,
                attempt.model,
                attempt.is_fallback,
                len(source_image_bytes_list),
                [len(image_bytes) for image_bytes in source_image_bytes_list],
                matched_message_id,
                provider_prompt[:120],
            )
            if provider_name == "aliyun":
                return await self.run_provider_call(
                    image_platform.edit_images_with_urls,
                    provider_prompt,
                    attempt.model,
                    source_image_bytes_list,
                    source_image_urls,
                    1,
                )
            return await self.run_provider_call(
                image_platform.edit_images,
                provider_prompt,
                attempt.model,
                source_image_bytes_list,
                1,
            )

        self.ctx.logger.info(
            "开始绘图任务尝试: task_id=%s task_type=%s provider=%s model=%s is_fallback=%s source_image_count=0 prompt=%s",
            task_id,
            task_type,
            provider_name,
            attempt.model,
            attempt.is_fallback,
            provider_prompt[:120],
        )
        return await self.run_provider_call(
            image_platform.generate_images,
            provider_prompt,
            attempt.model,
            1,
        )

    async def _run_codex_attempt(
        self,
        *,
        attempt: ImageRequestAttempt,
        image_platform: Any,
        prompt: str,
        task_id: str,
        task_type: str,
        source_image_bytes_list: list[bytes],
    ) -> list[bytes]:
        """执行 Codex 智能体任务；图生图源图来自本平台近期结果时接续原会话。"""

        settings = image_platform.agent_settings
        store = getattr(self, "agent_threads", None)
        record = self.task_store.get_task(task_id)
        session_key = record.session_key if record is not None else ""
        instance = self.router.describe_model(attempt.model).get("platform_name", "")
        resume = None
        if store is not None and settings.resume_enabled and source_image_bytes_list:
            try:
                resume = await asyncio.to_thread(
                    store.find,
                    instance=instance,
                    session_key=session_key,
                    images=source_image_bytes_list,
                    retention_days=settings.thread_retention_days,
                )
            except Exception as exc:
                self.ctx.logger.warning("Codex 会话匹配失败，改为新会话: task_id=%s error=%s", task_id, type(exc).__name__)
        work_dir = resume.work_dir if resume is not None else (
            store.new_work_dir() if store is not None else getattr(image_platform, "provider", image_platform).new_work_dir()
        )
        self.ctx.logger.info(
            "开始绘图任务尝试: task_id=%s task_type=%s provider=codex model=%s is_fallback=%s source_image_count=%s resume_thread=%s prompt=%s",
            task_id,
            task_type,
            attempt.model,
            attempt.is_fallback,
            len(source_image_bytes_list),
            resume.thread_id if resume is not None else "",
            prompt[:120],
        )
        running_message = "Codex 智能体正在接续原会话调整图片" if resume is not None else "Codex 智能体正在检索资料并创作"

        async def on_queue(ahead: int) -> None:
            # 排队与开始运行分别写入任务状态，查询进度时不会把排队误报为正在创作。
            if ahead > 0:
                message = f"Codex 智能体正忙，排队中，前面还有 {ahead} 个任务"
                self.ctx.logger.info("Codex 任务排队: task_id=%s ahead=%s", task_id, ahead)
            else:
                message = running_message
            await update_task_owned(self.task_store, task_id, status="running", message=message)

        request = CodexRunRequest(
            prompt=prompt,
            model=attempt.model,
            work_dir=work_dir,
            source_images=list(source_image_bytes_list),
            resume_thread_id=resume.thread_id if resume is not None else "",
        )
        outcome: dict[str, Any] = {}

        async def run() -> list[bytes]:
            result = await image_platform.run_agent(request, on_queue)
            outcome["result"] = result
            return result.images

        # 外层只兜底：排队与运行各自由适配器计时，这里留出两者之和与收尾余量。
        timeout_seconds = (
            self.router.resolve_task_timeout_seconds(attempt.model)
            + self.router.resolve_queue_timeout_seconds(attempt.model)
            + 60
        )
        images = await self.run_provider_call(run, timeout_seconds=timeout_seconds)
        result = outcome.get("result")
        if store is not None and result is not None and result.thread_id:
            try:
                await asyncio.to_thread(
                    store.record,
                    thread_id=result.thread_id,
                    instance=instance,
                    session_key=session_key,
                    work_dir=work_dir,
                    images=images,
                    retention_days=settings.thread_retention_days,
                )
            except Exception as exc:
                # 会话索引仅用于后续接续，写入失败不影响本次已生成结果。
                self.ctx.logger.warning(
                    "Codex 会话索引保存失败，后续调整将新建会话: task_id=%s thread_id=%s error=%s",
                    task_id,
                    result.thread_id,
                    type(exc).__name__,
                )
        if result is not None:
            self.ctx.logger.info(
                "Codex 智能体结果: task_id=%s thread_id=%s resumed=%s image_count=%s source_count=%s summary=%s",
                task_id,
                result.thread_id,
                resume is not None,
                len(images),
                len(result.sources),
                self.task_store.sanitize_message(sanitize_provider_text(result.summary, max_chars=300)),
            )
        return images

    @staticmethod
    def _format_attempt_error(attempt: ImageRequestAttempt, error_message: str) -> str:
        """格式化一次模型尝试失败信息。"""

        role_name = "备选模型" if attempt.is_fallback else "首选模型"
        return f"{role_name} {attempt.provider_name}:{attempt.model} 失败：{error_message}"
