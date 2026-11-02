"""Codex 智能体绘图的命令参数、任务提示与结构化回复定义（纯定义，不访问网络或进程）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence
import json

CODEX_PROVIDER = "codex"
REFERENCE_SERVER_NAME = "drawpic_refs"
MAX_CODEX_SOURCE_IMAGES = 4

# 插件强制关闭的 Codex 功能：命令行、浏览器/电脑操控、应用与插件、记忆和 hooks。
# 智能体只保留联网搜索、查看图片、内置生图和插件提供的参考图下载工具。
DISABLED_FEATURES = (
    "shell_tool",
    "unified_exec",
    "computer_use",
    "browser_use",
    "in_app_browser",
    "apps",
    "plugins",
    "multi_agent",
    "memories",
    "hooks",
)

REASONING_EFFORTS = ("low", "medium", "high", "xhigh", "ultra")

DEFAULT_AGENT_INSTRUCTIONS = (
    "你是一名图片创作助手，按用户需求完成一张高质量图片。\n"
    "1. 先判断需求是否涉及具体角色、作品、人物、地点、产品或特定风格；涉及时自主联网检索，"
    "优先官方页面与官方立绘，核实身份与外观。\n"
    "2. 需要参考外观时，下载可靠参考图，实际查看后再作为生图参考图输入，并在生图描述中说明每张参考图的用途。"
    "只找到链接或读到文字描述不算使用了参考图。下载失败时换其他来源；仍无法获取时如实说明。\n"
    "3. 生成后检查结果；明显偏离需求或角色特征时，可以针对性调整后再生成一次，避免无必要的多次重绘。\n"
    "4. 不得用插值放大冒充更高分辨率，不添加文字、水印或无关元素（除非用户要求）。"
)

OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status": {"type": "string", "enum": ["completed", "refused", "failed"]},
        "summary": {"type": "string"},
        "final_images": {"type": "array", "items": {"type": "string"}},
        "sources": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "summary", "final_images", "sources"],
}


@dataclass(frozen=True, slots=True)
class CodexReferenceServer:
    """插件参考图下载 MCP 服务的启动方式。"""

    python: str
    script: str
    config_path: str


def _toml(value: Any) -> str:
    # JSON 字符串与字符串数组同时是合法的 TOML 基本字符串/数组。
    return json.dumps(value, ensure_ascii=False)


def build_exec_args(
    executable: str,
    *,
    model: str,
    reasoning_effort: str,
    output_schema_path: str,
    last_message_path: str,
    image_paths: Sequence[str] = (),
    resume_thread_id: str = "",
    reference_server: CodexReferenceServer | None = None,
) -> List[str]:
    """构造 `codex exec`（或 `exec resume`）参数列表；提示词通过 stdin 传入。"""

    args = [executable, "exec"]
    if resume_thread_id:
        args += ["resume", resume_thread_id]
    args += [
        "--skip-git-repo-check",
        "--ignore-user-config",
        "-c",
        'sandbox_mode="read-only"',
        "-c",
        'approval_policy="never"',
        "-c",
        'web_search="live"',
    ]
    for feature in DISABLED_FEATURES:
        args += ["--disable", feature]
    if reference_server is not None:
        prefix = f"mcp_servers.{REFERENCE_SERVER_NAME}"
        args += [
            "-c",
            f"{prefix}.command={_toml(reference_server.python)}",
            "-c",
            f"{prefix}.args={_toml([reference_server.script, '--config', reference_server.config_path])}",
            "-c",
            f"{prefix}.startup_timeout_sec=30",
            "-c",
            f"{prefix}.tool_timeout_sec=150",
            "-c",
            f'{prefix}.default_tools_approval_mode="approve"',
        ]
    if model.strip():
        args += ["-m", model.strip()]
    if reasoning_effort in REASONING_EFFORTS:
        args += ["-c", f"model_reasoning_effort={_toml(reasoning_effort)}"]
    for path in image_paths:
        args.append(f"--image={path}")
    args += ["--json", "--output-schema", output_schema_path, "-o", last_message_path, "-"]
    return args


def build_agent_prompt(
    *,
    instructions: str,
    user_prompt: str,
    source_image_paths: Sequence[str] = (),
    references_dir: str = "",
    reference_downloads_enabled: bool = True,
    resume: bool = False,
) -> str:
    """组合固定任务说明、运行限制与用户需求。"""

    environment = [
        "你在绘图插件托管的非交互环境中运行，无法向用户提问；有歧义时按最合理的理解直接完成。",
        "本环境没有命令行工具，文件系统只读。",
    ]
    if reference_downloads_enabled:
        environment.append(
            "需要网络图片时，先联网搜索找到图片直链，再调用 MCP 工具 fetch_reference_image 下载（每次任务有数量上限），"
            f"文件保存在 {references_dir or '任务参考图目录'}；然后用 view_image 查看。"
        )
    else:
        environment.append("本次未提供图片下载工具，只能依靠联网搜索结果和已附带的图片。")
    environment.append(
        "生成或修改图片必须调用内置生图工具；把已查看的参考图作为参考图片输入（如 referenced_image_paths），"
        "并在描述中说明每张图的用途。"
    )
    if source_image_paths:
        environment.append(
            "用户附带的图片已作为附件提供，本地路径：" + "；".join(source_image_paths) + "。图生图时以它们为编辑对象或参考。"
        )
    environment.append(
        "完成后按要求的 JSON 结构回复：status 为 completed / refused / failed；final_images 列出要交付给用户的生成图片"
        "绝对路径（使用生图工具返回的保存路径，通常只填最终一张）；summary 用中文简述做了什么；sources 列出实际使用的参考来源 URL。"
    )
    sections = [
        "【任务说明】\n" + (instructions.strip() or DEFAULT_AGENT_INSTRUCTIONS),
        "【运行环境】\n" + "\n".join(f"- {line}" for line in environment),
    ]
    if resume:
        sections.append(
            "【本轮为二次调整】\n用户希望修改之前的作品。附件通常是你上一轮生成并被用户引用的图片。"
            "沿用之前已核实的资料和参考图，按下面的要求修改后重新生成；未提到的部分尽量保持不变。"
        )
    sections.append("【用户需求】\n" + user_prompt.strip())
    return "\n\n".join(sections)


def parse_final_message(text: str) -> Dict[str, Any]:
    """解析结构化最终回复；不符合结构时返回空结果，由调用方按生成文件兜底。"""

    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        return {"status": "", "summary": str(text or "")[:500], "final_images": [], "sources": []}
    if not isinstance(value, dict):
        return {"status": "", "summary": "", "final_images": [], "sources": []}
    status = value.get("status") if value.get("status") in {"completed", "refused", "failed"} else ""
    images = value.get("final_images") if isinstance(value.get("final_images"), list) else []
    sources = value.get("sources") if isinstance(value.get("sources"), list) else []
    return {
        "status": status,
        "summary": str(value.get("summary") or "")[:2000],
        "final_images": [item for item in images if isinstance(item, str)][:16],
        "sources": [item for item in sources if isinstance(item, str)][:32],
    }
