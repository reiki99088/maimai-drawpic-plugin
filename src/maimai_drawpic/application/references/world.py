"""世界知识作为参考体系的一个来源。

- 点名参考：用户点名的对象在词条库里已有设计图时，先拿词条图当候选，仍由原版识别模型确认匹配，
  不匹配才走网络素材搜索。
- 补位参考：词条参考图与自带图、自我参考、预设、聊天和网络素材共用 8 张 / 40 MiB 额度，只占剩余位置；
  已由素材覆盖的对象和同一张图不重复加入。文生图请求不加图，只注入文字。
"""

from hashlib import sha256
from typing import Any, Awaitable, Callable, Iterable, List, Optional, Sequence, Tuple
import asyncio

from ...domain.references import ReferenceImage
from ...infrastructure.storage.world_knowledge import entry_names, is_usable, normalize_key

MAX_SOURCE_IMAGES = 8
MAX_SOURCE_BYTES = 40 * 1024 * 1024
WORLD_SOURCE = "world"
# 点名参考时每个对象只拿首张词条图（手工图优先）当候选：每张都占原版 12 次识别预算
MAX_CANDIDATES_PER_NEED = 1

MaterialFinder = Callable[[Any], Awaitable[List[ReferenceImage]]]


def world_material_finder(store: Any) -> MaterialFinder:
    """按点名对象查词条库，返回词条参考图作为候选；查不到、已停用或没有图时返回空列表。"""

    async def find(need: Any) -> List[ReferenceImage]:
        def read() -> List[ReferenceImage]:
            entry = store.find(need.mention, None, [need.subject])
            if entry is None or not is_usable(entry):
                return []
            images: List[ReferenceImage] = []
            for ref in entry["refs"][:MAX_CANDIDATES_PER_NEED]:
                data = store.read_image(entry["id"], ref["file"])
                if data:
                    images.append(ReferenceImage(data, WORLD_SOURCE))
            return images

        return await asyncio.to_thread(read)

    return find


def covered_keys(subjects: Iterable[str]) -> set:
    return {key for key in (normalize_key(subject) for subject in subjects) if key}


def select_world_images(
    resolution: Any, *, existing: Sequence[bytes], covered: Iterable[str], slots: int,
) -> List[Tuple[str, bytes]]:
    """从本次检索到的词条图里挑出能补进请求的几张（词条 id, 图片），按词条顺序。"""
    if slots <= 0:
        return []
    covered_names = covered_keys(covered)
    digests = {sha256(data).hexdigest() for data in existing}
    size = sum(len(data) for data in existing)
    entries = {entry["id"]: entry for entry in resolution.entries}
    chosen: List[Tuple[str, bytes]] = []
    for entry_id, data in resolution.images:
        if len(chosen) >= slots or len(digests) >= MAX_SOURCE_IMAGES:
            break
        entry: Optional[dict] = entries.get(entry_id)
        if entry is None or covered_names & covered_keys(entry_names(entry)):
            continue
        digest = sha256(data).hexdigest()
        if digest in digests or size + len(data) > MAX_SOURCE_BYTES:
            continue
        chosen.append((entry_id, data))
        digests.add(digest)
        size += len(data)
    return chosen
