"""configuration/common.py 的强类型配置定义。"""

from maibot_sdk import Field, PluginConfigBase
from typing import List

from .types import CommandReplyMode, ProxyScheme, QuotaPeriodMode, ReviewModelTask


class PluginSectionConfig(PluginConfigBase):
    """插件基础配置。"""

    __ui_label__ = "插件基础配置"
    __ui_icon__ = "package"
    __ui_order__ = 0

    enabled: bool = Field(
        default=True,
        description="是否启用插件",
        json_schema_extra={
            "label": "启用插件",
        },
    )
    config_version: str = Field(
        default="2.44.0",
        description="配置版本",
        json_schema_extra={
            "hint": "配置版本",
        },
    )

    image_cache_max_mb: int = Field(
        default=300,
        ge=1,
        le=102400,
        description="生成图片缓存总容量上限（MB），包含原图和 WebP 预览，超出后清理最旧任务的图片",
        json_schema_extra={
            "label": "图片缓存上限（MB）",
            "hint": "默认 300 MB。保存在插件临时目录，超限自动清理较旧图片，保留任务记录；正在保存的任务受保护。",
        },
    )
    log_max_mb: int = Field(
        default=10,
        ge=1,
        le=1024,
        description="插件日志总容量上限（MB），包含当前日志和轮转备份",
        json_schema_extra={
            "label": "日志上限（MB）",
            "hint": "默认 10 MB，包含所有轮转备份；超限自动淘汰最旧日志。",
        },
    )
    upload_cache_max_mb: int = Field(
        default=256,
        ge=40,
        le=102400,
        description="上传图片及图生图输入文件的合计容量上限（MB）",
        json_schema_extra={
            "label": "上传缓存上限（MB）",
            "hint": "默认 256 MB，至少 40 MB；同时保留 24 小时与 100 个文件限制，超限清理最旧上传。",
        },
    )


class GeneralConfig(PluginConfigBase):
    """通用配置。"""

    __ui_label__ = "通用配置"
    __ui_order__ = 1

    default_model: str = Field(
        default="",
        description="留空自动选择已启用平台的可用模型，也可以指定一个平台实例的模型",
        json_schema_extra={
            "label": "默认首选模型",
            "hint": "留空自动选择已启用平台的可用模型，也可以指定一个平台实例的模型",
            "order": 0,
        },
    )
    fallback_model: str = Field(
        default="",
        description="生图备选模型名称。首选模型调用失败或未返回图片时，后台任务会自动尝试该模型；留空表示不启用",
        json_schema_extra={
            "label": "生图备选模型",
            "hint": "首选模型调用失败或未返回图片时自动尝试；需填写已在下方任一平台模型列表中配置的模型名，留空表示不启用",
            "order": 1,
            "hidden": True,
        },
    )
    fallback_models: List[str] = Field(
        default=[],
        max_length=20,
        description="生图备选模型列表，按顺序尝试；旧单个备选模型自动迁入此列表",
        json_schema_extra={
            "label": "生图备选模型",
            "hint": "按需添加并通过上移、下移调整优先级。每个模型的重试次数用尽后再切换到下一个；留空表示不启用备选模型。",
            "order": 1,
        },
    )
    request_retry_count: int = Field(
        default=1,
        ge=0,
        le=5,
        description="同一模型发生明确可安全重试的失败时额外重试的次数；审核拒绝、结果处理失败和受理状态不确定均不重绘",
        json_schema_extra={
            "label": "最多重试次数",
            "hint": "默认额外重试 1 次，可选 0～5 次。仅限连接未建立、明确限流等可安全重试的失败；审核拒绝、结果下载失败或远端状态不确定时停止，不自动重绘。",
            "order": 1.5,
        },
    )
    request_timeout_seconds: int = Field(
        default=150,
        description="单次图片请求超时时间（秒），用于后台图片任务",
        json_schema_extra={
            "label": "图片请求超时",
            "hint": "单次图片请求超时时间（秒），建议设置为 120 到 300",
            "order": 2,
        },
    )
    skip_image_url_ip_check: bool = Field(
        default=False,
        description="忽略提供商返回图片地址的 IP 范围与内网同源限制",
        json_schema_extra={
            "label": "忽略图片地址 IP 校验",
            "hint": "默认关闭。开启后允许下载内网或特殊 DNS 图床，仅用于可信服务；仍检查 HTTP(S) 格式和每次跳转。实际走代理的域名始终由代理解析。",
            "order": 2.5,
        },
    )
    command_reply_mode: CommandReplyMode = Field(
        default="图片",
        description="聊天命令返回形式，可选择图片或文本",
        json_schema_extra={
            "label": "命令返回形式",
            "hint": "图片=使用粉色图片模板回复命令；文本=直接发送纯文本回复",
            "options": ["图片", "文本"],
            "order": 3,
        },
    )
    failure_reason_enabled: bool = Field(
        default=True,
        description="是否由插件主动发送绘图失败状态和简要原因。关闭后仅保留日志、任务状态和工具返回，不主动发送通知",
        json_schema_extra={
            "label": "失败通知附带原因",
            "hint": "开启后，工具和指令失败时会主动发送状态及截断、脱敏后的简要原因；关闭后仅通知 LLM、保留日志和任务状态，不主动发送消息",
            "order": 3.5,
        },
    )
    permission_enabled: bool = Field(
        default=True,
        description="是否启用权限管理。启用后，仅插件管理员可设置首选模型、切换兼容模式、NAI mode 或画师标签，以及修改用户次数",
        json_schema_extra={
            "label": "启用权限管理",
            "hint": "启用后，首选模型设置、兼容模式、NAI mode、NAI 画师标签和次数管理命令仅允许插件管理员使用",
            "order": 4,
        },
    )
    admin_user_ids: list[str] = Field(
        default=[],
        description="插件管理员用户 ID 列表，支持 OneBot QQ 号和 QQ 官方用户 OpenID",
        json_schema_extra={
            "label": "插件管理员列表",
            "hint": "填写允许管理模型、兼容模式和用户次数的用户 ID；OneBot 填 QQ 号，QQ 官方适配器填用户 OpenID",
            "order": 5,
        },
    )
    group_quota_enabled: bool = Field(
        default=True,
        description="是否启用群聊绘图次数管理。管理员不受次数限制",
        json_schema_extra={
            "label": "启用群聊次数管理",
            "hint": "启用后，群聊每次绘图会消耗该群剩余次数；管理员不受限制",
            "order": 6,
        },
    )
    group_quota_period: QuotaPeriodMode = Field(
        default="daily",
        description="群聊次数重置周期：daily / weekly / monthly / once",
        json_schema_extra={
            "label": "群聊次数周期",
            "hint": "daily=每日，weekly=每周，monthly=每月，once=一次性不自动重置",
            "order": 7,
        },
    )
    group_default_quota: int = Field(
        default=5,
        description="群聊在当前周期内默认可用绘图次数。",
        json_schema_extra={
            "label": "群聊默认可用次数",
            "hint": "群聊在所选周期内默认可用的绘图次数",
            "order": 8,
        },
    )
    private_quota_enabled: bool = Field(
        default=True,
        description="是否启用私聊绘图次数管理。管理员不受次数限制",
        json_schema_extra={
            "label": "启用私聊次数管理",
            "hint": "启用后，私聊每次绘图会消耗该用户剩余次数；管理员不受限制",
            "order": 9,
        },
    )
    private_quota_period: QuotaPeriodMode = Field(
        default="daily",
        description="私聊次数重置周期：daily / weekly / monthly / once",
        json_schema_extra={
            "label": "私聊次数周期",
            "hint": "daily=每日，weekly=每周，monthly=每月，once=一次性不自动重置",
            "order": 10,
        },
    )
    private_default_quota: int = Field(
        default=5,
        description="私聊用户在当前周期内默认可用绘图次数。",
        json_schema_extra={
            "label": "私聊默认可用次数",
            "hint": "私聊用户在所选周期内默认可用的绘图次数",
            "order": 11,
        },
    )
    image_edit_unsupported_models: list[str] = Field(
        default=[],
        description="人工标记为仅支持文生图的模型名列表。命中后图生图任务会提前拒绝",
        json_schema_extra={
            "label": "仅支持文生图模型（可选）",
            "hint": "每行一个模型名。人工结果优先于自动识别，命中后不会创建后台图生图任务",
            "order": 12,
        },
    )
    text_to_image_unsupported_models: list[str] = Field(
        default=[],
        description="人工标记为仅支持图生图的模型名列表。命中后文生图任务会提前拒绝",
        json_schema_extra={
            "label": "仅支持图生图模型（可选）",
            "hint": "每行一个模型名。人工结果优先于自动识别，命中后不会创建后台文生图任务",
            "order": 12.5,
        },
    )
    prompt_review_enabled: bool = Field(
        default=False,
        description="是否启用提示词审核。启用后使用所选宿主模型任务审核",
        json_schema_extra={
            "label": "启用提示词审核",
            "hint": "启用后，文生图和图生图的提示词会先交给所选模型审核，通过后才提交生图",
            "order": 13,
        },
    )
    prompt_review_model: ReviewModelTask = Field(
        default="vlm",
        description="提示词审核使用的宿主模型任务",
        json_schema_extra={
            "label": "提示词审核模型",
            "hint": "默认 vlm；沿用 MaiBot 中对应任务组的模型配置，可选 replyer、planner 或 vlm。",
            "order": 13.1,
        },
    )
    prompt_review_timeout_seconds: int = Field(
        default=60, ge=5, le=600,
        description="提示词审核最长等待时间（秒）",
        json_schema_extra={
            "label": "提示词审核等待时间（秒）",
            "hint": "单次默认 60 秒，可设 5～600 秒，重试另计；审核提前完成即继续，失败不会绕过审核。",
            "order": 13.2,
        },
    )
    prompt_review_retry_count: int = Field(
        default=2, ge=0, le=5,
        description="提示词审核失败后额外重试的次数",
        json_schema_extra={
            "label": "提示词审核重试次数",
            "hint": "默认额外重试 2 次，最多调用 3 次；可设 0～5 次，0 表示关闭。明确拒绝和取消不重试。",
            "order": 13.3,
        },
    )
    prompt_review_prompt: str = Field(
        default=(
            "你是绘图提示词审核器。请判断下面的绘图提示词是否适合继续交给绘图模型生成。\n"
            "审核要求：\n"
            "1. 如果提示词涉及明显违法、暴力犯罪、血腥猎奇、未成年人色情、仇恨歧视、现实人物色情深度伪造等高风险内容，必须拒绝。\n"
            "2. 如果提示词内容普通、安全、可接受，则允许通过。\n"
            "3. 你的回复必须严格使用以下格式，不要输出多余内容：\n"
            "结论：PASS 或 REJECT\n"
            "原因：一句简短中文说明\n"
            "\n"
            "待审核提示词：\n"
            "{user_prompt}\n"
        ),
        description="提示词审核模板，支持 {user_prompt} 占位符",
        json_schema_extra={
            "label": "提示词审核模板",
            "hint": "支持 {user_prompt} 占位符；建议要求模型只返回 PASS 或 REJECT 及简短原因",
            "x-widget": "textarea",
            "rows": 8,
            "order": 14,
        },
    )
    image_review_enabled: bool = Field(
        default=False,
        description="是否启用生成图片审核。启用后使用所选宿主模型任务审核",
        json_schema_extra={
            "label": "启用生成图片审核",
            "hint": "启用后，生成完成的图片会先交给所选模型审核，通过后才发送",
            "order": 15,
        },
    )
    image_review_model: ReviewModelTask = Field(
        default="vlm",
        description="生成图片审核使用的宿主模型任务",
        json_schema_extra={
            "label": "图片审核模型",
            "hint": "默认 vlm；也可选择 replyer 或 planner，但该任务组中的模型必须支持图片输入，否则审核会失败。",
            "order": 15.1,
        },
    )
    image_review_timeout_seconds: int = Field(
        default=60, ge=5, le=600,
        description="每张生成图片审核的最长等待时间（秒）",
        json_schema_extra={
            "label": "图片审核等待时间（秒）",
            "hint": "每张图片单次默认 60 秒，可设 5～600 秒，重试另计；与生图及提示词审核分别设置。失败不发送、不重绘。",
            "order": 15.2,
        },
    )
    image_review_retry_count: int = Field(
        default=2, ge=0, le=5,
        description="每张图片审核失败后额外重试的次数",
        json_schema_extra={
            "label": "图片审核重试次数",
            "hint": "默认额外重试 2 次，最多调用 3 次；可设 0～5 次，0 表示关闭。只重试同一图片的审核，明确拒绝和取消不重试。",
            "order": 15.3,
        },
    )
    image_review_prompt: str = Field(
        default=(
            "你是绘图结果审核器。请审核这张图片是否适合直接发送给普通聊天场景。\n"
            "审核要求：\n"
            "1. 如果图片包含明显违法、暴力犯罪、血腥猎奇、未成年人色情、仇恨歧视、现实人物色情深度伪造等高风险内容，必须拒绝。\n"
            "2. 如果图片内容普通、安全、可接受，则允许通过。\n"
            "3. 结合本次生成提示词一起判断。\n"
            "4. 你的回复必须严格使用以下格式，不要输出多余内容：\n"
            "结论：PASS 或 REJECT\n"
            "原因：一句简短中文说明\n"
            "\n"
            "本次生成提示词：\n"
            "{user_prompt}\n"
        ),
        description="生成图片审核模板，支持 {user_prompt} 占位符",
        json_schema_extra={
            "label": "生成图片审核模板",
            "hint": "支持 {user_prompt} 占位符；建议要求模型只返回 PASS 或 REJECT 及简短原因",
            "x-widget": "textarea",
            "rows": 8,
            "order": 16,
        },
    )
    world_knowledge_enabled: bool = Field(
        default=False,
        description="是否启用世界知识：画前检索提示词里的现实对象（游戏角色、战队、赛事、新产品），按词条和参考图作画",
        json_schema_extra={
            "label": "启用世界知识",
            "hint": "默认关闭。启用后群聊画图、工作台和插件 API 都会先识别提示词里的现实对象，查词条库或联网检索，"
                    "把外观描述和参考图交给绘图模型；需要 MaiBot 已配置联网搜索。任何一步失败都按原提示词继续出图。",
            "order": 17,
        },
    )
    world_knowledge_model: ReviewModelTask = Field(
        default="planner",
        description="识别现实对象与整理词条使用的宿主模型任务",
        json_schema_extra={
            "label": "世界知识模型",
            "hint": "默认 planner；沿用 MaiBot 中对应任务组的模型配置，可选 replyer、planner 或 vlm。",
            "order": 17.1,
        },
    )
    world_knowledge_timeout_seconds: int = Field(
        default=60, ge=5, le=600,
        description="画前世界知识阶段的总等待时间（秒）",
        json_schema_extra={
            "label": "世界知识等待时间（秒）",
            "hint": "默认 60 秒，可设 5～600 秒；超时就用已经拿到的词条继续出图，不会让任务失败。",
            "order": 17.2,
        },
    )
    world_knowledge_max_entities: int = Field(
        default=3, ge=0, le=5,
        description="单次绘图最多识别的现实对象个数",
        json_schema_extra={
            "label": "最多识别对象数",
            "hint": "默认 3，可设 0～5；0 表示只用词条库里手工建立或改过的词条，不调用模型识别。",
            "order": 17.3,
        },
    )
    world_knowledge_max_searches: int = Field(
        default=4, ge=0, le=8,
        description="单次绘图最多联网检索的次数",
        json_schema_extra={
            "label": "最多联网检索次数",
            "hint": "默认 4，可设 0～8；词条库里未过期的词条不重复检索，0 表示只用词条库。",
            "order": 17.4,
        },
    )
    world_knowledge_max_reference_images: int = Field(
        default=2, ge=0, le=2,
        description="单次绘图最多附加的词条参考图张数",
        json_schema_extra={
            "label": "最多附加参考图",
            "hint": "默认 2，可设 0～2；还受模型可接收的源图张数限制。附加参考图会让文生图改走图生图，"
                    "不支持图生图的模型只使用文字描述。",
            "order": 17.5,
        },
    )
    world_knowledge_auto_images: bool = Field(
        default=True,
        description="是否为新词条自动查找参考图",
        json_schema_extra={
            "label": "自动查找参考图",
            "hint": "默认开启。先查游戏资料站和维基；找不到时，如果插件配置页的「世界知识搜图」填了密钥，再网搜候选图，由世界知识校验模型挑一张。"
                    "电竞选手和公众人物不自动取图，可在工作台手动上传。",
            "order": 17.6,
        },
    )
    world_knowledge_screen_images: bool = Field(
        default=False,
        description="是否让图片审核模型确认自动找到的参考图确实是该对象",
        json_schema_extra={
            "label": "用模型筛选参考图",
            "hint": "默认关闭。开启后每张自动找到的参考图多一次图片审核模型调用，更准但更慢。",
            "order": 17.7,
        },
    )
    world_knowledge_allow_fake_ip: bool = Field(
        default=False,
        description="检索资料和下载参考图时是否允许代理 TUN 的 Fake-IP 地址段（198.18.0.0/15）",
        json_schema_extra={
            "label": "允许 Fake-IP 地址",
            "hint": "默认关闭。只有在 Clash、sing-box 等 TUN 模式下资料站被解析为 198.18.x.x 而下载失败时才开启，"
                    "其他内网地址始终拒绝。",
            "order": 17.8,
        },
    )
    world_knowledge_verify_enabled: bool = Field(
        default=False,
        description="是否在出图后对照词条参考图检查画得像不像",
        json_schema_extra={
            "label": "出图后校验",
            "hint": "默认关闭。只在本次用到了带外观描述或参考图的词条时检查；只对照提供的参考资料，"
                    "画风和姿势不同不算错。",
            "order": 18,
        },
    )
    world_knowledge_verify_model: ReviewModelTask = Field(
        default="vlm",
        description="出图后校验使用的宿主模型任务，需要支持图片输入",
        json_schema_extra={
            "label": "校验模型",
            "hint": "默认 vlm；所选任务组的模型必须支持多张图片输入，否则校验按通过处理。",
            "order": 18.1,
        },
    )
    world_knowledge_redraw_enabled: bool = Field(
        default=True,
        description="校验发现严重画错时是否自动重画一次",
        json_schema_extra={
            "label": "严重画错时重画一次",
            "hint": "默认开启。只重画 1 次且不额外扣次数，任务耗时约翻倍；重画后再比较一次，保留更准的一张，重画失败保留原图。",
            "order": 18.2,
        },
    )


class ProxyConfig(PluginConfigBase):
    """图片提供商的全局代理配置。"""

    __ui_label__ = "网络代理"
    __ui_order__ = 3

    enabled: bool = Field(
        default=False,
        description="是否为图片提供商启用全局 HTTP 代理。",
        json_schema_extra={
            "label": "启用全局代理",
            "hint": "开启后，除已配置绕过的国内提供商外，所有图片请求都会使用代理",
            "order": 0,
        },
    )
    use_system_proxy: bool = Field(
        default=True,
        description="是否读取系统环境变量中的 HTTP/HTTPS 代理。",
        json_schema_extra={
            "label": "使用系统代理",
            "hint": "开启后读取 HTTP_PROXY、HTTPS_PROXY 和 NO_PROXY；关闭后使用下方手动代理地址",
            "order": 1,
        },
    )
    scheme: ProxyScheme = Field(
        default="http",
        description="手动代理使用的协议。",
        json_schema_extra={
            "label": "手动代理协议",
            "hint": "仅支持 HTTP 或 HTTPS 代理；使用系统代理时忽略",
            "options": ["http", "https"],
            "order": 2,
        },
    )
    host: str = Field(
        default="127.0.0.1",
        description="手动代理 Host。",
        json_schema_extra={
            "label": "手动代理 Host",
            "hint": "例如 127.0.0.1、localhost 或代理服务器域名；使用系统代理时忽略",
            "order": 3,
        },
    )
    port: int = Field(
        default=7890,
        ge=1,
        le=65535,
        description="手动代理端口。",
        json_schema_extra={
            "label": "手动代理端口",
            "hint": "例如 7890；使用系统代理时忽略",
            "order": 4,
        },
    )
    username: str = Field(
        default="",
        description="手动代理认证用户名。",
        json_schema_extra={
            "label": "代理用户名",
            "hint": "代理无需认证时留空；使用系统代理时忽略",
            "order": 5,
        },
    )
    password: str = Field(
        default="",
        description="手动代理认证密码。",
        json_schema_extra={
            "label": "代理密码",
            "hint": "代理无需认证时留空；使用系统代理时忽略",
            "input_type": "password",
            "order": 6,
        },
    )
    bypass_china_providers: bool = Field(
        default=True,
        description="是否让阿里云、火山引擎和硅基流动绕过全局代理。",
        json_schema_extra={
            "label": "国内提供商绕过代理",
            "hint": "开启后，阿里云、火山引擎、硅基流动直连；其他提供商仍按全局代理设置请求",
            "order": 7,
        },
    )
