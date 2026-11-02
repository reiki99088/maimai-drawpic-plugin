"""Codex 智能体专用的参考图下载 MCP 服务（stdio）。

Codex 的命令行工具在插件中被禁用，智能体只能通过本服务获取网络图片：
仅访问公网 HTTP(S)、逐跳校验重定向和 DNS、校验真实图片，并只写入当前
任务的参考图目录。服务由 Codex 以独立进程启动，配置文件由插件写在任务
私有目录中，不经命令行传递代理密码。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional
import asyncio
import json
import sys

SERVER_NAME = "drawpic_refs"
TOOL_NAME = "fetch_reference_image"
_UNTRUSTED_BASE = "https://reference.invalid"
_FORMAT_SUFFIX = {"jpeg": "jpg", "jpg": "jpg", "png": "png", "webp": "webp", "gif": "gif"}

TOOL_DEFINITION: Dict[str, Any] = {
    "name": TOOL_NAME,
    "description": (
        "Download one reference image from a public http(s) URL into this task's reference folder. "
        "Only real images are accepted (redirects and DNS are validated, private networks are refused). "
        "Returns the saved absolute path; call view_image on it before using it as an image_gen reference."
    ),
    "inputSchema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "url": {"type": "string", "description": "Direct http(s) URL of the image file."},
            "purpose": {
                "type": "string",
                "description": "Short note on what this reference is for, e.g. 'official character art'.",
            },
        },
        "required": ["url"],
    },
}


class ReferenceDownloader:
    """有数量上限的参考图下载器；只写入配置的目录。"""

    def __init__(self, config: Dict[str, Any]) -> None:
        from ..http import HttpProxySettings

        self.output_dir = Path(str(config["output_dir"])).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_downloads = int(config.get("max_downloads", 8))
        self.timeout_seconds = max(5, min(int(config.get("timeout_seconds", 45)), 120))
        proxy = config.get("proxy") or {}
        self.proxy = HttpProxySettings(
            enabled=bool(proxy.get("enabled", False)),
            use_system_proxy=bool(proxy.get("use_system_proxy", True)),
            scheme=str(proxy.get("scheme", "http")),
            host=str(proxy.get("host", "")),
            port=int(proxy.get("port", 0) or 0),
            username=str(proxy.get("username", "")),
            password=str(proxy.get("password", "")),
        )
        self.allow_fake_ip = bool(config.get("allow_fake_ip", False))
        self.ledger = self.output_dir / "references.jsonl"
        self.count = sum(1 for path in self.output_dir.glob("ref-*") if path.is_file())

    async def fetch(self, url: str, purpose: str = "") -> Dict[str, Any]:
        from ..http import sanitize_provider_url
        from ..media.downloads import FAKE_IP_NETWORK, download_image
        from ..media.images import detect_image_dimensions, detect_image_format

        if not isinstance(url, str) or not url.strip() or len(url) > 4096:
            raise ValueError("url 必须是 1～4096 个字符的 http(s) 地址")
        if self.count >= self.max_downloads:
            raise ValueError(f"本任务最多下载 {self.max_downloads} 张参考图，已达到上限")
        raw = await download_image(
            url.strip(),
            base_url=_UNTRUSTED_BASE,
            proxy_settings=self.proxy,
            timeout_seconds=self.timeout_seconds,
            extra_allowed_networks=(FAKE_IP_NETWORK,) if self.allow_fake_ip else (),
        )
        image_format = await asyncio.to_thread(detect_image_format, raw)
        dimensions = await asyncio.to_thread(detect_image_dimensions, raw) or (0, 0)
        self.count += 1
        path = self.output_dir / f"ref-{self.count:02d}.{_FORMAT_SUFFIX.get(image_format, 'png')}"
        await asyncio.to_thread(path.write_bytes, raw)
        record = {
            "path": str(path),
            "source": sanitize_provider_url(url.strip()),
            "purpose": str(purpose or "")[:200],
            "width": dimensions[0],
            "height": dimensions[1],
            "bytes": len(raw),
            "format": image_format,
        }
        line = json.dumps(record, ensure_ascii=False) + "\n"
        await asyncio.to_thread(_append_text, self.ledger, line)
        return record


def _append_text(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)


def _response(request_id: Any, result: Optional[Dict[str, Any]] = None, error: Optional[Dict[str, Any]] = None):
    payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result if result is not None else {}
    return payload


async def handle_message(message: Any, downloader: ReferenceDownloader) -> Optional[Dict[str, Any]]:
    """处理一条 JSON-RPC 消息；通知返回 None。"""

    if not isinstance(message, dict):
        return _response(None, error={"code": -32600, "message": "Invalid Request"})
    method = message.get("method")
    request_id = message.get("id")
    is_notification = "id" not in message
    params = message.get("params") if isinstance(message.get("params"), dict) else {}
    if method == "initialize":
        version = params.get("protocolVersion") if isinstance(params.get("protocolVersion"), str) else "2025-06-18"
        return _response(
            request_id,
            {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": "1.0.0"},
            },
        )
    if is_notification:
        return None
    if method == "ping":
        return _response(request_id, {})
    if method == "tools/list":
        return _response(request_id, {"tools": [TOOL_DEFINITION]})
    if method == "tools/call":
        if params.get("name") != TOOL_NAME:
            return _response(request_id, error={"code": -32602, "message": "Unknown tool"})
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        try:
            record = await downloader.fetch(arguments.get("url", ""), str(arguments.get("purpose", "") or ""))
        except Exception as exc:  # 工具失败返回给模型，不终止服务。
            from ..http import sanitize_provider_text

            text = sanitize_provider_text(str(exc) or type(exc).__name__, max_chars=300)
            return _response(request_id, {"content": [{"type": "text", "text": f"下载失败：{text}"}], "isError": True})
        return _response(
            request_id,
            {"content": [{"type": "text", "text": json.dumps(record, ensure_ascii=False)}], "isError": False},
        )
    return _response(request_id, error={"code": -32601, "message": "Method not found"})


def serve(config_path: Path) -> int:
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    downloader = ReferenceDownloader(config)
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    loop = asyncio.new_event_loop()
    try:
        while True:
            line = stdin.readline()
            if not line:
                return 0
            if not line.strip():
                continue
            try:
                message = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                reply: Optional[Dict[str, Any]] = _response(None, error={"code": -32700, "message": "Parse error"})
            else:
                reply = loop.run_until_complete(handle_message(message, downloader))
            if reply is not None:
                stdout.write((json.dumps(reply, ensure_ascii=False) + "\n").encode("utf-8"))
                stdout.flush()
    finally:
        loop.close()


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] != "--config":
        print("usage: codex_references.py --config <file>", file=sys.stderr)
        return 2
    return serve(Path(argv[1]))


if __name__ == "__main__":
    # 以脚本运行时插件目录名可能不是合法包名；构造私有包后按包导入，
    # 使相对导入复用插件的安全下载器与图片校验。
    import importlib
    import types

    _root = Path(__file__).resolve().parents[4]
    _package = "_maimai_drawpic_codex_refs"
    _module = types.ModuleType(_package)
    _module.__path__ = [str(_root)]  # type: ignore[attr-defined]
    sys.modules[_package] = _module
    _server = importlib.import_module(f"{_package}.src.maimai_drawpic.infrastructure.providers.codex_references")
    raise SystemExit(_server.main(sys.argv[1:]))
