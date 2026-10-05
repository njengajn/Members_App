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

# =========================================================
# PAYMENT LIFECYCLE ENGINE
# =========================================================

@transaction.atomic
def process_payment_lifecycle(
    request_id=None,
    performed_by=None,
):
    """
    SINGLE SOURCE OF TRUTH FOR PAYMENT REQUEST LIFECYCLE

    MODES
    ---------------------------------------------------------
    1. request_id is None:
         Process ALL overdue active requests.

    2. request_id is supplied:
         Process ONLY that payment request.

    BUSINESS RULES
    ---------------------------------------------------------
    1. Overdue active requests are closed.

    2. Explicit/manual closing is request-specific.

    3. A member-causer claim:
         - retires the member
         - retires all of that member's dependants

    4. A dependant-causer claim:
         - retires the causer dependant only

    5. Membership/subscription non-payment continues to use
       the existing unpaid-member retirement rules.

    6. Fully-paid requests do NOT need this lifecycle engine
       merely because they have reached their required amount.

    7. This function must never process unrelated requests
       when a specific request_id is supplied.
    """

    now = timezone.now()

    # =====================================================
    # DETERMINE WHICH REQUESTS TO PROCESS
    # =====================================================

    if request_id is not None:

        # -------------------------------------------------
        # REQUEST-SPECIFIC MODE
        # -------------------------------------------------
        # Only ONE PaymentRequest can be processed.
        # -------------------------------------------------

        requests = (
            PaymentRequest.objects
            .filter(id=request_id)
            .select_related(
                "member",
                "claim",
            )
            .prefetch_related(
                "selected_members",
                "paid_members",
            )
        )

    else:

        # -------------------------------------------------
        # GLOBAL OVERDUE MODE
        # -------------------------------------------------
        # Used by scheduled/automatic lifecycle processing.
        # -------------------------------------------------

        requests = (
            PaymentRequest.objects
            .filter(
                due_date__lt=now,
                status__in=[
                    PaymentRequest.STATUS_ACTIVE,
                    PaymentRequest.STATUS_CLOSED,
                ]
            )
            .select_related(
                "member",
                "claim",
            )
            .prefetch_related(
                "selected_members",
                "paid_members",
            )
        )

    # =====================================================
    # PROCESS REQUESTS
    # =====================================================

    for pr in requests:

        # =================================================
        # REQUEST-SPECIFIC MODE
        # =================================================
        #
        # An explicitly supplied request_id means this
        # request must be processed even if it is not overdue.
        #
        # However, a request already closed needs no further
        # closing operation.
        # =================================================

        if request_id is not None:

            if pr.status == PaymentRequest.STATUS_ARCHIVED:
                continue

            if pr.status == PaymentRequest.STATUS_ACTIVE:

                pr.status = PaymentRequest.STATUS_CLOSED

                # -----------------------------------------
                # Record who explicitly closed the request.
                #
                # Automatic lifecycle calls have
                # performed_by=None and therefore do not
                # falsely attribute the close to an admin.
                # -----------------------------------------

                if performed_by is not None:

                    pr.closed_by = performed_by
                    pr.closed_at = now

                    pr.save(
                        update_fields=[
                            "status",
                            "closed_by",
                            "closed_at",
                            "updated_at",
                        ]
                    )

                else:

                    pr.save(
                        update_fields=[
                            "status",
                            "updated_at",
                        ]
                    )

        # =================================================
        # GLOBAL MODE
        # =================================================

        else:

            # -------------------------------------------------
            # Only active overdue requests are automatically
            # closed.
            #
            # Already-closed requests remain closed but still
            # need any applicable lifecycle retirement rules
            # processed.
            # -------------------------------------------------

            if pr.status == PaymentRequest.STATUS_ACTIVE:

                pr.status = PaymentRequest.STATUS_CLOSED

                pr.save(
                    update_fields=[
                        "status",
                        "updated_at",
                    ]
                )

        # =================================================
        # CLAIM RETIREMENT
        # =================================================
        #
        # Claims have their own business rule.
        #
        # IMPORTANT:
        # Do NOT use the generic payment-member retirement
        # logic for claims.
        # =================================================

        claim = getattr(pr, "claim", None)

        if claim:

            # -------------------------------------------------
            # MEMBER-CAUSER CLAIM
            # -------------------------------------------------
            #
            # Retire the member and ALL dependants.
            #
            # Member.retire() already contains the project
            # rule that synchronises dependant retirement.
            # -------------------------------------------------

            if claim.causer_dependant is None:

                member = claim.member

                if member and member.status != Member.STATUS_RETIRED:

                    member.retire(
                        reason=f"Claim settled (Claim #{claim.id})",
                        payment_request=pr,
                        admin_user=performed_by,
                    )

            # -------------------------------------------------
            # DEPENDANT-CAUSER CLAIM
            # -------------------------------------------------
            #
            # Retire ONLY the dependant who was the causer.
            # Do not retire the parent member or siblings.
            # -------------------------------------------------

            else:

                dependant = claim.causer_dependant

                if dependant.status != "retired":

                    dependant.status = "retired"

                    # Keep the retirement reason explicit.
                    if hasattr(
                        dependant,
                        "retirement_reason"
                    ):
                        dependant.retirement_reason = (
                            f"Claim settled (Claim #{claim.id})"
                        )

                    if hasattr(
                        dependant,
                        "retired_reason"
                    ):
                        dependant.retired_reason = (
                            f"Claim settled (Claim #{claim.id})"
                        )

                    if hasattr(
                        dependant,
                        "retired_at"
                    ):
                        dependant.retired_at = now

                    dependant.save()

            # -------------------------------------------------
            # A claim has now been handled by the claim-specific
            # retirement rule.
            #
            # Do NOT also run the generic unpaid-member logic.
            # -------------------------------------------------

            continue

        # =================================================
        # ONLY MEMBERSHIP/SUBSCRIPTION USE THE GENERIC
        # NON-PAYMENT RETIREMENT RULE
        # =================================================

        if pr.request_type not in [
            "membership",
            "subscription",
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

            if pr.member:

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

            # -------------------------------------------------
            # Skip already retired members.
            # -------------------------------------------------

            if member.status == Member.STATUS_RETIRED:
                continue

            # -------------------------------------------------
            # Paid members must never be retired for
            # non-payment.
            # -------------------------------------------------

            if member.id in paid_member_ids:
                continue

            # -------------------------------------------------
            # RETIRE UNPAID MEMBER
            # -------------------------------------------------

            member.retire(
                reason=f"non_payment_{pr.request_type}",
                payment_request=pr,
                admin_user=performed_by,
            )

            # -------------------------------------------------
            # AUDIT
            # -------------------------------------------------

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