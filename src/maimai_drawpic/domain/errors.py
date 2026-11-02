"""提供商失败的执行语义，避免把未知结果当作可重复提交的请求。"""


class ProviderError(RuntimeError):
    """默认不重新生成；只有明确未受理的临时错误才允许重试。"""

    retryable = False
    allow_fallback = False
    rejected = False
    outcome_unknown = False


class ProviderRequestError(ProviderError):
    """收到明确拒绝响应，保留协议状态与审核分类。"""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code = status, code
        normalized = code.casefold().replace("-", "_")
        self.rejected = any(
            marker in normalized
            for marker in (
                "content_policy",
                "content_filter",
                "safety",
                "moderation",
                "sensitive",
                "inappropriate",
                "responsibleai",
                "datainspection",
                "riskcontrol",
                "prohibited",
            )
        )
        quota = any(marker in normalized for marker in ("quota", "balance", "billing", "credit"))
        self.retryable = (
            not self.rejected
            and not quota
            and (
                status == 429
                or normalized in {"server_busy", "service_unavailable", "model_overloaded", "rate_limit_exceeded"}
            )
        )
        self.allow_fallback = not self.rejected and (400 <= status < 500 or self.retryable)
        self.outcome_unknown = not self.rejected and status >= 500 and not self.retryable


class ProviderResultError(ProviderError):
    """已收到生成响应，解析或结果下载失败只能恢复结果，不能重新生图。"""


class ProviderDownloadError(ProviderResultError):
    """只允许下载器恢复同一结果 URL 的临时传输错误，不能重新生成。"""


class ProviderOutcomeUnknown(ProviderError):
    """连接中断或超时，无法确认上游是否已经受理、生成或计费。"""

    outcome_unknown = True


class ProviderConnectionError(ProviderError):
    """连接尚未建立，生成请求没有发出，可按配置重试或切换。"""

    retryable = True
    allow_fallback = True


class ProviderBusyError(ProviderConnectionError):
    """本地排队已满或排队超时，请求尚未发出；不在同一模型重试，可切换备选模型。"""

    retryable = False
    allow_fallback = True


class ProviderSubmittedError(ProviderResultError):
    """保留已受理的远端 ID；后续失败绝不能重新提交生成。"""

    def __init__(self, provider: str, remote_task_id: str, reason: str, *, outcome_unknown: bool = False) -> None:
        super().__init__(f"{provider} 任务 {remote_task_id} 已提交；{reason}；未重新提交生成，请检查该任务的远端记录")
        self.provider = provider
        self.remote_task_id = remote_task_id
        self.outcome_unknown = outcome_unknown
