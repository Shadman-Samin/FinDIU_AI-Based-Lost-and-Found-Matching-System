import io

from PIL import Image, ImageOps, UnidentifiedImageError

from backend.app.errors import ServiceFailure

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 20_000_000


def prepare_image(raw: bytes) -> bytes:
    if len(raw) > MAX_BYTES:
        raise ServiceFailure("image_too_large")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if getattr(image, "is_animated", False):
                raise ServiceFailure("animated_image_not_allowed")
            width, height = image.size
            if width * height > MAX_PIXELS:
                raise ServiceFailure("image_dimensions_too_large")
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=88, optimize=True, exif=b"")
            return output.getvalue()
    except ServiceFailure:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise ServiceFailure("invalid_image") from None
