"""Codex 智能体绘图平台配置：由本机 Codex CLI 自主检索、参考并生成图片。"""

from maibot_sdk import Field, PluginConfigBase
from typing import List, Literal

from ...models.codex_profiles import DEFAULT_AGENT_INSTRUCTIONS

CodexReasoningEffort = Literal["default", "low", "medium", "high", "xhigh", "ultra"]
CodexAccessScope = Literal["admin", "all"]


class CodexAgentConfig(PluginConfigBase):
    """调用本机已登录的 Codex CLI，以对话智能体方式完成绘图任务。"""

    __ui_label__ = "Codex 智能体配置"
    __ui_order__ = 13

    enabled: bool = Field(default=True, json_schema_extra={"label": "启用 Codex 智能体平台", "order": -1})
    access_scope: CodexAccessScope = Field(
        default="admin",
        description="使用范围：admin=仅插件管理员；all=所有用户",
        json_schema_extra={
            "label": "使用范围",
            "hint": "admin=沿用通用设置的权限管理，仅插件管理员可使用（关闭“启用权限管理”时所有人可用）；all=所有用户可用。"
            "智能体会联网检索并消耗 Codex 账号额度，建议保持仅管理员。",
            "options": ["admin", "all"],
            "order": 0,
        },
    )
    models: List[str] = Field(
        default=["gpt-6.1-sol"],
        json_schema_extra={
            "label": "Codex 对话模型",
            "hint": "填写 Codex 可用的对话模型；图片由 Codex 内置生图工具生成，具体生图模型由 Codex 决定。",
            "order": 1,
        },
    )
    reasoning_effort: CodexReasoningEffort = Field(
        default="medium",
        json_schema_extra={
            "label": "推理强度",
            "hint": "default=使用 Codex 默认值。强度越高，检索与核对越充分，但耗时和额度消耗明显增加。",
            "options": ["default", "low", "medium", "high", "xhigh", "ultra"],
            "order": 2,
        },
    )
    codex_path: str = Field(
        default="",
        json_schema_extra={
            "label": "Codex 可执行文件",
            "hint": "留空自动查找：PATH 中的 codex，以及 Codex 桌面版 %LOCALAPPDATA%\\OpenAI\\Codex\\bin 下最新的 codex.exe。"
            "桌面版更新后目录会变化，建议留空。",
            "order": 3,
        },
    )
    codex_home: str = Field(
        default="",
        json_schema_extra={
            "label": "CODEX_HOME 目录",
            "hint": "留空使用环境变量 CODEX_HOME 或用户目录下的 .codex。必须是已登录 Codex 的目录，MaiBot 需以同一系统用户运行。",
            "order": 4,
        },
    )
    task_timeout_seconds: int = Field(
        default=900,
        ge=120,
        le=3600,
        json_schema_extra={
            "label": "任务超时（秒）",
            "hint": "轮到任务、Codex 开始运行后的最长时间，不含排队，也不受通用“图片请求超时”限制。检索和多轮调整通常需要数分钟。",
            "order": 5,
        },
    )
    max_concurrent_tasks: int = Field(
        default=1,
        ge=1,
        le=4,
        json_schema_extra={
            "label": "同时运行任务数",
            "hint": "同一 CODEX_HOME 同时运行的 Codex 任务上限，超出的任务按提交顺序排队。",
            "order": 6,
        },
    )
    max_queued_tasks: int = Field(
        default=3,
        ge=0,
        le=20,
        json_schema_extra={
            "label": "最多排队任务数",
            "hint": "运行名额已满时最多排队的任务数。队列已满时在扣次数前直接拒绝，提示稍后再试；0 表示不排队。",
            "order": 6.1,
        },
    )
    queue_timeout_seconds: int = Field(
        default=1200,
        ge=60,
        le=7200,
        json_schema_extra={
            "label": "排队等待上限（秒）",
            "hint": "排队超过该时间仍未轮到时放弃，请求尚未发出：有备选模型则改用备选，否则失败并退回次数，不会重新排队。",
            "order": 6.2,
        },
    )
    max_reference_downloads: int = Field(
        default=8,
        ge=0,
        le=20,
        json_schema_extra={
            "label": "每次最多下载参考图",
            "hint": "智能体通过插件的受控下载工具获取参考图（仅公网 HTTP(S)、校验真实图片）。0 表示不提供下载工具，只使用联网搜索。",
            "order": 7,
        },
    )
    allow_proxy_fake_ip: bool = Field(
        default=True,
        json_schema_extra={
            "label": "允许代理 fake-ip 地址",
            "hint": "Clash / Mihomo / sing-box 的 TUN fake-ip 模式会把域名解析到 198.18.0.0/15。开启后参考图下载放行该地址段，其他内网地址仍会拒绝。",
            "order": 8,
        },
    )
    resume_enabled: bool = Field(
        default=True,
        json_schema_extra={
            "label": "二次调整接续原会话",
            "hint": "图生图的源图是本平台近期生成的图片时，接续生成它的 Codex 会话，保留已查到的资料与参考图。",
            "order": 9,
        },
    )
    thread_retention_days: int = Field(
        default=7,
        ge=1,
        le=30,
        json_schema_extra={
            "label": "会话保留天数",
            "hint": "超过天数的会话不再接续，并清理插件为其保存的参考图和源图。",
            "order": 10,
        },
    )
    deliver_all_images: bool = Field(
        default=False,
        json_schema_extra={
            "label": "发送本轮全部图片",
            "hint": "关闭时只发送智能体选定的最终图片；开启后发送本轮生成的全部图片（包括中间稿）。",
            "order": 11,
        },
    )
    agent_instructions: str = Field(
        default=DEFAULT_AGENT_INSTRUCTIONS,
        json_schema_extra={
            "label": "智能体任务说明",
            "hint": "附加在每次请求前的固定说明，用于约束检索、参考图使用和交付方式。工具与安全限制由插件强制，不受此处影响。",
            "x-widget": "textarea",
            "rows": 10,
            "order": 12,
        },
    )
