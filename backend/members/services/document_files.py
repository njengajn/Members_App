import re
from datetime import date
from pathlib import Path
from uuid import uuid4
from io import BytesIO
from django.core.files.base import ContentFile
from PIL import Image


def sanitize_filename_part(value, fallback="document"):
    """
    Convert a filename/title into a safe filename component.

    Keeps the filename readable while removing unsafe characters.
    """

    if not value:
        return fallback

    value = str(value).strip()

    # Remove extension if one happens to be included.
    value = Path(value).stem

    # Replace anything other than letters/numbers with a hyphen.
    value = re.sub(r"[^A-Za-z0-9]+", "-", value)

    # Remove repeated hyphens.
    value = re.sub(r"-+", "-", value)

    # Remove leading/trailing hyphens.
    value = value.strip("-")

    return value[:80] or fallback


def prepare_document_file(
    uploaded_file,
    member,
    document_title="document",
):
    """
    Prepare an uploaded document with a meaningful,
    collision-resistant stored filename.

    The original browser filename is preserved separately
    by the caller.

    Example:

        passport_scan.jpg

    becomes:

        KRO-1001-passport-2026-08-09-a83f2c.jpg
    """

    original_name = uploaded_file.name or "document"

    extension = Path(original_name).suffix.lower()

    if not extension:
        extension = ""

    # --------------------------------------------------
    # MEMBER IDENTIFIER
    # --------------------------------------------------

    member_uid = getattr(member, "member_uid", None)

    if member_uid:
        member_identifier = sanitize_filename_part(
            member_uid,
            fallback=f"member-{member.pk}",
        )
    else:
        member_identifier = f"member-{member.pk}"

    # --------------------------------------------------
    # DOCUMENT NAME
    # --------------------------------------------------

    document_name = sanitize_filename_part(
        document_title,
        fallback="document",
    )

    # --------------------------------------------------
    # DATE
    # --------------------------------------------------

    upload_date = date.today().isoformat()

    # --------------------------------------------------
    # COLLISION-RESISTANT IDENTIFIER
    # --------------------------------------------------

    unique_suffix = uuid4().hex[:6]

    # --------------------------------------------------
    # FINAL STORED NAME
    # --------------------------------------------------

    stored_filename = (
        f"{member_identifier}-"
        f"{document_name}-"
        f"{upload_date}-"
        f"{unique_suffix}"
        f"{extension}"
    )

    # Keep the generated name safely below common
    # filesystem/storage limits.
    uploaded_file.name = stored_filename

    prepared_file = compress_uploaded_image(
        uploaded_file
    )

    # Preserve the browser-uploaded filename for the caller.
    prepared_file._original_filename = original_name

    return prepared_file

def compress_uploaded_image(
    uploaded_file,
    quality=85,
    minimum_size=300 * 1024,
):
    """
    Compress an uploaded image when worthwhile.

    Step 4 scope:
    - JPEG/JPG: recompress at the requested quality.
    - PNG: optimise without changing format.
    - WebP: recompress at the requested quality.
    - Other file types: leave unchanged.
    - Do not resize images.
    - Do not convert PNG to another format.
    - Keep the original uploaded file if compression does
      not produce a smaller file.

    Returns the original uploaded file or a replacement
    ContentFile with the same filename.
    """

    if not uploaded_file:
        return uploaded_file

    original_size = getattr(uploaded_file, "size", 0) or 0

    # Avoid processing small images where compression is
    # unlikely to provide a meaningful benefit.
    if original_size < minimum_size:
        return uploaded_file

    extension = Path(
        getattr(uploaded_file, "name", "")
    ).suffix.lower()

    supported_extensions = {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
    }

    if extension not in supported_extensions:
        return uploaded_file

    try:
        uploaded_file.seek(0)

        image = Image.open(uploaded_file)

        # Verify that Pillow can fully read the image.
        image.verify()

        uploaded_file.seek(0)
        image = Image.open(uploaded_file)

    except Exception:
        # If Pillow cannot process the image, leave the
        # original upload untouched.
        try:
            uploaded_file.seek(0)
        except Exception:
            pass

        return uploaded_file

    output = BytesIO()

    try:
        save_kwargs = {}

        # -------------------------------------------------
        # JPEG
        # -------------------------------------------------

        if extension in {".jpg", ".jpeg"}:

            # JPEG cannot store transparency.
            if image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")

            save_kwargs = {
                "format": "JPEG",
                "quality": quality,
                "optimize": True,
                "progressive": True,
            }

        # -------------------------------------------------
        # PNG
        # -------------------------------------------------

        elif extension == ".png":

            save_kwargs = {
                "format": "PNG",
                "optimize": True,
            }

        # -------------------------------------------------
        # WEBP
        # -------------------------------------------------

        elif extension == ".webp":

            save_kwargs = {
                "format": "WEBP",
                "quality": quality,
                "method": 6,
            }

        image.save(output, **save_kwargs)

    except Exception:
        return uploaded_file

    compressed_data = output.getvalue()

    # -----------------------------------------------------
    # Only use the compressed version if it is smaller.
    # -----------------------------------------------------

    if not compressed_data:
        return uploaded_file

    if len(compressed_data) >= original_size:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass

        return uploaded_file

    compressed_file = ContentFile(
        compressed_data,
        name=uploaded_file.name,
    )

    return compressed_file