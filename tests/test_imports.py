"""验证重构后的模块和薄入口能完整导入。"""

from importlib import import_module
from pathlib import Path
from types import ModuleType
import sys

import pytest

_PKG_NAME = "maimai_drawpic_pkg"
if _PKG_NAME not in sys.modules:
    pkg = ModuleType(_PKG_NAME)
    pkg.__path__ = [str(Path(__file__).resolve().parent.parent)]
    sys.modules[_PKG_NAME] = pkg

modules_to_check = [
    "src.maimai_drawpic.infrastructure.media.images",
    "src.maimai_drawpic.infrastructure.storage.tasks",
    "src.maimai_drawpic.infrastructure.storage.quotas",
    "src.maimai_drawpic.domain.parameters",
    "src.maimai_drawpic.interfaces.chat.texts",
    "src.maimai_drawpic.infrastructure.storage.preferences",
    "src.maimai_drawpic.application.moderation",
    "src.maimai_drawpic.interfaces.chat.message_images",
    "src.maimai_drawpic.application.chat",
    "src.maimai_drawpic.application.routing",
    "src.maimai_drawpic.application.drawing",
    "src.maimai_drawpic.domain.configuration.models",
    "src.maimai_drawpic.domain.models.aliyun_profiles",
    "src.maimai_drawpic.domain.models.rinkoai_profiles",
    "src.maimai_drawpic.domain.models.openai_profiles",
    "src.maimai_drawpic.infrastructure.providers.aliyun",
    "src.maimai_drawpic.infrastructure.providers.gemini",
    "src.maimai_drawpic.infrastructure.providers.novelai",
    "src.maimai_drawpic.infrastructure.providers.openai",
    "src.maimai_drawpic.infrastructure.providers.siliconflow",
    "src.maimai_drawpic.infrastructure.providers.volcengine",
    "src.maimai_drawpic.infrastructure.providers.zhipu",
    "src.maimai_drawpic.infrastructure.providers.codex",
    "src.maimai_drawpic.infrastructure.providers.codex_references",
    "src.maimai_drawpic.infrastructure.storage.agent_threads",
    "src.maimai_drawpic.domain.models.codex_profiles",
]


@pytest.mark.parametrize("name", modules_to_check + ["plugin"])
def test_import_module(name: str) -> None:
    import_module(f"{_PKG_NAME}.{name}")
