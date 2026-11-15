"""逐跳检查结果地址；直连固定 IP，代理保留域名并交由代理解析。"""

from ipaddress import ip_address, ip_network
from aiohttp.helpers import get_env_proxy_for_url
from typing import Callable, Iterable, List, Mapping, Optional, Tuple
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

# 公开资料抓取的默认上限与"不可信来源"基准：基准地址不可能同源，因此不放行任何内网。
MAX_PUBLIC_TEXT_BYTES = 1_500_000
_UNTRUSTED_BASE = "https://reference.invalid"


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
        # 优先 IPv4；直连把已验证的 IP 交给连接器，避免第二次 DNS 解析改变目标。
        records.sort(key=lambda record: record[0] != socket.AF_INET)
        return list(dict.fromkeys(record[4][0] for record in records))


async def _download_target(
    current: URL, trusted: URL, *, via_proxy: bool, skip_ip_check: bool, extra_allowed_networks: tuple = ()
) -> URL:
    """按实际出站方式检查地址，避免把本地 Fake-IP 当作代理的目标 IP。"""
    if skip_ip_check:
        return current

    local_origin = current.origin() == trusted.origin()
    if via_proxy:
        # 代理在远端解析域名；本地 DNS 可能返回 Fake-IP，甚至无法解析。
        # 不把域名替换成 IP，否则代理的 DNS、分流和 HTTPS CONNECT 都会失去原始目标。
        host = current.raw_host.rstrip(".").casefold()
        try:
            address = ip_address(host)
        except ValueError:
            try:
                # inet_aton 只解析字面量，不查询 DNS；同时识别十六进制、整数等旧式 IPv4 写法。
                address = ip_address(socket.inet_aton(host))
            except OSError:
                if not local_origin and (host == "localhost" or host.endswith(".localhost")):
                    raise ProviderResultError("图片结果地址指向非公网网络，且不属于已配置服务的同源地址")
                return current
        if not local_origin and not _allowed_address(str(address), extra_allowed_networks):
            raise ProviderResultError("图片结果地址指向非公网网络，且不属于已配置服务的同源地址")
        return current

    addresses = await _addresses(current.raw_host, current.port)
    if not addresses or (
        not local_origin and not all(_allowed_address(value, extra_allowed_networks) for value in addresses)
    ):
        raise ProviderResultError("图片结果地址指向非公网网络，且不属于已配置服务的同源地址")
    return current.with_host(addresses[0])


@bounded_results
async def download_image(
    url: str,
    *,
    base_url: str,
    proxy_settings: HttpProxySettings,
    timeout_seconds: int,
    skip_ip_check: bool = False,
    extra_allowed_networks: tuple = (),
    headers: Optional[Mapping[str, str]] = None,
) -> bytes:
    """在有限预算内只恢复同一结果地址；每次重新选择代理并校验地址与跳转。"""
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
                        skip_ip_check=skip_ip_check,
                        extra_allowed_networks=extra_allowed_networks,
                        headers=headers,
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
    skip_ip_check: bool,
    extra_allowed_networks: tuple = (),
    headers: Optional[Mapping[str, str]] = None,
    image_content: bool = True,
) -> bytes:
    """逐跳选择实际代理；直连默认只访问公网或管理员配置的同源服务。"""
    try:
        async with asyncio.timeout(timeout_seconds):
            raw, _final, _content_type = await _get_public(
                url,
                base_url=base_url,
                proxy_settings=proxy_settings,
                timeout_seconds=timeout_seconds,
                skip_ip_check=skip_ip_check,
                extra_allowed_networks=extra_allowed_networks,
                # 素材网页只读有限正文，不计入图片配额、不按图片校验。
                max_bytes=current_budget().available if image_content else (lambda: 512 * 1024),
                headers=headers,
            )
            if image_content:
                await asyncio.to_thread(validate_image_bytes, raw)
            return raw
    except ProviderResultError:
        raise
    except (aiohttp.ClientConnectionError, aiohttp.ClientPayloadError, TimeoutError) as exc:
        raise ProviderDownloadError(f"图片结果传输中断（{type(exc).__name__}），未重新提交生成请求") from None
    except (aiohttp.ClientError, OSError, ValueError, RuntimeError) as exc:
        raise ProviderResultError(f"图片结果下载或校验失败（{type(exc).__name__}），未重新提交生成请求") from None


async def _get_public(
    url: str,
    *,
    base_url: str,
    proxy_settings: HttpProxySettings,
    timeout_seconds: int,
    skip_ip_check: bool,
    extra_allowed_networks: tuple,
    max_bytes: Callable[[], int],
    headers: Optional[Mapping[str, str]],
) -> Tuple[bytes, URL, str]:
    """逐跳 GET：每一跳重新选择出站并校验地址，返回正文、最终地址与 Content-Type。"""
    current, trusted = _url(url), _url(base_url)
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    # 只读取代理环境，不启用 trust_env 的目标站点 .netrc 自动鉴权。
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for hop in range(6):
            kwargs = proxy_settings.aiohttp_request_kwargs()
            if proxy_settings.enabled and proxy_settings.use_system_proxy:
                try:
                    proxy, proxy_auth = get_env_proxy_for_url(current)
                except LookupError:
                    pass  # NO_PROXY 命中或未配置代理时直连。
                else:
                    kwargs.update(proxy=proxy, proxy_auth=proxy_auth)
            # NO_PROXY 或平台绕过代理时仍走直连校验，不能仅按 enabled 跳过 DNS。
            target = await _download_target(
                current,
                trusted,
                via_proxy=bool(kwargs.get("proxy")),
                skip_ip_check=skip_ip_check,
                extra_allowed_networks=extra_allowed_networks,
            )
            if current.scheme == "https":
                kwargs["server_hostname"] = current.raw_host
            request_headers = dict(headers or {})
            request_headers["Host"] = current.raw_authority
            # 不附加生成服务的鉴权头，关闭自动跳转，每一跳重新选择出站并校验地址。
            async with session.get(target, headers=request_headers, allow_redirects=False, **kwargs) as response:
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
                raw = await read_response_bytes(response, max_bytes=max_bytes())
                return raw, current, response.headers.get("Content-Type", "")
    raise ProviderResultError("图片结果下载未完成")


class PublicFetchError(RuntimeError):
    """公开资料抓取失败；与生成结果无关，调用方只应降级，不得据此重绘。"""


def _fetch_reason(exc: BaseException) -> str:
    message = str(exc)
    if "非公网" in message:
        return "地址指向非公网网络"
    if "HTTP " in message:
        return "HTTP " + message.split("HTTP ", 1)[1].split(" ", 1)[0]
    if "重定向" in message:
        return "重定向无效或超过 5 次"
    if "URL" in message:
        return "地址必须为不含凭据的 HTTP(S) URL"
    if "大小限制" in message:
        return "响应超过大小限制"
    return type(exc).__name__


async def fetch_public_bytes(
    url: str,
    *,
    proxy_settings: HttpProxySettings,
    timeout_seconds: float,
    max_bytes: int = MAX_PUBLIC_TEXT_BYTES,
    headers: Optional[Mapping[str, str]] = None,
    extra_allowed_networks: tuple = (),
) -> Tuple[bytes, str, str]:
    """只读抓取公网资源（网页、JSON），不放行任何同源内网；失败统一抛 PublicFetchError。

    返回正文、脱敏后的最终地址与 Content-Type。不做重试：资料抓取失败只降级。
    """
    try:
        async with asyncio.timeout(timeout_seconds):
            raw, final, content_type = await _get_public(
                url,
                base_url=_UNTRUSTED_BASE,
                proxy_settings=proxy_settings,
                timeout_seconds=max(1, int(timeout_seconds)),
                skip_ip_check=False,
                extra_allowed_networks=extra_allowed_networks,
                max_bytes=lambda: max_bytes,
                headers=headers,
            )
            return raw, sanitize_provider_url(str(final)), content_type
    except TimeoutError:
        raise PublicFetchError("资料抓取超时") from None
    except (ProviderResultError, aiohttp.ClientError, OSError, ValueError, RuntimeError) as exc:
        raise PublicFetchError(f"资料抓取失败：{_fetch_reason(exc)}") from None


async def fetch_public_text(
    url: str,
    *,
    proxy_settings: HttpProxySettings,
    timeout_seconds: float,
    max_bytes: int = MAX_PUBLIC_TEXT_BYTES,
    headers: Optional[Mapping[str, str]] = None,
    extra_allowed_networks: tuple = (),
) -> Tuple[str, str]:
    """按响应声明的字符集解码公网文本；未声明时按 UTF-8 宽松解码。"""
    raw, final, content_type = await fetch_public_bytes(
        url,
        proxy_settings=proxy_settings,
        timeout_seconds=timeout_seconds,
        max_bytes=max_bytes,
        headers=headers,
        extra_allowed_networks=extra_allowed_networks,
    )
    charset = "utf-8"
    for part in content_type.split(";")[1:]:
        key, _, value = part.strip().partition("=")
        if key.strip().lower() == "charset" and value.strip():
            charset = value.strip().strip('"')
    try:
        return raw.decode(charset, errors="replace"), final
    except LookupError:
        return raw.decode("utf-8", errors="replace"), final
