from django.utils import timezone

from django.utils import timezone

from backend.members.models import (
    MembershipStatusHistory,
    Dependant,
    Member,
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

    # All dependants follow the member into retirement.
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
    • Eligible dependants become active.
    • A deceased parent remains RETIRED.
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

    # ------------------------------------------------------
    # DEPENDANT ACTIVATION SAFEGUARD
    # ------------------------------------------------------
    # Deceased parents must never become active merely because
    # their member is being reactivated.
    #
    # All other dependants follow the member's active status.
    # A deceased parent remains retired.
    # ------------------------------------------------------

    member.dependants.exclude(
        relationship="PARENT",
        parent_status="DECEASED",
    ).update(
        status="active"
    )

    member.dependants.filter(
        relationship="PARENT",
        parent_status="DECEASED",
    ).update(
        status="retired"
    )

    MembershipStatusHistory.objects.create(
        member=member,
        action="reactivated",
        reason=reason,
        performed_by=performed_by,
    )

    return member


def is_protected_parent(dependant):
    """
    Return True when a parent dependant is permanently
    prevented from becoming ACTIVE.

    Protected parent states:
        • DECEASED
        • UNKNOWN
    """

    return (
        dependant.relationship == Dependant.TYPE_PARENT
        and dependant.parent_status in {
            Dependant.PARENT_DECEASED,
            Dependant.PARENT_UNKNOWN,
        }
    )


def activate_eligible_dependants(dependants):
    """
    Activate eligible dependants while explicitly preventing
    DECEASED and UNKNOWN parents from becoming ACTIVE.

    QuerySet.update() is used here deliberately for the bulk
    operation, so the protected rows must be excluded explicitly.
    """

    protected = dependants.filter(
        relationship=Dependant.TYPE_PARENT,
        parent_status__in=[
            Dependant.PARENT_DECEASED,
            Dependant.PARENT_UNKNOWN,
        ],
    )

    eligible = dependants.exclude(
        pk__in=protected.values("pk")
    )

    eligible.update(
        status=Dependant.STATUS_ACTIVE
    )

    # Even if bad historical data exists, a lifecycle activation
    # must never leave a protected parent ACTIVE.
    protected.update(
        status=Dependant.STATUS_RETIRED
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

    if member.status == Member.STATUS_RETIRED:
        return member

    member.status = Member.STATUS_RETIRED
    member.retirement_reason = reason
    member.retired_reason = reason
    member.retired_at = timezone.now()
    member.can_edit = False
    member.can_edit_expires_at = None
    member.is_portal_access_enabled = False

    member.save()

    # All dependants follow the member into retirement.
    member.dependants.update(
        status=Dependant.STATUS_RETIRED
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
    • Eligible dependants become active.
    • Deceased parents remain RETIRED.
    • Unknown parents remain RETIRED.
    • Unknown parents can never become ACTIVE.
    • Portal access is enabled.
    """

    if member.status != Member.STATUS_RETIRED:
        return member

    member.status = Member.STATUS_ACTIVE

    # New activation period starts now.
    member.joined_at = timezone.now()

    member.retired_reason = None
    member.retirement_reason = None
    member.retired_at = None

    member.can_edit = False
    member.can_edit_expires_at = None

    member.is_portal_access_enabled = True

    member.save()

    # ------------------------------------------------------
    # DEPENDANT ACTIVATION SAFEGUARD
    # ------------------------------------------------------
    #
    # DECEASED and UNKNOWN parents are permanently protected
    # from activation.
    #
    # All other dependants follow the member's active status.
    # ------------------------------------------------------

    activate_eligible_dependants(
        member.dependants.all()
    )

    MembershipStatusHistory.objects.create(
        member=member,
        action="reactivated",
        reason=reason,
        performed_by=performed_by,
    )

    return member