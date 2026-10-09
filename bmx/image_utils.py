"""Shared image helpers used across apps (avatar normalization, etc.)."""
from io import BytesIO

from django.conf import settings
from PIL import Image, ImageFile, ImageOps, features


def normalize_avatar_image(image_file):
    """Resize and re-encode an avatar image to a square WEBP (or JPEG fallback).

    ``image_file`` must be an already-open binary file-like object. Returns a
    ``(content_bytes, extension)`` tuple. Raises the usual Pillow errors
    (``FileNotFoundError``, ``UnidentifiedImageError``, ``OSError``) to the
    caller so they can be mapped to domain-specific messages.
    """
    final_size = int(getattr(settings, "AVATAR_FINAL_IMAGE_SIZE", 512))
    output_quality = int(getattr(settings, "AVATAR_FINAL_IMAGE_QUALITY", 86))
    preferred_format = "WEBP" if features.check("webp") else "JPEG"
    extension = "webp" if preferred_format == "WEBP" else "jpg"
    original_truncated_setting = ImageFile.LOAD_TRUNCATED_IMAGES

    try:
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        image = Image.open(image_file)
        image.load()
        image = ImageOps.exif_transpose(image).convert("RGB")
        image = ImageOps.fit(
            image,
            (final_size, final_size),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
        output = BytesIO()
        try:
            if preferred_format == "WEBP":
                image.save(output, format="WEBP", quality=output_quality, method=6)
            else:
                image.save(output, format="JPEG", quality=90, optimize=True)
        except (OSError, KeyError):
            output = BytesIO()
            image.save(output, format="JPEG", quality=90, optimize=True)
            extension = "jpg"
    finally:
        ImageFile.LOAD_TRUNCATED_IMAGES = original_truncated_setting

    output.seek(0)
    return output.read(), extension
