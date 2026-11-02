"""对提供商返回的图片地址逐跳校验，并固定实际连接 IP。"""

from ipaddress import ip_address, ip_network
from aiohttp.helpers import get_env_proxy_for_url
from typing import Iterable, List
from yarl import URL
import aiohttp
import asyncio
import socket

from ...domain.errors import ProviderDownloadError, ProviderResultError
from ..http import HttpProxySettings, read_response_bytes, sanitize_provider_url
from .images import validate_image_bytes
from .collection import bounded_results, current_budget


def _public_address(value: str) -> bool:
    address = ip_address(value)
    mapped = address.ipv4_mapped if address.version == 6 else None
    if mapped is not None:
        return _public_address(str(mapped))
    return address.is_global and not any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )


# Clash / Mihomo / sing-box 等代理 TUN 的 fake-ip 地址段（RFC 2544 基准测试保留段）。
# 仅供调用方显式允许，提供商结果下载默认不放行。
FAKE_IP_NETWORK = ip_network("198.18.0.0/15")


def _allowed_address(value: str, extra_networks: Iterable) -> bool:
    if _public_address(value):
        return True
    address = ip_address(value)
    return any(address.version == network.version and address in network for network in extra_networks)


def _url(value: str) -> URL:
    try:
        url = URL(value)
        if url.scheme not in {"http", "https"} or not url.raw_host or url.user is not None or url.password is not None:
            raise ValueError
        if "%" in url.raw_host:
            raise ValueError
        _ = url.port  # 校验端口，拒绝非法 authority。
        return url.with_fragment(None)
    except (ValueError, TypeError):
        raise ProviderResultError("图片结果地址必须为不含凭据的 HTTP(S) URL") from None


async def _addresses(host: str, port: int) -> List[str]:
    try:
        return [str(ip_address(host))]
    except ValueError:
        records = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
        # 优先 IPv4；把已验证的 IP 直接交给连接器，不让代理或第二次 DNS 解析改变目标。
        records.sort(key=lambda record: record[0] != socket.AF_INET)
        return list(dict.fromkeys(record[4][0] for record in records))


@bounded_results
async def download_image(
    url: str,
    *,
    base_url: str,
    proxy_settings: HttpProxySettings,
    timeout_seconds: int,
    extra_allowed_networks: tuple = (),
) -> bytes:
    """在有限预算内只恢复同一结果地址；每次重新检查 DNS 与重定向。"""
    current_budget().available()
    try:
        async with asyncio.timeout(timeout_seconds):
            for attempt in range(3):
                try:
                    raw = await _download_image(
                        url,
                        base_url=base_url,
                        proxy_settings=proxy_settings,
                        timeout_seconds=timeout_seconds,
                        extra_allowed_networks=extra_allowed_networks,
                    )
                    return current_budget().accept(raw)
                except ProviderDownloadError:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(0.5 * (attempt + 1))
    except TimeoutError:
        raise ProviderDownloadError("图片已生成，结果下载等待超时，未重新提交生成请求") from None
    raise AssertionError("unreachable download retry state")


async def _download_image(
    url: str,
    *,
    base_url: str,
    proxy_settings: HttpProxySettings,
    timeout_seconds: int,
    extra_allowed_networks: tuple = (),
) -> bytes:
    """默认只访问公网；管理员配置的服务同源结果允许本地部署，无需额外开关。"""
    current, trusted = _url(url), _url(base_url)
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    try:
        async with asyncio.timeout(timeout_seconds):
            # 只读取代理环境，不启用 trust_env 的目标站点 .netrc 自动鉴权。
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for hop in range(6):
                    addresses = await _addresses(current.raw_host, current.port)
                    local_origin = current.origin() == trusted.origin()
                    if not addresses or (
                        not local_origin
                        and not all(_allowed_address(value, extra_allowed_networks) for value in addresses)
                    ):
                        raise ProviderResultError("图片结果地址指向非公网网络，且不属于已配置服务的同源地址")
                    target = current.with_host(addresses[0])
                    kwargs = proxy_settings.aiohttp_request_kwargs()
                    if proxy_settings.enabled and proxy_settings.use_system_proxy:
                        try:
                            proxy, proxy_auth = get_env_proxy_for_url(current)
                        except LookupError:
                            pass  # NO_PROXY 命中或未配置代理时直连。
                        else:
                            kwargs.update(proxy=proxy, proxy_auth=proxy_auth)
                    if current.scheme == "https":
                        kwargs["server_hostname"] = current.raw_host
                    # 无鉴权头，显式关闭自动跳转，每一跳重新验证地址和 DNS。
                    async with session.get(
                        target, headers={"Host": current.raw_authority}, allow_redirects=False, **kwargs
                    ) as response:
                        if response.status in {301, 302, 303, 307, 308}:
                            location = response.headers.get("Location")
                            if not location or hop == 5:
                                raise ProviderResultError("图片下载重定向无效或超过 5 次")
                            current = _url(str(current.join(URL(location))))
                            continue
                        if response.status != 200:
                            raise ProviderResultError(
                                f"图片结果下载失败: HTTP {response.status} url={sanitize_provider_url(str(current))}"
                            )
                        raw = await read_response_bytes(response, max_bytes=current_budget().available())
                        await asyncio.to_thread(validate_image_bytes, raw)
                        return raw
    except ProviderResultError:
        raise
    except (aiohttp.ClientConnectionError, aiohttp.ClientPayloadError, TimeoutError) as exc:
        raise ProviderDownloadError(f"图片结果传输中断（{type(exc).__name__}），未重新提交生成请求") from None
    except (aiohttp.ClientError, OSError, ValueError, RuntimeError) as exc:
        raise ProviderResultError(f"图片结果下载或校验失败（{type(exc).__name__}），未重新提交生成请求") from None
    raise ProviderResultError("图片结果下载未完成")
