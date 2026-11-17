"""绘图配置共享的枚举类型。"""

from typing import Literal

NovelAIModelId = Literal[
    "nai-diffusion-5-full",
    "nai-diffusion-5-curated",
    "nai-diffusion-4-5-full",
    "nai-diffusion-4-5-curated",
    "nai-diffusion-4-full",
    "nai-diffusion-4-curated-preview",
    "nai-diffusion-3",
    "nai-diffusion-furry-3",
]

QuotaPeriodMode = Literal["daily", "weekly", "monthly", "once"]

AccessListMode = Literal["blacklist", "whitelist"]

ReviewModelTask = Literal["replyer", "planner", "vlm"]

# 世界知识识别与整理词条只处理文字；思考模型会把输出预算花在思考上，所以多给两个常配非思考模型的任务组
WorldModelTask = Literal["replyer", "planner", "vlm", "utils", "fast_model"]

ProxyScheme = Literal["http", "https"]

CommandReplyMode = Literal["图片", "文本"]

ComfyUIPromptMode = Literal["single_prompt", "positive_negative"]

NovelAIMode = Literal["anime", "furry", "background"]

AliyunImageInputMode = Literal["auto", "base64", "url"]

AliyunPromptExtendMode = Literal["direct", "agent"]

AliyunKlingResultType = Literal["single", "series"]

VolcengineResponseFormat = Literal["url", "b64_json"]

VolcengineSequentialMode = Literal["disabled", "auto"]
