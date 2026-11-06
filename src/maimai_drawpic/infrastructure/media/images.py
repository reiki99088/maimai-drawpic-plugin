from __future__ import annotations

from PIL import Image as PILImage
from io import BytesIO

MAX_IMAGE_BYTES = 25 * 1024 * 1024
# Allow square 4K and panoramic model output without permitting arbitrary rasters.
MAX_IMAGE_PIXELS = 4096 * 4096
MAX_IMAGE_DIMENSION = 8192


def check_image_dimensions(image) -> int:
    width, height = image.size
    if (width <= 0 or height <= 0 or max(width, height) > MAX_IMAGE_DIMENSION
            or width * height > MAX_IMAGE_PIXELS):
        raise ValueError("图片像素超过限制：最长边 8192，单张最多 16777216 像素")
    return width * height



_MIME_TYPE_MAP = {
    "BMP": "image/bmp",
    "GIF": "image/gif",
    "JPEG": "image/jpeg",
    "JPG": "image/jpeg",
    "PNG": "image/png",
    "TIFF": "image/tiff",
    "WEBP": "image/webp",
}


def validate_image_bytes(image_bytes: bytes) -> bytes:
    """校验图片大小与内容，并返回原始字节。"""

    if not image_bytes:
        raise ValueError("图片数据为空")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError(f"图片大小超过限制：{MAX_IMAGE_BYTES} 字节")
    with PILImage.open(BytesIO(image_bytes)) as image:
        check_image_dimensions(image)
        image.verify()
    return image_bytes


def detect_mime_type(image_bytes: bytes) -> str:
    """尽量根据图片内容推断 MIME 类型，无法识别时回退 image/png。"""

    with PILImage.open(BytesIO(image_bytes)) as image:
        format_name = str(image.format or "").upper()
    return _MIME_TYPE_MAP.get(format_name, "image/png")


def detect_image_dimensions(image_bytes: bytes) -> tuple[int, int] | None:
    """读取图片像素尺寸，异常或非正尺寸返回 None。"""

    with PILImage.open(BytesIO(image_bytes)) as image:
        width, height = image.size
    if width <= 0 or height <= 0:
        return None
    return width, height


def detect_image_format(image_bytes: bytes) -> str:
    """根据图片字节推断格式名（小写），仅保留常见可发送格式。"""

    with PILImage.open(BytesIO(image_bytes)) as image:
        format_name = str(image.format or "").strip().lower()
    if format_name in {"jpg", "jpeg", "png", "webp", "gif"}:
        return format_name
    return "png"


MAX_GIF_FRAMES = 64
_REVIEW_SHEET_FRAMES = 16
_REVIEW_SHEET_EDGE = 2048


def gif_frame_count(image_bytes: bytes) -> int:
    """非 GIF 返回 0；GIF 返回帧数，帧数异常多时拒绝解码。"""

    with PILImage.open(BytesIO(image_bytes)) as image:
        if str(image.format or "").upper() != "GIF":
            return 0
        frames = int(getattr(image, "n_frames", 1) or 1)
    if frames > MAX_GIF_FRAMES:
        raise ValueError(f"GIF 帧数超过限制：最多 {MAX_GIF_FRAMES} 帧")
    return frames


def _rgba_frame(image) -> PILImage.Image:
    return image.convert("RGBA") if image.mode in {"P", "LA", "RGBA"} else image.convert("RGB")


def first_frame_png(image_bytes: bytes) -> bytes:
    """上游编辑接口只接受静态图；GIF 源图取首帧转 PNG。"""

    with PILImage.open(BytesIO(image_bytes)) as image:
        image.seek(0)
        frame = _rgba_frame(image)
    output = BytesIO()
    frame.save(output, format="PNG")
    return output.getvalue()


def review_image_payload(image_bytes: bytes) -> tuple[bytes, str]:
    """审核模型只看静态图：GIF 拼成一张最多 16 帧的 PNG 联系表，避免只审首帧。"""

    with PILImage.open(BytesIO(image_bytes)) as image:
        if str(image.format or "").upper() != "GIF":
            return image_bytes, detect_image_format(image_bytes)
        total = min(int(getattr(image, "n_frames", 1) or 1), MAX_GIF_FRAMES)
        step = max(1, -(-total // _REVIEW_SHEET_FRAMES))
        frames = []
        for index in range(0, total, step):
            image.seek(index)
            frames.append(_rgba_frame(image).convert("RGB"))
    columns = min(len(frames), 4)
    rows = -(-len(frames) // columns)
    width, height = frames[0].size
    scale = min(1.0, _REVIEW_SHEET_EDGE / max(width * columns, height * rows))
    cell = (max(1, int(width * scale)), max(1, int(height * scale)))
    sheet = PILImage.new("RGB", (cell[0] * columns, cell[1] * rows), "white")
    for index, frame in enumerate(frames):
        sheet.paste(frame.resize(cell), ((index % columns) * cell[0], (index // columns) * cell[1]))
    output = BytesIO()
    sheet.save(output, format="PNG")
    return output.getvalue(), "png"
