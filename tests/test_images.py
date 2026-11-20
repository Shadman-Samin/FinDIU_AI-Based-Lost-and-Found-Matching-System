import io

import pytest
from PIL import Image


def image_bytes(mode="RGB", size=(80, 40), format="PNG"):
    image = Image.new(mode, size, (20, 40, 60, 255) if "A" in mode else (20, 40, 60))
    output = io.BytesIO()
    image.save(output, format=format)
    return output.getvalue()


def test_filename_cannot_make_text_an_image():
    from backend.app.errors import ServiceFailure
    from backend.app.image_utils import prepare_image

    with pytest.raises(ServiceFailure):
        prepare_image(b"this is not an image")


def test_image_is_reencoded_as_small_metadata_free_jpeg():
    from backend.app.image_utils import prepare_image

    prepared = prepare_image(image_bytes(size=(2000, 1000)))
    result = Image.open(io.BytesIO(prepared))
    assert result.format == "JPEG"
    assert max(result.size) <= 1024
    assert not result.getexif()


def test_animated_image_is_rejected():
    from backend.app.errors import ServiceFailure
    from backend.app.image_utils import prepare_image

    frame = Image.new("RGB", (10, 10), "red")
    second = Image.new("RGB", (10, 10), "blue")
    output = io.BytesIO()
    frame.save(output, format="GIF", save_all=True, append_images=[second], loop=0)
    with pytest.raises(ServiceFailure):
        prepare_image(output.getvalue())
