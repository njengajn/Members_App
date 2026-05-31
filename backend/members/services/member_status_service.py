from backend.members.models import MembershipStatusHistory


def retire_member(
    member,
    reason="Claim Settled",
    performed_by=None,
):
    """
    Retire member and record history.
    """

    member.status = "retired"
    member.retirement_reason = reason
    member.save()

    MembershipStatusHistory.objects.create(
        member=member,
        action="retired",
        reason=reason,
        performed_by=performed_by,
    )

    member.dependants.update(
        status="retired"
    )

    return member


def reactivate_member(
    member,
    reason="Member Reactivated",
    performed_by=None,
):
    """
    Reactivate member and record history.
    """

    member.status = "active"
    member.save()

    MembershipStatusHistory.objects.create(
        member=member,
        action="reactivated",
        reason=reason,
        performed_by=performed_by,
    )