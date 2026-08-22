import re
from datetime import date
from pathlib import Path
from uuid import uuid4
from io import BytesIO
from django.core.files.base import ContentFile
from PIL import Image
import logging

logger = logging.getLogger(__name__)

# =========================================================
# STEP 7 - DOCUMENT UPLOAD VALIDATION
# =========================================================
#
# Maximum size of the ORIGINAL uploaded file.
#
# This limit is deliberately checked before image
# compression, PNG conversion, resizing, or saving.
# =========================================================

MAX_DOCUMENT_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


# =========================================================
# STEP 7 - PERMITTED DOCUMENT TYPES
# =========================================================
#
# The Members App currently intends to accept:
#
#   - JPEG / JPG images
#   - PNG images
#   - WebP images
#   - PDF documents
#
# Other formats that the MemberDocument model can classify
# are NOT automatically permitted for uploading.
# =========================================================

ALLOWED_DOCUMENT_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".pdf",
}


# =========================================================
# STEP 7 - EXPECTED IMAGE FORMATS
# =========================================================
#
# Used to verify that the actual image content matches
# the filename extension.
# =========================================================

EXPECTED_IMAGE_FORMATS = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
}


class DocumentUploadValidationError(ValueError):
    """
    Raised when an uploaded document fails the central
    Members App upload validation rules.

    The messages raised by this exception are deliberately
    safe for display to members/admins.
    """

def validate_document_upload(uploaded_file):
    """
    Centrally validate an uploaded MemberDocument.

    Validation performed here:
        1. File must exist.
        2. Original file must not exceed 10 MB.
        3. Extension must be permitted.
        4. Browser-provided content_type is not trusted.
        5. Images must be valid images according to Pillow.
        6. Image content must match the filename extension.
        7. PDFs must contain the PDF file signature.

    Validation happens before image processing or saving.

    Returns:
        The original uploaded file, unchanged.

    Raises:
        DocumentUploadValidationError:
            If the upload fails validation.
    """

    # -----------------------------------------------------
    # FILE PRESENCE
    # -----------------------------------------------------

    if not uploaded_file:
        raise DocumentUploadValidationError(
            "Please select a document to upload."
        )

    # -----------------------------------------------------
    # ORIGINAL FILE SIZE
    # -----------------------------------------------------
    #
    # Check the incoming file before Pillow processes it.
    # A large image must not be accepted simply because it
    # could later be compressed to a smaller file.
    # -----------------------------------------------------

    file_size = getattr(
        uploaded_file,
        "size",
        None,
    )

    if file_size is None:
        raise DocumentUploadValidationError(
            "The uploaded file could not be verified."
        )

    if file_size <= 0:
        raise DocumentUploadValidationError(
            "The uploaded file is empty."
        )

    if file_size > MAX_DOCUMENT_UPLOAD_SIZE:
        raise DocumentUploadValidationError(
            "File too large. "
            "The maximum allowed size is 10 MB."
        )

    # -----------------------------------------------------
    # FILE EXTENSION
    # -----------------------------------------------------

    original_name = (
        getattr(
            uploaded_file,
            "name",
            "",
        )
        or ""
    )

    extension = Path(
        original_name
    ).suffix.lower()

    if extension not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise DocumentUploadValidationError(
            "Unsupported file type. "
            "Please upload a PDF, JPEG, PNG, or WebP file."
        )

    # -----------------------------------------------------
    # READ FILE HEADER
    # -----------------------------------------------------
    #
    # Do not use uploaded_file.content_type as the security
    # decision. That value originates from the client.
    # -----------------------------------------------------

    try:
        uploaded_file.seek(0)
        header = uploaded_file.read(16)
        uploaded_file.seek(0)

    except (AttributeError, OSError):
        raise DocumentUploadValidationError(
            "The uploaded file could not be verified."
        )

    # -----------------------------------------------------
    # PDF VALIDATION
    # -----------------------------------------------------

    if extension == ".pdf":

        # A PDF file begins with the "%PDF-" signature.
        if not header.startswith(b"%PDF-"):
            raise DocumentUploadValidationError(
                "The uploaded file is not a valid PDF."
            )

        uploaded_file.seek(0)

        return uploaded_file

    # -----------------------------------------------------
    # IMAGE VALIDATION
    # -----------------------------------------------------

    expected_format = EXPECTED_IMAGE_FORMATS.get(
        extension
    )

    if not expected_format:
        raise DocumentUploadValidationError(
            "Unsupported file type. "
            "Please upload a PDF, JPEG, PNG, or WebP file."
        )

    try:
        uploaded_file.seek(0)

        image = Image.open(
            uploaded_file
        )

        # Verify the actual image contents rather than
        # trusting the filename extension.
        image.verify()

        detected_format = image.format

        uploaded_file.seek(0)

    except Exception:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass

        raise DocumentUploadValidationError(
            "The uploaded image could not be verified "
            "as a valid image."
        )

    # -----------------------------------------------------
    # EXTENSION / ACTUAL CONTENT MATCH
    # -----------------------------------------------------

    if detected_format != expected_format:
        raise DocumentUploadValidationError(
            "The file extension does not match the actual "
            "file type."
        )

    # Leave the upload positioned at the beginning for the
    # existing image-processing function.
    uploaded_file.seek(0)

    return uploaded_file

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
    Validate and prepare an uploaded document.

    Step 7 validation happens first.

    Existing Steps 4-6 image processing then handles:
        - JPEG/JPG compression
        - PNG conversion when beneficial
        - transparent PNG compositing
        - WebP compression
        - maximum 2000px image resizing

    PDFs are validated but otherwise passed through unchanged.

    The original browser filename is kept separately from
    the generated stored filename.
    """

    # =====================================================
    # STEP 7 - VALIDATE BEFORE PROCESSING
    # =====================================================
    #
    # This must happen before:
    #   - Pillow processing
    #   - compression
    #   - conversion
    #   - resizing
    #   - saving
    # =====================================================

    validate_document_upload(
        uploaded_file
    )

    # =====================================================
    # ORIGINAL BROWSER FILENAME
    # =====================================================

    original_name = (
        uploaded_file.name
        or "document"
    )

    extension = Path(
        original_name
    ).suffix.lower()

    # =====================================================
    # MEMBER IDENTIFIER
    # =====================================================

    member_uid = getattr(
        member,
        "member_uid",
        None,
    )

    if member_uid:
        member_identifier = sanitize_filename_part(
            member_uid,
            fallback=f"member-{member.pk}",
        )
    else:
        member_identifier = (
            f"member-{member.pk}"
        )

    # =====================================================
    # DOCUMENT NAME
    # =====================================================

    document_name = sanitize_filename_part(
        document_title,
        fallback="document",
    )

    # =====================================================
    # DATE
    # =====================================================

    upload_date = date.today().isoformat()

    # =====================================================
    # COLLISION-RESISTANT IDENTIFIER
    # =====================================================

    unique_suffix = uuid4().hex[:6]

    # =====================================================
    # GENERATED STORED FILENAME
    # =====================================================

    stored_filename = (
        f"{member_identifier}-"
        f"{document_name}-"
        f"{upload_date}-"
        f"{unique_suffix}"
        f"{extension}"
    )

    uploaded_file.name = stored_filename

    # =====================================================
    # EXISTING STEPS 4-6 PROCESSING
    # =====================================================
    #
    # Do not change compress_uploaded_image().
    #
    # It already contains the tested compression,
    # conversion and resizing behaviour.
    #
    # PDF is not an image extension and therefore passes
    # through unchanged.
    # =====================================================

    prepared_file = compress_uploaded_image(
        uploaded_file
    )

    # =====================================================
    # PRESERVE ORIGINAL BROWSER FILENAME
    # =====================================================

    prepared_file._original_filename = (
        original_name
    )

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
            # -------------------------------------------------
            # NORMALISE MODE FOR JPEG
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

                image = background

            elif image.mode not in {
                "RGB",
                "L",
            }:

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

# =========================================================
# STEP 8 - DOCUMENT THUMBNAIL GENERATION
# =========================================================

THUMBNAIL_MAX_DIMENSION = 300


def generate_document_thumbnail(document):
    """
    Generate a private thumbnail for an image MemberDocument.

    STEP 8 RULES
    ------------
    - JPEG/JPG, PNG and WebP receive thumbnails.
    - PDFs do not receive thumbnails.
    - The thumbnail is generated from the already processed
      document.file.
    - Maximum dimension is 300px.
    - Aspect ratio is preserved.
    - Images are never enlarged.
    - Thumbnail failure does not invalidate the document.

    Returns:
        True if a thumbnail was generated.
        False if no thumbnail was generated.
    """

    if not document:
        return False

    if not document.file:
        return False

    extension = Path(
        document.file.name
    ).suffix.lower()

    if extension not in {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
    }:
        return False

    try:
        with document.file.open("rb") as source_file:

            image = Image.open(source_file)

            image.load()

            image.thumbnail(
                (
                    THUMBNAIL_MAX_DIMENSION,
                    THUMBNAIL_MAX_DIMENSION,
                ),
                Image.Resampling.LANCZOS,
            )

            if image.mode not in {
                "RGB",
                "L",
            }:
                image = image.convert("RGB")

            output = BytesIO()

            image.save(
                output,
                format="JPEG",
                quality=82,
                optimize=True,
                progressive=True,
            )

            thumbnail_data = output.getvalue()

        if not thumbnail_data:
            return False

        original_name = Path(
            document.file.name
        )

        thumbnail_filename = (
            f"{original_name.stem}-thumb.jpg"
        )

        if document.thumbnail:
            try:
                document.thumbnail.delete(
                    save=False
                )
            except Exception:
                logger.exception(
                    "Failed to remove old thumbnail "
                    "for MemberDocument %s",
                    document.pk,
                )

        document.thumbnail.save(
            thumbnail_filename,
            ContentFile(thumbnail_data),
            save=False,
        )

        document.save(
            update_fields=["thumbnail"]
        )

        return True

    except Exception:
        logger.exception(
            "Thumbnail generation failed for "
            "MemberDocument %s",
            getattr(document, "pk", None),
        )

        return False