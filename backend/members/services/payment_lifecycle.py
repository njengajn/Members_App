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

# ==========================================================
# MAIN LIFECYCLE ENGINE
# ==========================================================
@transaction.atomic
def process_payment_lifecycleStopped03_05_25():
    """
    SINGLE SOURCE OF TRUTH

    RULES:
    ---------------------------------------
    1. Close request if overdue

    2. ONLY claim + subscription:
        unpaid members → RETIRE

    3. Respect:
        - viewable_by_all
        - selected_members

    4. Use ONE source of truth:
        pr.member_payment_status(member)
    ---------------------------------------
    """

    now = timezone.now()

    overdue_requests = PaymentRequest.objects.filter(
        status=PaymentRequest.STATUS_ACTIVE,
        due_date__lt=now
    ).select_related("member").prefetch_related("selected_members", "paid_members")

    for pr in overdue_requests:

        # -----------------------------------
        # CLOSE REQUEST
        # -----------------------------------
        PaymentRequest.objects.filter(id=pr.id).update(
            status=PaymentRequest.STATUS_CLOSED
        )

        # -----------------------------------
        # ONLY CLAIM + SUBSCRIPTION
        # -----------------------------------
        if pr.request_type not in ["claim", "subscription"]:
            continue

        # -----------------------------------
        # DETERMINE TARGET MEMBERS
        # -----------------------------------          
        if pr.viewable_by_all:
            if not pr.member or not pr.member.organization:
                # Skip broken data instead of crashing
                continue

            target_members = Member.objects.filter(
                organization=pr.member.organization,
                status=Member.STATUS_ACTIVE
            )

        # -----------------------------------
        # PROCESS EACH MEMBER
        # -----------------------------------
        for member in target_members:

            # Skip already retired
            if member.status == Member.STATUS_RETIRED:
                continue

            # 🔥 SINGLE SOURCE OF TRUTH
            payment_status = pr.member_payment_status(member)

            if payment_status == "paid":
                continue

            # -----------------------------------
            # CHECK OVERDUE PER MEMBER
            # -----------------------------------
            if not pr.is_member_overdue(member):
                continue

            # -----------------------------------
            # RETIRE MEMBER
            # -----------------------------------
            member.retire(
                reason=f"non_payment_{pr.request_type}",
                admin_user=None
            )

            # -----------------------------------
            # AUDIT
            # -----------------------------------
            AuditLog.objects.create(
                action="member_retired_non_payment",
                target_member=member,
                message=f"Auto retired due to unpaid {pr.request_type} #{pr.id}"
            )


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
        - membership
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

        if pr.status == PaymentRequest.STATUS_ACTIVE:

            pr.status = PaymentRequest.STATUS_CLOSED

            pr.save(update_fields=["status"])

        # -------------------------------------------------
        # ONLY THESE TYPES TRIGGER RETIREMENT
        # -------------------------------------------------

        if pr.request_type not in [
            "membership",
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

            if member.status == Member.STATUS_RETIRED:
                continue

            # ---------------------------------------------
            # TRUE PAYMENT STATUS
            # ---------------------------------------------

            if member.id in paid_member_ids:
                continue

            # =================================================
            # RETIRE UNPAID MEMBER
            # =================================================

            member.retire(
                reason=f"non_payment_{pr.request_type}",
                admin_user=None
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

@transaction.atomic
def process_payment_lifecycleOnHold10_05_26():
    """
    SINGLE SOURCE OF TRUTH

    RULES
    -------------------------------------------------

    1. Automatically closes overdue requests

    2. Retirement applies ONLY to:
        - membership
        - subscription
        - claim

    3. Retirement occurs AFTER request closes

    4. Respect:
        - selected_members
        - viewable_by_all
        - single-member requests

    5. Uses ONE source of truth:
        pr.member_payment_status(member)

    -------------------------------------------------
    """

    now = timezone.now()

    # =================================================
    # FETCH REQUESTS REQUIRING LIFECYCLE PROCESSING
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
        # AUTO CLOSE OVERDUE ACTIVE REQUESTS
        # -------------------------------------------------
        if pr.status == PaymentRequest.STATUS_ACTIVE:
            pr.status = PaymentRequest.STATUS_CLOSED
            pr.save(update_fields=["status"])
        # -------------------------------------------------
        # RETIREMENT ONLY FOR THESE TYPES
        # -------------------------------------------------
        if pr.request_type not in [
            "membership",
            "subscription",
            "claim",
        ]:
            continue

        # =================================================
        # DETERMINE TARGET MEMBERS
        # =================================================

        target_members = Member.objects.none()

        # -------------------------------------------------
        # CASE 1:
        # SELECTED MEMBERS
        # -------------------------------------------------

        if pr.selected_members.exists():

            target_members = pr.selected_members.filter(
                status=Member.STATUS_ACTIVE
            )

        # -------------------------------------------------
        # CASE 2:
        # GLOBAL REQUEST
        # -------------------------------------------------

        elif pr.viewable_by_all:

            # IMPORTANT:
            # DO NOT RELY ON pr.member
            # IT MAY BE NULL
            # -------------------------------------------------

            organization = None

            # ---------------------------------------------
            # FIRST TRY CLAIM ORGANIZATION
            # ---------------------------------------------

            if getattr(pr, "claim", None):

                if pr.claim.member:

                    organization = (
                        pr.claim.member.organization
                    )

            # ---------------------------------------------
            # FALLBACK TO CREATOR MEMBER
            # ---------------------------------------------

            elif pr.member:

                organization = pr.member.organization

            # ---------------------------------------------
            # STILL NO ORGANIZATION
            # ---------------------------------------------

            if not organization:
                continue

            target_members = Member.objects.filter(
                organization=organization,
                status=Member.STATUS_ACTIVE
            )

        # -------------------------------------------------
        # CASE 3:
        # SINGLE MEMBER
        # -------------------------------------------------

        elif pr.member:

            if pr.member.status == Member.STATUS_ACTIVE:

                target_members = Member.objects.filter(
                    id=pr.member.id
                )

        # =================================================
        # PROCESS TARGET MEMBERS
        # =================================================

        for member in target_members:

            # ---------------------------------------------
            # SKIP RETIRED MEMBERS
            # ---------------------------------------------

            if member.status == Member.STATUS_RETIRED:
                continue

            # ---------------------------------------------
            # SINGLE SOURCE OF TRUTH
            # ---------------------------------------------

            payment_status = pr.member_payment_status(
                member
            )

            # ---------------------------------------------
            # MEMBER PAID
            # ---------------------------------------------

            if payment_status == "paid":
                continue

            # ---------------------------------------------
            # MEMBER NOT YET OVERDUE
            # ---------------------------------------------

            if not pr.is_member_overdue(member):
                continue

            # ---------------------------------------------
            # RETIRE MEMBER
            # ---------------------------------------------

            member.retire(
                reason=f"non_payment_{pr.request_type}",
                admin_user=None
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

@transaction.atomic
def process_payment_lifecycleONHooold():
    """
    SINGLE SOURCE OF TRUTH

    RULES
    -------------------------------------------------

    1. Automatically closes overdue requests

    2. Retirement applies ONLY to:
        - membership
        - subscription
        - claim

    3. Retirement occurs AFTER request closes

    4. Respect:
        - selected_members
        - viewable_by_all
        - single-member requests

    5. Uses ONE source of truth:
        pr.member_payment_status(member)

    -------------------------------------------------
    """

    now = timezone.now()

    # =================================================
    # FETCH REQUESTS REQUIRING LIFECYCLE PROCESSING
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

    for pr in requests:

        # =================================================
        # AUTO CLOSE OVERDUE ACTIVE REQUESTS
        # =================================================

        if pr.status == PaymentRequest.STATUS_ACTIVE:

            pr.status = PaymentRequest.STATUS_CLOSED
            pr.save(update_fields=["status"])

        # =================================================
        # RETIREMENT RULES APPLY ONLY TO THESE TYPES
        # =================================================

        if pr.request_type not in [
            "membership",
            "subscription",
            "claim",
        ]:
            continue

        # =================================================
        # DETERMINE TARGET MEMBERS
        # =================================================

        target_members = []

        # ---------------------------------------------
        # SELECTED MEMBERS
        # ---------------------------------------------
        if pr.selected_members.exists():

            target_members = pr.selected_members.filter(
                status=Member.STATUS_ACTIVE
            )

        # ---------------------------------------------
        # GLOBAL REQUEST
        # ---------------------------------------------
        elif pr.viewable_by_all:

            if not pr.member or not pr.member.organization:
                continue

            target_members = Member.objects.filter(
                organization=pr.member.organization,
                status=Member.STATUS_ACTIVE
            )

        # ---------------------------------------------
        # SINGLE MEMBER
        # ---------------------------------------------
        elif pr.member:

            if pr.member.status == Member.STATUS_ACTIVE:
                target_members = [pr.member]

        # =================================================
        # PROCESS MEMBERS
        # =================================================

        for member in target_members:

            # ---------------------------------------------
            # SKIP ALREADY RETIRED
            # ---------------------------------------------
            if member.status == Member.STATUS_RETIRED:
                continue

            # ---------------------------------------------
            # SINGLE SOURCE OF TRUTH
            # ---------------------------------------------
            payment_status = pr.member_payment_status(member)

            if payment_status == "paid":
                continue

            # ---------------------------------------------
            # MEMBER-LEVEL OVERDUE CHECK
            # ---------------------------------------------
            if not pr.is_member_overdue(member):
                continue

            # ---------------------------------------------
            # RETIRE MEMBER
            # ---------------------------------------------
            member.retire(
                reason=f"non_payment_{pr.request_type}",
                admin_user=None
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