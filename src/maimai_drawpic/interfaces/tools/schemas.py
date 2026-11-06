"""绘图工具的参数声明。"""

from typing import Any

ANIMATION_TOOL_PROPERTIES: dict[str, Any] = {
    "animated": {
        "type": "boolean",
        "description": "可选，仅当用户明确要求动图/GIF/会动的图时传 true；只有 gpt-image-2.6 系列模型支持，其余模型会返回原因",
    },
    "frame_count": {
        "type": "integer",
        "minimum": 2,
        "maximum": 16,
        "description": "可选，动图帧数 2～16，仅 animated=true 时有效；不填使用上游默认 9 帧",
    },
    "frame_duration_ms": {
        "type": "integer",
        "minimum": 20,
        "maximum": 2000,
        "description": "可选，动图每帧毫秒 20～2000，仅 animated=true 时有效；不填使用上游默认 200",
    },
}

DRAW_TOOL_PARAMETERS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "prompt": {
            "type": "string",
            "description": "图片提示词，尽量描述清楚主体、风格和画面内容",
        },
        "model": {
            "type": "string",
            "description": "可选，指定要优先使用的图片模型；未传时使用当前会话首选模型",
        },
        "negative_prompt": {
            "type": "string",
            "description": "可选，本次绘图的反向提示词；支持独立反向字段的平台会单独传递，否则合并到正向提示词",
        },
        **ANIMATION_TOOL_PROPERTIES,
    },
    "required": ["prompt"],
}


EDIT_IMAGE_TOOL_PARAMETERS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "prompt": {
            "type": "string",
            "description": "图片编辑提示词，描述希望基于源图修改成什么样；不要把源图片描述写在这里替代真实图片",
        },
        "source_message_id": {
            "type": "string",
            "description": "可选，指定要编辑的源图片消息 ID；不填时自动优先取当前/最近引用消息中的图片，再取最近一张图片",
        },
        "source_image_base64": {
            "type": "string",
            "description": "可选，直接传入真实源图片 Base64 或 data:image/...;base64；不要传图片描述文本",
        },
        "model": {
            "type": "string",
            "description": "可选，指定要优先使用的图片模型；未传时使用当前会话首选模型",
        },
        "negative_prompt": {
            "type": "string",
            "description": "可选，本次图生图的反向提示词；会与平台默认反向词合并",
        },
        **ANIMATION_TOOL_PROPERTIES,
    },
    "required": ["prompt"],
}


DRAW_STATUS_TOOL_PARAMETERS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "task_id": {
            "type": "string",
            "description": "可选，指定要查询的后台绘图任务 ID；不填时默认查询当前会话最近一个任务",
        },
    },
    "required": [],
}


STYLED_DRAW_TOOL_PARAMETERS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "prompt": {
            "type": "string",
            "description": "用户正向提示词；图生图时可以留空，由风格模板和源图片共同决定画面",
        },
        "style": {
            "type": "string",
            "description": "可选的插件全平台风格模板名称；不填时按普通 draw/edit_image 行为执行",
        },
        "negative_prompt": {
            "type": "string",
            "description": "可选的用户反向提示词，会与风格反向模板及平台默认反向词合并",
        },
        "source_message_id": {
            "type": "string",
            "description": "可选，指定图生图源图片消息 ID",
        },
        "source_image_base64": {
            "type": "string",
            "description": "可选，直接提供真实源图片 Base64 或 data URL",
        },
        **ANIMATION_TOOL_PROPERTIES,
    },
    "required": [],
}


DRAW_STYLES_TOOL_PARAMETERS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {},
    "required": [],
}
