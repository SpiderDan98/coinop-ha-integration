"""Re-encoding every stored image: upright, without metadata, downscaled, WebP."""

from collections.abc import Collection
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

FULL_EDGE = 1600
TILE_EDGE = 480
QUALITY = 80


class InvalidImage(Exception):
    """The bytes are not an image Pillow can read."""


def _webp(image: Image.Image, edge: int) -> bytes:
    scaled = image.copy()
    scaled.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    scaled.save(buffer, "WEBP", quality=QUALITY)
    return buffer.getvalue()


def encode(data: bytes, formats: Collection[str] | None = None) -> tuple[bytes, bytes]:
    """The full image and its tile; blocking, so run it in the executor.

    `formats` limits which Pillow formats are accepted; any readable one by default.
    """
    try:
        with Image.open(BytesIO(data)) as source:
            if formats is not None and source.format not in formats:
                raise InvalidImage(f"{source.format} is not accepted")
            upright = ImageOps.exif_transpose(source)
            mode = "RGBA" if upright.has_transparency_data else "RGB"
            # A new image from the pixels alone carries no EXIF, XMP or ICC data.
            clean = Image.new(mode, upright.size)
            clean.paste(upright.convert(mode))
    except (UnidentifiedImageError, OSError, ValueError) as err:
        raise InvalidImage from err
    return _webp(clean, FULL_EDGE), _webp(clean, TILE_EDGE)
