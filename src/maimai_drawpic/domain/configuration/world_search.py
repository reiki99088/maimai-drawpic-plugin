"""世界知识网搜取图的搜索服务配置；含密钥，只保存在宿主管理的 config.toml。"""

from maibot_sdk import Field, PluginConfigBase
from pydantic import field_validator
from typing import List, Literal

IMAGE_SEARCH_PROVIDERS = ("openai", "brave", "tavily")
ImageSearchStrategy = Literal["ordered", "round_robin"]


class WorldSearchConfig(PluginConfigBase):
    """固定图源找不到参考图时，用这些搜索服务搜图，再由图片模型挑出真正对应的一张。"""

    __ui_label__ = "世界知识搜图"
    __ui_order__ = 4

    order: List[str] = Field(
        default=["openai", "tavily", "brave"],
        description="参与搜图的服务及先后顺序，可选 openai、brave、tavily",
        json_schema_extra={
            "label": "搜图服务顺序",
            "hint": "可选 openai、tavily、brave，默认按这个顺序（实测中文对象 OpenAI 最准、Tavily 次之、Brave 偏新闻图）；"
                    "没填密钥的服务自动跳过，全部没填时不网搜取图，只用游戏资料站和维基。",
            "order": 0,
        },
    )
    strategy: ImageSearchStrategy = Field(
        default="ordered",
        description="多个服务之间的使用方式",
        json_schema_extra={
            "label": "使用方式",
            "hint": "ordered：每次都从第一个开始，失败或没有合适的图才换下一个；round_robin：每次换一个起点轮流使用，均摊额度。"
                    "两种方式下，同一个对象最多试 2 个服务。",
            "order": 1,
        },
    )
    max_candidates: int = Field(
        default=8, ge=2, le=12,
        description="每次搜图交给图片模型挑选的候选张数",
        json_schema_extra={
            "label": "候选张数",
            "hint": "默认 8，可设 2～12；先按尺寸、比例和站点过滤，再把缩略图交给世界知识校验模型挑一张，挑不出就不用图。",
            "order": 2,
        },
    )
    openai_api_key: str = Field(
        default="",
        description="OpenAI 搜图使用的 API 密钥（Responses API web_search）",
        json_schema_extra={
            "label": "OpenAI 密钥",
            "hint": "留空表示不用 OpenAI 搜图；与绘图平台的密钥互不影响。每次搜图都会产生搜索工具费和少量模型 token 费。",
            "input_type": "password",
            "order": 3,
        },
    )
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        description="OpenAI 搜图的 API 根地址",
        json_schema_extra={
            "label": "OpenAI 地址",
            "hint": "填到 /v1 为止；中转服务必须支持 Responses API 的 web_search 工具和图片结果。",
            "order": 4,
        },
    )
    openai_model: str = Field(
        default="gpt-5.5",
        description="OpenAI 搜图使用的模型",
        json_schema_extra={
            "label": "OpenAI 模型",
            "hint": "需要支持 web_search 工具返回图片结果的模型。",
            "order": 5,
        },
    )
    brave_api_key: str = Field(
        default="",
        description="Brave Search API 密钥（图片搜索）",
        json_schema_extra={
            "label": "Brave 密钥",
            "hint": "留空表示不用 Brave；使用 Brave 图片搜索接口，结果带原图尺寸和缩略图。",
            "input_type": "password",
            "order": 6,
        },
    )
    tavily_api_key: str = Field(
        default="",
        description="Tavily API 密钥（网页搜索附带图片）",
        json_schema_extra={
            "label": "Tavily 密钥",
            "hint": "留空表示不用 Tavily；返回搜到的网页里的图片和图片描述，每次 1 个 credit。",
            "input_type": "password",
            "order": 7,
        },
    )

    @field_validator("order", mode="before")
    @classmethod
    def _normalize_order(cls, value):
        if isinstance(value, str):
            value = [part for part in value.replace("，", ",").split(",")]
        if not isinstance(value, list):
            raise ValueError("搜图服务顺序必须是列表")
        result: List[str] = []
        for item in value:
            name = str(item or "").strip().lower()
            if not name:
                continue
            if name not in IMAGE_SEARCH_PROVIDERS:
                raise ValueError(f"未知的搜图服务：{name}（可选 openai、brave、tavily）")
            if name not in result:
                result.append(name)
        return result

    @field_validator("openai_base_url")
    @classmethod
    def _normalize_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("https://", "http://")):
            raise ValueError("OpenAI 搜图地址必须以 http:// 或 https:// 开头")
        return value

    @field_validator("openai_api_key", "brave_api_key", "tavily_api_key", "openai_model")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()
