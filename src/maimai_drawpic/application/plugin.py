"""插件生命周期、配置与运行服务的组合。"""

from collections.abc import Mapping
from maibot_sdk import CONFIG_RELOAD_SCOPE_SELF, MaiBotPlugin, ON_BOT_CONFIG_RELOAD, ON_MODEL_CONFIG_RELOAD
from pathlib import Path
from typing import Any, ClassVar, List
from threading import RLock
from weakref import WeakSet
import asyncio

from ..paths import PLUGIN_DIR
from ..domain.configuration.models import DrawpicConfig, migrate_legacy_review_config
from ..infrastructure.storage.migration import migrate_plugin_data
from .drawing import DrawService
from ..interfaces.chat.image_reply import PinkImageReplyRenderer
from .moderation import DrawpicModerationService
from .routing import ProviderRouter
from .routing.instances import InstanceProviderRouter
from ..infrastructure.storage.preferences import SessionPreferenceStore
from ..domain.styles import StylePromptResolver
from .chat import ChatStreamService
from ..infrastructure.storage.tasks import DrawTaskStore
from ..infrastructure.storage.agent_threads import CodexThreadStore
from ..infrastructure.storage.quotas import UserQuotaStore
from ..infrastructure.storage.platforms import PLATFORM_NAMES, WorkspaceConfigStore, host_config, host_default_config
from ..infrastructure.storage.results import ImageResultStore
from ..infrastructure.observability.redaction import SecretRedactor
from ..infrastructure.concurrency import run_owned_thread
from .workspace.lifecycle import attach_workspace, close_workspace, prepare_workspace, refresh_runtime
from .workspace.service import WorkspaceService


class DrawpicRuntime(MaiBotPlugin):
    """拥有服务实例及其启动、刷新和关闭过程。"""

    config_model = DrawpicConfig
    config_reload_subscriptions: ClassVar[tuple[str, ...]] = ("bot", "model")

    def __init__(self) -> None:
        super().__init__()
        self._redactor = SecretRedactor()
        # 数据路径和存储对象在 on_load 获得 Runner 上下文后初始化。
        self._data_dir: Path
        self._workflows_dir: Path
        self._workflows_readme_path: Path
        self._session_preferences_path: Path
        self._router: ProviderRouter | None = None
        self._session_store: SessionPreferenceStore | None = None
        self._style_prompt_resolver: StylePromptResolver | None = None
        self._stream_service: ChatStreamService | None = None
        self._moderation_service: DrawpicModerationService | None = None
        self._task_store: DrawTaskStore
        self._usage_store: UserQuotaStore
        self._agent_threads: CodexThreadStore | None = None
        self._image_reply_renderer = PinkImageReplyRenderer()
        self._draw_service: DrawService | None = None
        self._retired_draw_services: List[DrawService] = []
        self._draw_services: WeakSet[DrawService] = WeakSet()
        self._service_lifecycle_lock = RLock()
        self._closing = False
        self._platform_store: WorkspaceConfigStore | None = None
        self._effective_config: DrawpicConfig | None = None
        self._result_store: ImageResultStore | None = None
        self._workspace_service: WorkspaceService | None = None
        self._workspace_cleanup_task: asyncio.Task | None = None

    @property
    def config(self) -> DrawpicConfig:
        """使用宿主通用配置与已添加平台组成的运行时配置。"""
        if self._effective_config is not None:
            return self._effective_config
        return super().config

    def normalize_plugin_config(self, config_data: Mapping[str, Any] | None) -> tuple[dict[str, Any], bool]:
        """归一化配置，并把旧版独立审核节迁移到通用配置。"""

        migrated_config = migrate_legacy_review_config(config_data or {})
        general = migrated_config.get("general", {})
        if general.get("fallback_model") and not general.get("fallback_models"):
            general["fallback_models"] = [general["fallback_model"]]
            general["fallback_model"] = ""
        normalized_config, changed = super().normalize_plugin_config(migrated_config)
        normalized_config.pop("prompt_review", None)
        normalized_config.pop("image_review", None)
        # SDK 会补齐模型默认值；不可把已迁出的节在每次加载时重新写回 TOML。
        present = set(config_data or {})
        if present & {"prompt_review", "image_review"}:
            present.add("general")
        for section in (*PLATFORM_NAMES, "general", "style"):
            if section not in present:
                normalized_config.pop(section, None)
        if self._platform_store is not None:
            normalized_config = host_config(normalized_config)
        return normalized_config, changed or normalized_config != dict(config_data or {})

    def get_default_config(self) -> dict[str, Any]:
        """只生成宿主配置；完整模型默认值仅用于运行时和旧配置迁移。"""

        default_config = super().get_default_config()
        if self._platform_store is not None:
            return host_config(default_config)
        return host_default_config(default_config, PLUGIN_DIR / "config.toml")

    def get_webui_config_schema(
        self,
        *,
        plugin_id: str = "",
        plugin_name: str = "",
        plugin_version: str = "",
        plugin_description: str = "",
        plugin_author: str = "",
    ) -> dict[str, Any]:
        """返回不包含旧审核节的 WebUI 配置 Schema。"""

        schema = super().get_webui_config_schema(
            plugin_id=plugin_id,
            plugin_name=plugin_name,
            plugin_version=plugin_version,
            plugin_description=plugin_description,
            plugin_author=plugin_author,
        )
        sections = schema.get("sections")
        if isinstance(sections, dict):
            for kind in PLATFORM_NAMES:
                sections.pop(kind, None)
            sections.pop("prompt_review", None)
            sections.pop("image_review", None)
            sections.pop("general", None)
            sections.pop("style", None)
        return schema

    def _prepare_data_dir(self) -> None:
        """准备插件运行时数据目录，并迁移旧位置的数据文件。"""

        self._data_dir = self.ctx.paths.data_dir
        self._workflows_dir = self._data_dir / "workflows"
        self._workflows_readme_path = self._workflows_dir / "README.txt"
        self._session_preferences_path = self._data_dir / "session_preferences.json"
        backups = migrate_plugin_data(PLUGIN_DIR, self._data_dir)
        for backup in backups:
            self.ctx.logger.info("旧插件数据已迁移: data_dir=%s backup=%s", self._data_dir, backup)
        self._prepare_workflows_dir()
        self._task_store = DrawTaskStore(
            path=self._data_dir / "draw_tasks.json", logger=self.ctx.logger, sanitize=self._redactor.redact
        )
        self._usage_store = UserQuotaStore(path=self._data_dir / "user_quotas.json", logger=self.ctx.logger)
        self._agent_threads = CodexThreadStore(self._data_dir / "codex_agent", logger=self.ctx.logger)

    def _load_agent_threads(self) -> None:
        """读取 Codex 会话索引并清理过期会话目录；索引损坏只停用接续，不影响其他平台。"""

        self._agent_threads.load()
        records = self._platform_store.providers if self._platform_store is not None else []
        # 多个 Codex 实例共用会话目录，按最长保留期清理，避免误删其他实例仍可接续的会话。
        days = max(
            [int(item["config"].get("thread_retention_days", 7)) for item in records if item["kind"] == "codex"] or [7]
        )
        try:
            removed = self._agent_threads.prune(days)
        except OSError as exc:
            self.ctx.logger.warning("Codex 会话目录清理失败: error_type=%s", type(exc).__name__)
            return
        if removed:
            self.ctx.logger.info("已清理过期 Codex 会话目录: count=%s", removed)

    def _prepare_workflows_dir(self) -> None:
        """创建 ComfyUI 工作流目录及首次使用说明，不覆盖用户内容。"""

        self._workflows_dir.mkdir(parents=True, exist_ok=True)
        if self._workflows_readme_path.exists():
            return

        self._workflows_readme_path.write_text(
            """ComfyUI 工作流目录说明

请将从 ComfyUI 菜单“导出（API 格式）”得到的 JSON 工作流放入本目录。

默认文件名：
1. t2i.json：文生图工作流，对应 comfyui.t2i_workflow_path。
2. i2i.json：图生图工作流，对应 comfyui.i2i_workflow_path。

普通“保存”得到的画布 JSON 不能直接使用；它通常包含 nodes、links 等字段。
请在插件配置中填写提示词、种子和图生图源图片对应的 API 工作流节点 ID。
详细配置说明请查看插件 docs/platforms.md 的 ComfyUI 章节。
""",
            encoding="utf-8",
        )
        self.ctx.logger.info("已创建 ComfyUI 工作流目录说明: path=%s", self._workflows_readme_path)

    def _refresh_services(self) -> None:
        """刷新内部服务对象。"""

        self._task_store.bind_logger(self.ctx.logger)
        self._usage_store.bind_logger(self.ctx.logger)
        old_references = self._router.model_references() if isinstance(self._router, InstanceProviderRouter) else {}
        instance_configs = [
            (record, self._platform_store.effective_config(self.get_plugin_config_data(), [record]))
            for record in self._platform_store.providers
        ]
        self._router = InstanceProviderRouter(
            self.config, instance_configs, logger=self.ctx.logger, data_dir=self._data_dir
        )
        references = self._router.model_references()
        renamed = {selector: references[key] for key, selector in old_references.items() if key in references}
        # 禁用平台不在活动路由中，仍须同步重命名其已有会话引用，避免卸载时写回旧名。
        renamed.update(self._platform_store.pending_model_renames)
        if self._session_store is None:
            self._session_store = SessionPreferenceStore(
                path=self._session_preferences_path,
                router=self._router,
                logger=self.ctx.logger,
                persist=self._platform_store.save_preferences,
            )
        else:
            self._session_store.rebind_router(self._router, renamed, self._platform_store.save_preferences)
        self._style_prompt_resolver = StylePromptResolver(self.config.style)
        self._stream_service = ChatStreamService(self.ctx)
        self._moderation_service = DrawpicModerationService(self.config, self.ctx)
        self._image_reply_renderer = PinkImageReplyRenderer()
        # A submitting caller may still hold an otherwise idle service across an await.
        # Keep weak registration of every live service instead of using running tasks
        # as the only evidence that it must remain reachable by cancellation/unload.
        with self._service_lifecycle_lock:
            if self._closing:
                return
            self._retired_draw_services = [
                service for service in self._retired_draw_services if service.has_active_work
            ]
            if self._draw_service is not None and self._draw_service.has_active_work:
                self._retired_draw_services.append(self._draw_service)
            self._draw_service = DrawService(
                ctx=self.ctx,
                router=self._router,
                stream_service=self._stream_service,
                moderation_service=self._moderation_service,
                task_store=self._task_store,
                result_store=self._result_store,
                agent_threads=self._agent_threads,
            )
            self._draw_services.add(self._draw_service)
        self._platform_store.pending_model_renames.clear()

    def _require_router(self) -> ProviderRouter:
        """返回当前 Provider 路由器。"""

        if self._router is None:
            raise RuntimeError("插件服务尚未初始化，请等待插件完成加载")
        return self._router

    def _require_session_store(self) -> SessionPreferenceStore:
        """返回当前会话配置存储。"""

        if self._session_store is None:
            raise RuntimeError("插件服务尚未初始化，请等待插件完成加载")
        return self._session_store

    def _require_style_prompt_resolver(self) -> StylePromptResolver:
        """返回全平台风格提示词解析器。"""

        if self._style_prompt_resolver is None:
            raise RuntimeError("插件服务尚未初始化，请等待插件完成加载")
        return self._style_prompt_resolver

    def _require_stream_service(self) -> ChatStreamService:
        """返回聊天流服务。"""

        if self._stream_service is None:
            raise RuntimeError("插件服务尚未初始化，请等待插件完成加载")
        return self._stream_service

    def _require_moderation_service(self) -> DrawpicModerationService:
        """返回审核服务。"""

        if self._moderation_service is None:
            raise RuntimeError("插件服务尚未初始化，请等待插件完成加载")
        return self._moderation_service

    def _require_draw_service(self) -> DrawService:
        """返回绘图服务。"""

        if self._closing:
            raise RuntimeError("插件正在卸载，不能提交新的绘图任务")
        if self._draw_service is None:
            raise RuntimeError("插件服务尚未初始化，请等待插件完成加载")
        return self._draw_service

    async def on_load(self) -> None:
        """插件加载时初始化平台。"""

        self._closing = False
        self._redactor.add_config(self.get_plugin_config_data())
        self.ctx.logger.addFilter(self._redactor)
        try:
            await run_owned_thread(self._prepare_data_dir)
            await prepare_workspace(self, PLUGIN_DIR / "config.toml")
            await run_owned_thread(self._refresh_services)
            await run_owned_thread(self._require_session_store().load)
            await run_owned_thread(self._task_store.load)
            await run_owned_thread(self._usage_store.load)
            await run_owned_thread(self._load_agent_threads)
            await attach_workspace(self)
        except BaseException:
            # Runner 的 on_load 失败路径不会再调用 on_unload。只释放已创建
            # 的资源，不能保存尚未成功读取的偏好、任务或额度，覆盖旧数据。
            try:
                if self._draw_service is not None:
                    await close_workspace(self)
            except Exception:
                self.ctx.logger.exception("插件初始化失败后的资源清理失败")
            finally:
                self.ctx.logger.removeFilter(self._redactor)
            raise
        router = self._require_router()
        moderation_service = self._require_moderation_service()
        try:
            resolved_default_model = router.resolve_default_model() if router.get_all_models() else ""
        except ValueError as exc:
            resolved_default_model = ""
            self.ctx.logger.warning("默认模型配置无效，请在工作台选择完整实例模型名称: %s", exc)
        resolved_fallback_model = (
            router.resolve_fallback_model(resolved_default_model) if router.get_all_models() else ""
        )
        fallback_unavailable_reason = (
            router.get_fallback_model_unavailable_reason(resolved_default_model)
            if router.get_all_models()
            else "尚未添加绘图平台"
        )
        self.ctx.logger.info(
            "麦麦绘图插件已加载: default_model=%s fallback_model=%s configured_fallback_model=%s fallback_unavailable_reason=%s timeout=%ss aliyun_models=%s openai_models=%s google_models=%s zhipu_models=%s volcengine_models=%s siliconflow_models=%s novelai_models=%s prompt_review=%s image_review=%s session_pref_count=%s task_count=%s",
            resolved_default_model,
            resolved_fallback_model or "未启用",
            self.config.general.fallback_model.strip() or "未配置",
            fallback_unavailable_reason or "",
            router.resolve_request_timeout_seconds(),
            len(router.get_aliyun_models()),
            len(router.get_openai_models()),
            len(router.get_google_models()),
            len(router.get_zhipu_models()),
            len(router.get_volcengine_models()),
            len(router.get_siliconflow_models()),
            len(router.get_novelai_models()),
            moderation_service.is_prompt_review_enabled(),
            moderation_service.is_image_review_enabled(),
            len(self._require_session_store().preferences),
            self._task_store.get_task_count(),
        )

    async def on_unload(self) -> None:
        """插件卸载回调。"""

        if self._draw_service is None:
            return
        await close_workspace(self)
        await asyncio.to_thread(self._require_session_store().save)
        await asyncio.to_thread(self._task_store.save)
        await asyncio.to_thread(self._usage_store.save)
        self.ctx.logger.info("麦麦绘图插件已卸载")
        self.ctx.logger.removeFilter(self._redactor)

    async def on_config_update(self, scope: str, config_data: dict[str, Any], version: str) -> None:
        """配置变更时重新初始化平台。"""

        del config_data
        if scope in {CONFIG_RELOAD_SCOPE_SELF, ON_MODEL_CONFIG_RELOAD, ON_BOT_CONFIG_RELOAD}:
            await refresh_runtime(self)
            await asyncio.to_thread(self._require_session_store().save)
            router = self._require_router()
            moderation_service = self._require_moderation_service()
            try:
                resolved_default_model = router.resolve_default_model() if router.get_all_models() else ""
            except ValueError as exc:
                resolved_default_model = ""
                self.ctx.logger.warning("默认模型配置无效，请在工作台选择完整实例模型名称: %s", exc)
            resolved_fallback_model = (
                router.resolve_fallback_model(resolved_default_model) if router.get_all_models() else ""
            )
            fallback_unavailable_reason = (
                router.get_fallback_model_unavailable_reason(resolved_default_model)
                if router.get_all_models()
                else "尚未添加绘图平台"
            )
            self.ctx.logger.info(
                "麦麦绘图插件配置已更新: scope=%s version=%s default_model=%s fallback_model=%s configured_fallback_model=%s fallback_unavailable_reason=%s timeout=%ss aliyun_models=%s openai_models=%s google_models=%s zhipu_models=%s volcengine_models=%s siliconflow_models=%s novelai_models=%s prompt_review=%s image_review=%s task_count=%s",
                scope,
                version,
                resolved_default_model,
                resolved_fallback_model or "未启用",
                self.config.general.fallback_model.strip() or "未配置",
                fallback_unavailable_reason or "",
                router.resolve_request_timeout_seconds(),
                len(router.get_aliyun_models()),
                len(router.get_openai_models()),
                len(router.get_google_models()),
                len(router.get_zhipu_models()),
                len(router.get_volcengine_models()),
                len(router.get_siliconflow_models()),
                len(router.get_novelai_models()),
                moderation_service.is_prompt_review_enabled(),
                moderation_service.is_image_review_enabled(),
                self._task_store.get_task_count(),
            )
