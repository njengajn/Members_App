from django.utils import timezone

from backend.members.models import (
    MembershipStatusHistory,
)


def retire_member(
    member,
    reason="Claim Settled",
    performed_by=None,
):
    """
    Retire member and record history.

    Retirement does not change joined_at.
    The original activation date remains part
    of the member's history.
    """

    if member.status == "retired":
        return member

    member.status = "retired"
    member.retirement_reason = reason
    member.retired_reason = reason
    member.retired_at = timezone.now()
    member.can_edit = False
    member.can_edit_expires_at = None
    member.is_portal_access_enabled = False

    member.save()

    member.dependants.update(
        status="retired"
    )

    MembershipStatusHistory.objects.create(
        member=member,
        action="retired",
        reason=reason,
        performed_by=performed_by,
    )

    return member


def reactivate_member(
    member,
    reason="Member Reactivated",
    performed_by=None,
):
    """
    Reactivate a retired member.

    Business rules
    --------------
    • Status becomes ACTIVE.
    • Existing UID is retained.
    • joined_at is reset to reactivation date.
    • Claim cooling-off starts again.
    • Dependants become active.
    • Portal access is enabled.
    """

    if member.status != "retired":
        return member

    member.status = "active"

    # New activation period starts now.
    member.joined_at = timezone.now()

    member.retired_reason = None
    member.retirement_reason = None
    member.retired_at = None

    member.can_edit = False
    member.can_edit_expires_at = None

    member.is_portal_access_enabled = True

    member.save()

    member.dependants.update(
        status="active"
    )

    MembershipStatusHistory.objects.create(
        member=member,
        action="reactivated",
        reason=reason,
        performed_by=performed_by,
    )

    return member