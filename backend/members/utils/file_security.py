# backend/members/utils/file_security.py

from PIL import Image
import io


def compress_image(file):
    """
    Compress image before saving
    """
    img = Image.open(file)
    img = img.convert("RGB")

    output = io.BytesIO()
    img.save(output, format="JPEG", quality=70)

    output.seek(0)
    return output


def validate_file(file):
    """
    Basic virus-safe validation (extend with ClamAV later)
    """
    allowed_types = ["image/jpeg", "image/png"]

    if file.content_type not in allowed_types:
        raise ValueError("Unsupported file type")

    if file.size > 5 * 1024 * 1024:
        raise ValueError("File too large")