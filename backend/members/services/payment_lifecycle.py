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
    PaymentRequest,
    MemberPaymentStatus,
    Member,
    AuditLog,
)
from backend.members.services.member_status_service import (
    retire_member,
)

# ==========================================================
# MAIN LIFECYCLE ENGINE
# ==========================================================

# =========================================================
# PAYMENT LIFECYCLE ENGINE
# =========================================================

@transaction.atomic
def process_payment_lifecycle():
    """
    SINGLE SOURCE OF TRUTH

    RULES
    -------------------------------------------------

    1. Automatically closes overdue requests

    2. Retirement applies ONLY to:
        - subscription
        - claim

    3. Retirement occurs AFTER request closes

    4. Respect:
        - selected_members
        - viewable_by_all
        - single-member requests

    -------------------------------------------------
    """

    now = timezone.now()

    # =================================================
    # FETCH ELIGIBLE REQUESTS
    # =================================================

    requests = (
        PaymentRequest.objects
        .filter(
            due_date__lt=now,
            status__in=[
                PaymentRequest.STATUS_ACTIVE,
                PaymentRequest.STATUS_CLOSED,
            ]
        )
        .select_related("member")
        .prefetch_related(
            "selected_members",
            "paid_members"
        )
    )

    # =================================================
    # PROCESS REQUESTS
    # =================================================

    for pr in requests:

        # -------------------------------------------------
        # AUTO CLOSE ACTIVE OVERDUE REQUESTS
        # -------------------------------------------------
        # All overdue request types are closed automatically.
        # This is separate from the retirement rule below.

        if pr.status == PaymentRequest.STATUS_ACTIVE:

            pr.status = PaymentRequest.STATUS_CLOSED

            pr.save(update_fields=["status"])

        # -------------------------------------------------
        # ONLY THESE TYPES TRIGGER RETIREMENT
        # -------------------------------------------------
        # Membership requests do NOT retire active members.
        # Only unpaid subscription and claim requests can
        # trigger automatic retirement.

        if pr.request_type not in [
            "subscription",
            "claim",
        ]:
            continue

        # =================================================
        # DETERMINE TARGET MEMBERS
        # =================================================

        target_members = Member.objects.none()

        # -------------------------------------------------
        # SELECTED MEMBERS
        # -------------------------------------------------

        if pr.selected_members.exists():

            target_members = pr.selected_members.filter(
                status=Member.STATUS_ACTIVE
            )

        # -------------------------------------------------
        # GLOBAL REQUEST
        # -------------------------------------------------

        elif pr.viewable_by_all:

            organization = None

            # ---------------------------------------------
            # CLAIM ORGANIZATION
            # ---------------------------------------------

            if getattr(pr, "claim", None):

                if pr.claim.member:

                    organization = (
                        pr.claim.member.organization
                    )

            # ---------------------------------------------
            # REQUEST OWNER ORGANIZATION
            # ---------------------------------------------

            elif pr.member:

                organization = pr.member.organization

            if not organization:
                continue

            target_members = Member.objects.filter(
                organization=organization,
                status=Member.STATUS_ACTIVE
            )

        # -------------------------------------------------
        # SINGLE MEMBER
        # -------------------------------------------------

        elif pr.member:

            target_members = Member.objects.filter(
                id=pr.member.id,
                status=Member.STATUS_ACTIVE
            )

        # =================================================
        # TRUE PAYMENT CHECK
        # =================================================

        paid_member_ids = set(
            pr.paid_members.values_list(
                "id",
                flat=True
            )
        )

        # =================================================
        # PROCESS TARGET MEMBERS
        # =================================================

        for member in target_members:

            # ---------------------------------------------
            # SKIP RETIRED
            # ---------------------------------------------
            # Normally already excluded by the queryset,
            # but retain this guard for safety.

            if member.status == Member.STATUS_RETIRED:
                continue

            # ---------------------------------------------
            # TRUE PAYMENT STATUS
            # ---------------------------------------------
            # A member who has actually paid this request
            # must never be retired by this lifecycle run.

            if member.id in paid_member_ids:
                continue

            # =================================================
            # RETIRE UNPAID MEMBER
            # =================================================
            # Use the central retirement service so that all
            # retirement rules and related records are applied
            # consistently.

            retire_member(
                member,
                reason=f"non_payment_{pr.request_type}",
                performed_by=None,
            )

            # ---------------------------------------------
            # AUDIT LOG
            # ---------------------------------------------

            AuditLog.objects.create(
                action="member_retired_non_payment",
                target_member=member,
                message=(
                    f"Auto retired due to unpaid "
                    f"{pr.request_type} request #{pr.id}"
                )
            )


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