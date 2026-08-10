import re
from datetime import date
from pathlib import Path
from uuid import uuid4


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

    return uploaded_file