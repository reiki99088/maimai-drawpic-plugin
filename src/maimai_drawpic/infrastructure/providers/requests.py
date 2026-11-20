"""区分生成提交与已受理任务查询，网络异常不能跨阶段推断可重绘。"""

from contextlib import asynccontextmanager
from functools import wraps
from typing import AsyncIterator, Awaitable, Callable, ParamSpec, TypeVar
import aiohttp
import asyncio

from ...domain.errors import (
    ProviderConnectionError,
    ProviderError,
    ProviderOutcomeUnknown,
    ProviderSubmittedError,
)
from ..http import sanitize_provider_text

_P = ParamSpec("_P")
_T = TypeVar("_T")


def generation_submission(operation: Callable[_P, Awaitable[_T]]) -> Callable[_P, Awaitable[_T]]:
    """只装饰实际提交 POST；禁用重定向时连接未建立才证明本次提交未发出。"""

    @wraps(operation)
    async def submit(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        try:
            return await operation(*args, **kwargs)
        except ProviderError:
            raise
        except aiohttp.ClientConnectorError:
            raise ProviderConnectionError("图片服务连接未建立，生成请求尚未发出") from None
        except (TimeoutError, aiohttp.ClientConnectionError):
            raise ProviderOutcomeUnknown("图片请求超时或中断，远端受理状态不确定，未自动重绘") from None

    return submit


@asynccontextmanager
async def submitted_task(provider: str, remote_task_id: str) -> AsyncIterator[None]:
    """取得 ID 后收紧整个结果阶段的错误语义，同时保留审核拒绝、明确未出图的终态失败和取消。"""

    try:
        yield
    except ProviderSubmittedError:
        raise
    except Exception as exc:
        if isinstance(exc, ProviderError) and (exc.rejected or exc.resubmit_safe):
            raise
        unknown = isinstance(exc, (TimeoutError, aiohttp.ClientError, ProviderOutcomeUnknown, ProviderConnectionError))
        reason = "查询连接失败或超时，结果未确认" if unknown else sanitize_provider_text(str(exc))
        raise ProviderSubmittedError(provider, remote_task_id, reason, outcome_unknown=unknown) from exc


async def query_submitted_task(query: Callable[[], Awaitable[_T]], *, poll_interval: float) -> _T:
    """短暂断线仅重试同一个只读查询，最多三次；不受生成重试/备选设置影响。"""

    for attempt in range(3):
        try:
            return await query()
        except (TimeoutError, aiohttp.ClientConnectionError):
            if attempt == 2:
                raise
            await asyncio.sleep(poll_interval)
    raise AssertionError("unreachable query retry state")
