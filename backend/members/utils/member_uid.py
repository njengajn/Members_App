import random
"""
Utility: Generate Member UID safely
"""

from django.conf import settings


def generate_member_uid(organization=None):
    """
    Lazy import avoids AppRegistryNotReady error
    """

    # ✅ IMPORT INSIDE FUNCTION (REQUIRED)
    from backend.members.models import Member

    # -----------------------------
    # PREFIX
    # -----------------------------
    if organization and organization.code_prefix:
        prefix = organization.code_prefix
    else:
        prefix = settings.DEFAULT_MEMBER_PREFIX

    start_number = getattr(settings, "DEFAULT_MEMBER_START_NUMBER", 1000)

    last_member = (
        Member.objects
        .filter(member_uid__startswith=prefix)
        .order_by("-member_uid")
        .first()
    )

    if last_member and last_member.member_uid:
        try:
            last_number = int(last_member.member_uid.replace(prefix, ""))
        except Exception:
            last_number = start_number
    else:
        last_number = start_number

    return f"{prefix}{last_number + 1}"
