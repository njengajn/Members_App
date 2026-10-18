"""
Payment lifecycle engine.

✔ Close overdue requests
✔ Retire unpaid members (CLAIM only)
✔ Uses model methods (single source of truth)
✔ Safe (no validation crash)
"""

from django.utils import timezone
from django.db import transaction
from backend.members.models import (
    Claim,
    ClaimSettlement,
    Dependant,
    Payment,
    PaymentRequest,
    MemberPaymentStatus,
    Member,
    AuditLog,
)
from backend.members.services.member_status_service import (
    retire_member,
)

# =========================================================
# PAYMENT LIFECYCLE ENGINE
# =========================================================

@transaction.atomic
def process_payment_lifecycle(
    request_id=None,
    performed_by=None,
):
    """
    Close eligible payment requests only.

    BUSINESS RULES
    ---------------------------------------------------------
    1. When request_id is supplied, process only that request.
    2. Pending, non-rejected payment approvals block closure.
    3. Record the administrator who closes the request.
    4. Closing a request must never trigger retirement.
    5. Reconciliation and retirement are separate operations.

    Returns a list of dictionaries containing request_id and
    status, as expected by update_payment_request_status().
    """

    now = timezone.now()
    results = []

    # An explicit request ID must never cause unrelated requests
    # to be processed.
    if request_id is not None:
        requests = (
            PaymentRequest.objects
            .select_for_update()
            .filter(id=request_id)
            .select_related("member", "claim")
        )
    else:
        # Preserve the existing bulk behaviour for callers that
        # intentionally process overdue active requests.
        requests = (
            PaymentRequest.objects
            .select_for_update()
            .filter(
                due_date__lt=now,
                status=PaymentRequest.STATUS_ACTIVE,
            )
            .select_related("member", "claim")
        )

    for payment_request in requests:
        # Do not change requests that are already closed or archived.
        if payment_request.status != PaymentRequest.STATUS_ACTIVE:
            results.append({
                "request_id": payment_request.id,
                "status": (
                    "archived"
                    if payment_request.status
                    == PaymentRequest.STATUS_ARCHIVED
                    else "not_active"
                ),
            })
            continue

        # Closure is blocked until all non-rejected payment
        # approvals for this request have been resolved.
        if get_pending_payment_approvals(payment_request).exists():
            results.append({
                "request_id": payment_request.id,
                "status": "pending_approvals",
            })
            continue

        payment_request.status = PaymentRequest.STATUS_CLOSED

        update_fields = ["status", "updated_at"]

        if performed_by is not None:
            payment_request.closed_by = performed_by
            payment_request.closed_at = now
            update_fields.extend(["closed_by", "closed_at"])

        payment_request.save(update_fields=update_fields)

        results.append({
            "request_id": payment_request.id,
            "status": "closed",
        })

    return results

@transaction.atomic
def process_reconciled_payment_request(
    request_id,
    performed_by=None,
):
    """
    Apply retirement rules to one closed payment request.

    CLAIM REQUESTS
    - Require an approved settlement.
    - The settlement preparer cannot approve their own settlement.
    - Member-causer: retire the member and all dependants through
      Member.retire().
    - Dependant-causer: retire only the identified dependant.

    SUBSCRIPTION REQUESTS
    - Require closure, reconciliation, an overdue due date,
      an active targeted member, and explicit unpaid status.
    - Never retire a member with evidence of payment.

    MEMBERSHIP AND OTHER REQUESTS
    - Never trigger non-payment retirement.

    Processing is request-specific and idempotent.
    Manual administrative retirement remains separate.
    """
    from django.utils import timezone

    payment_request = (
        PaymentRequest.objects
        .select_for_update()
        .select_related("member", "claim")
        .get(pk=request_id)
    )

    # A request must be closed before any retirement processing.
    if payment_request.status != PaymentRequest.STATUS_CLOSED:
        return False

    # Pending, non-rejected payment approvals block processing.
    if get_pending_payment_approvals(payment_request).exists():
        return False

    claim = getattr(payment_request, "claim", None)

    # ==========================================================
    # CLAIM RETIREMENT
    # ==========================================================
    if payment_request.request_type == "claim":
        if claim is None:
            return False

        settlement = getattr(claim, "settlement", None)

        if settlement is None or not settlement.is_approved:
            return False

        # Enforce separation of duties even if this service is
        # called outside the normal settlement-approval view.
        if (
            settlement.prepared_by_id is not None
            and settlement.prepared_by_id
            == settlement.approved_by_id
        ):
            return False

        # ------------------------------------------------------
        # MEMBER-CAUSER
        # ------------------------------------------------------
        if claim.cause_type == Claim.CLAIM_CAUSER_MEMBER:
            member = claim.member

            if member is None:
                return False

            if member.status != Member.STATUS_RETIRED:
                member.retire(
                    reason=f"Claim settled (Claim #{claim.id})",
                    payment_request=payment_request,
                    admin_user=performed_by,
                )

            return True

        # ------------------------------------------------------
        # DEPENDANT-CAUSER
        # ------------------------------------------------------
        if claim.cause_type == Claim.CLAIM_CAUSER_DEPENDANT:
            dependant = claim.causer_dependant

            # Never substitute the parent member if the dependant
            # cannot be identified.
            if dependant is None:
                return False

            if dependant.status != "retired":
                dependant.status = "retired"
                dependant.save(update_fields=["status"])

            return True

        # Unknown cause types must never trigger retirement.
        return False

    # ==========================================================
    # NON-CLAIM RETIREMENT
    # ==========================================================
    # Only subscriptions can trigger automatic non-payment
    # retirement. Membership and Other requests are excluded.
    if payment_request.request_type != "subscription":
        return True

    # Subscription requests must be reconciled first.
    if not payment_request.is_reconciled:
        return False

    # Only overdue subscriptions can trigger retirement.
    if (
        payment_request.due_date is None
        or payment_request.due_date >= timezone.now()
    ):
        return True

    # ----------------------------------------------------------
    # DETERMINE TARGET MEMBERS
    # ----------------------------------------------------------
    if payment_request.viewable_by_all:
        target_members = Member.objects.filter(
            status=Member.STATUS_ACTIVE,
        )
    elif payment_request.selected_members.exists():
        target_members = payment_request.selected_members.filter(
            status=Member.STATUS_ACTIVE,
        )
    elif payment_request.member_id:
        target_members = Member.objects.filter(
            pk=payment_request.member_id,
            status=Member.STATUS_ACTIVE,
        )
    else:
        # No identifiable target: do not infer one.
        return True

    # ----------------------------------------------------------
    # COLLECT ALL EVIDENCE THAT A MEMBER HAS PAID
    # ----------------------------------------------------------
    paid_ids = set(
        payment_request.paid_members.values_list("pk", flat=True)
    )

    paid_ids.update(
        Payment.objects.filter(
            payment_request=payment_request,
            status=Payment.STATUS_COMPLETED,
        ).values_list("member_id", flat=True)
    )

    paid_ids.update(
        MemberPaymentStatus.objects.filter(
            payment_request=payment_request,
            status=MemberPaymentStatus.STATUS_PAID,
        ).values_list("member_id", flat=True)
    )

    # ----------------------------------------------------------
    # RETIRE ONLY EXPLICITLY UNPAID ACTIVE TARGETS
    # ----------------------------------------------------------
    unpaid_ids = set(
        MemberPaymentStatus.objects.filter(
            payment_request=payment_request,
            status=MemberPaymentStatus.STATUS_UNPAID,
        ).values_list("member_id", flat=True)
    )

    eligible_ids = set(
        target_members.values_list("pk", flat=True)
    )

    retire_ids = eligible_ids & unpaid_ids - paid_ids

    for member in target_members.filter(pk__in=retire_ids):
        # Recheck current status before applying retirement.
        member.refresh_from_db(fields=["status"])

        if member.status != Member.STATUS_ACTIVE:
            continue

        member.retire(
            reason="non_payment_subscription",
            payment_request=payment_request,
            admin_user=performed_by,
        )

        AuditLog.objects.create(
            action="member_retired_non_payment",
            target_member=member,
            message=(
                "Member retired for non-payment of overdue "
                f"subscription request #{payment_request.pk}."
            ),
            admin=performed_by,
        )

    return True

# ==========================================================
# RISK MEMBERS
# ==========================================================
def get_risk_members():
    """
    Members at risk (unpaid and nearing deadline)
    """

    now = timezone.now()
    soon = now + timezone.timedelta(hours=24)

    return MemberPaymentStatus.objects.filter(
        status=MemberPaymentStatus.STATUS_UNPAID,
        payment_request__due_date__lte=soon,
        payment_request__status=PaymentRequest.STATUS_ACTIVE,
    ).select_related("member", "payment_request")


def get_pending_payment_approvals(payment_request):
    """
    Return payments belonging to this request that have not
    yet been approved.

    Rejected payments should not remain blocked if the
    project records their rejection in a separate status field.
    """
    return Payment.objects.filter(
        payment_request=payment_request,
        approved_at__isnull=True,
    ).exclude(
        status="rejected"
    )