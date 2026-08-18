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
    max_dimension=2000,
):
    """
    Compress, convert, and resize an uploaded image when worthwhile.

    Step 4 / Step 5 / Step 6 scope:
    - JPEG/JPG: recompress at the requested quality.
    - PNG:
        - For qualifying PNG files, attempt conversion to JPEG.
        - Transparent PNGs are composited onto a white background.
        - When no resizing is required, preserve the existing
          Step 5 rule: use JPEG only when it is smaller than the
          original uploaded PNG.
        - When resizing is required, compare JPEG against the
          resized PNG and use whichever is smaller.
    - WebP: recompress at the requested quality.
    - Images larger than max_dimension are resized while preserving
      aspect ratio.
    - Images are never enlarged.
    - Other file types: leave unchanged.
    - Keep the original uploaded file when processing is unnecessary
      and the processed version does not provide a benefit.

    Important:
    - Resizing is mandatory when an image exceeds max_dimension.
    - PNG-to-JPEG conversion remains subject to the existing
      Step 5 size-saving rule.
    - If a PNG requires resizing but JPEG conversion is not
      beneficial compared with the resized PNG, the resized PNG
      is retained.
    - No image is ever upscaled.

    Returns the original uploaded file or a replacement
    ContentFile with the appropriate stored filename.
    """

    if not uploaded_file:
        return uploaded_file

    original_size = getattr(uploaded_file, "size", 0) or 0

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

    # -----------------------------------------------------
    # OPEN AND VERIFY IMAGE
    # -----------------------------------------------------

    try:
        uploaded_file.seek(0)

        image = Image.open(uploaded_file)

        # Verify that Pillow can fully read the image.
        image.verify()

        uploaded_file.seek(0)
        image = Image.open(uploaded_file)

        # Load image data before further processing.
        image.load()

    except Exception:
        # If Pillow cannot process the image, leave the
        # original upload untouched.
        try:
            uploaded_file.seek(0)
        except Exception:
            pass

        return uploaded_file

    original_dimensions = image.size

    # -----------------------------------------------------
    # DETERMINE WHETHER RESIZING IS REQUIRED
    # -----------------------------------------------------

    needs_resize = (
        image.width > max_dimension
        or image.height > max_dimension
    )

    # -----------------------------------------------------
    # SMALL IMAGE WITHIN DIMENSION LIMIT
    #
    # No compression/conversion is necessary for files below
    # the existing Step 4/5 threshold when they also do not
    # require resizing.
    # -----------------------------------------------------

    if original_size < minimum_size and not needs_resize:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass

        return uploaded_file

    # -----------------------------------------------------
    # CREATE RESIZED WORKING IMAGE
    #
    # thumbnail() preserves aspect ratio and never enlarges
    # an image.
    # -----------------------------------------------------

    if needs_resize:
        image.thumbnail(
            (max_dimension, max_dimension),
            Image.Resampling.LANCZOS,
        )

    resized_dimensions = image.size

    dimensions_changed = (
        resized_dimensions != original_dimensions
    )

    # -----------------------------------------------------
    # PREPARE OUTPUT
    # -----------------------------------------------------

    output = BytesIO()

    try:

        # -------------------------------------------------
        # JPEG / JPG
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

            output_extension = extension

            image.save(
                output,
                **save_kwargs,
            )

        # -------------------------------------------------
        # PNG
        # -------------------------------------------------

        elif extension == ".png":

            # -------------------------------------------------
            # PNG → JPEG
            #
            # JPEG cannot store transparency.
            # Transparent PNGs are therefore composited onto
            # a white RGB background before JPEG conversion.
            # -------------------------------------------------

            if "A" in image.getbands():

                rgba_image = image.convert("RGBA")

                background = Image.new(
                    "RGB",
                    rgba_image.size,
                    "white",
                )

                background.paste(
                    rgba_image,
                    mask=rgba_image.getchannel("A"),
                )

                jpeg_image = background

            else:
                jpeg_image = image.convert("RGB")

            jpeg_output = BytesIO()

            jpeg_image.save(
                jpeg_output,
                format="JPEG",
                quality=quality,
                optimize=True,
                progressive=True,
            )

            jpeg_data = jpeg_output.getvalue()

            # -------------------------------------------------
            # Create the PNG representation of the image being
            # processed. If resizing occurred, this represents
            # the resized PNG fallback.
            # -------------------------------------------------

            png_output = BytesIO()

            if image.mode not in {
                "1",
                "L",
                "P",
                "RGB",
                "RGBA",
                "LA",
            }:
                png_image = image.convert("RGBA")
            else:
                png_image = image

            png_image.save(
                png_output,
                format="PNG",
                optimize=True,
            )

            png_data = png_output.getvalue()

            # -------------------------------------------------
            # Preserve Step 5 behaviour when no resizing was
            # required:
            #
            # JPEG must be smaller than the ORIGINAL uploaded
            # PNG, not merely smaller than a newly generated
            # optimized PNG.
            #
            # When resizing was required, compare JPEG against
            # the RESIZED PNG because that is the PNG fallback
            # that would actually be stored.
            # -------------------------------------------------

            if needs_resize:

                use_jpeg = len(jpeg_data) < len(png_data)

            else:

                use_jpeg = len(jpeg_data) < original_size

            if use_jpeg:

                output = BytesIO(jpeg_data)
                output_extension = ".jpg"

            else:

                output = BytesIO(png_data)
                output_extension = ".png"

        # -------------------------------------------------
        # WEBP
        # -------------------------------------------------

        elif extension == ".webp":

            save_kwargs = {
                "format": "WEBP",
                "quality": quality,
                "method": 6,
            }

            output_extension = extension

            image.save(
                output,
                **save_kwargs,
            )

    except Exception:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass

        return uploaded_file

    processed_data = output.getvalue()

    # -----------------------------------------------------
    # INVALID OUTPUT
    # -----------------------------------------------------

    if not processed_data:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass

        return uploaded_file

    # -----------------------------------------------------
    # DECIDE WHETHER TO USE PROCESSED FILE
    #
    # Resizing is mandatory when dimensions exceeded the
    # maximum, so the resized result must be used.
    #
    # If no resizing occurred, retain the existing Step 4/5
    # rule: only use the processed file when it is smaller.
    # -----------------------------------------------------

    if not dimensions_changed:

        if len(processed_data) >= original_size:

            try:
                uploaded_file.seek(0)
            except Exception:
                pass

            return uploaded_file

    # -----------------------------------------------------
    # UPDATE STORED FILENAME WHEN FORMAT CHANGES
    # -----------------------------------------------------

    processed_name = uploaded_file.name

    if extension == ".png":

        processed_name = str(
            Path(uploaded_file.name).with_suffix(
                output_extension
            )
        )

    compressed_file = ContentFile(
        processed_data,
        name=processed_name,
    )

    return compressed_file