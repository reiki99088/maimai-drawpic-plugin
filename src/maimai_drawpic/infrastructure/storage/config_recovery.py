"""识别并备份移除已知升级错误生成的完整默认配置。"""

from hashlib import sha256
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4
import json
import shutil
import tomlkit

from .atomic import write_text_atomically


RESEEDED_SECTIONS = (
    "general", "style", "openai", "google", "zhipu", "aliyun", "volcengine",
    "siliconflow", "novelai", "comfyui", "agnes",
)
# 固定为 d689e63 / 2.37.0 和 95ec2ed / 2.38.0 的历史指纹，不能随当前
# 配置模型重新计算。完整输入样本保存在 tests/fixtures/reseeded-defaults-*.toml。
KNOWN_RESEEDED_DEFAULTS = {
    "2.37.0": (RESEEDED_SECTIONS[:-1], "075c49d00e2f2f116a6a7713e54fe00970b87da552b9e3fb0660d7653634be0f"),
    "2.38.0": (RESEEDED_SECTIONS, "66a34db1d5c52d507b880a17c6272debe0fe1b73cc9852261871bdf8e09f1586"),
}


def is_reseeded_defaults(document: Dict[str, Any]) -> bool:
    """只有已知版本、完整节集合和每个默认值均匹配时才识别为误生成。"""
    plugin = document.get("plugin")
    if not isinstance(plugin, dict) or not isinstance(plugin.get("config_version"), str):
        return False
    known = KNOWN_RESEEDED_DEFAULTS.get(plugin["config_version"])
    if known is None:
        return False
    sections, expected = known
    # world_search 是后来加的宿主节，Runner 可能先补进默认值；它不属于误生成的绘图设置。
    if set(document) - {"world_search"} != {"plugin", "proxy", *sections}:
        return False
    values = {section: document[section] for section in sections}
    try:
        encoded = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError):
        # TOML 中的日期等非 JSON 值不可能来自这份历史默认模板，留给正常迁移校验。
        return False
    return sha256(encoded).hexdigest() == expected


def remove_reseeded_defaults(config_path: Path, data_dir: Path, original: bytes) -> Path:
    """调用方先验证 JSON 和配置冲突；这里逐字节备份，再原子移除重复节。"""
    document = tomlkit.parse(original.decode("utf-8"))
    if not is_reseeded_defaults(document):
        raise ValueError("config.toml 不匹配已知误生成配置，已保留原文件")
    if config_path.read_bytes() != original:
        raise ValueError("config.toml 已在外部修改，已保留原文件，请重新加载插件")
    version = document["plugin"]["config_version"]
    backup = data_dir / "migration_backups" / f"config-reseeded-{version}-{uuid4().hex}.toml"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(config_path, backup)
    if backup.read_bytes() != original:
        raise RuntimeError("误生成配置备份校验失败，已保留原文件")
    if config_path.read_bytes() != original:
        raise ValueError("config.toml 已在外部修改，已保留原文件，请重新加载插件")
    for section in KNOWN_RESEEDED_DEFAULTS[version][0]:
        document.pop(section)
    write_text_atomically(config_path, tomlkit.dumps(document))
    return backup
