from urllib import request

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Q
from backend.members.models import (
    PaymentRequest,
    Payment,
    Claim,
    Member,
    AuditLog
)
from django.shortcuts import get_object_or_404
from decimal import Decimal, InvalidOperation
from django.utils.timezone import now

"""
CENTRAL PAYMENT SERVICE LAYER

This file is the SINGLE SOURCE OF TRUTH for:
• Payment request creation
• Payment request visibility
• Claim → payment linking
• Duplicate protection
• Compliance logic

ALL views must use this.
"""

# ==========================================================
# GET PAYMENT REQUESTS FOR MEMBER
# ==========================================================
def get_member_payment_requests(member):
    """
    Returns:
    • member-specific requests
    • global requests (member=None)
    """

    return (
        PaymentRequest.objects
        .filter(status="active")
        .filter(
            Q(member=member) | Q(member__isnull=True)
        )
        .order_by("-id")
    )


# ==========================================================
# RECORD PAYMENT (USED BY BOTH STRIPE + MANUAL)
# ==========================================================

from backend.members.models import Payment

def record_payment(member, payment_request, method="manual"):
    """
    Centralized payment creation.

    ✔ DOES NOT close request globally
    ✔ ONLY marks this member as paid
    ✔ prevents duplicates
    ✔ preserves original request type
    ✔ supports treasury reporting
    ✔ supports compliance reporting
    """

    # ---------------------------------------
    # PREVENT DUPLICATE COMPLETED PAYMENT
    # ---------------------------------------

    existing = Payment.objects.filter(
        member=member,
        payment_request=payment_request,
        status=Payment.STATUS_COMPLETED
    ).first()

    if existing:
        raise Exception(
            "Payment already exists for this request."
        )

    # ---------------------------------------
    # IMPORTANT:
    # Preserve originating request type
    #
    # Examples:
    # membership -> membership
    # subscription -> subscription
    # claim -> claim
    # other -> other
    # ---------------------------------------

    payment_type = (
        payment_request.request_type
    )

    # ---------------------------------------
    # CREATE PAYMENT
    # ---------------------------------------

    payment = Payment.objects.create(

        member=member,

        payment_request=payment_request,

        amount=payment_request.amount or 0,

        payment_type=payment_type,

        payment_method=method,

        status=Payment.STATUS_COMPLETED,

        external_payment_id=(
            f"{method}-"
            f"{payment_request.id}-"
            f"{member.id}"
        )
    )

    # ---------------------------------------
    # IMPORTANT:
    # ONLY MARK THIS MEMBER AS PAID
    # ---------------------------------------

    payment_request.paid_members.add(member)

    # ---------------------------------------
    # IMPORTANT:
    # DO NOT CLOSE REQUEST GLOBALLY
    #
    # Other members may still need to pay.
    # ---------------------------------------

    # ❌ DO NOT DO THIS:
    #
    # payment_request.status = "closed"
    # payment_request.save()

    return payment

# ==========================================================
# COMPLIANCE CALCULATION
# ==========================================================
def get_payment_compliance(payment_request):
    """
    Returns:
    • paid members
    • unpaid members
    • compliance %
    """

    all_members = Member.objects.filter(status="active")

    paid_members = Member.objects.filter(
        payments__payment_request=payment_request
    ).distinct()

    unpaid_members = all_members.exclude(id__in=paid_members)

    total = all_members.count()
    paid = paid_members.count()

    compliance = (paid / total * 100) if total > 0 else 0

    return {
        "paid_members": paid_members,
        "unpaid_members": unpaid_members,
        "compliance": round(compliance, 2),
    }


@transaction.atomic
def approve_payment(payment_id, approved_by=None):
    """
    SERVICE: Approve a payment

    PURPOSE:
    - Central place for payment approval logic
    - Used by admin views

    FIXES INCLUDED:
    ✔ Prevents DecimalField crash (invalid amount)
    ✔ Uses approved_at (correct project logic)
    ✔ Safely updates PaymentRequest
    ✔ Adds audit logging
    ✔ Handles corrupted legacy data
    """

    # ---------------------------------------------------
    # FETCH PAYMENT
    # ---------------------------------------------------
    payment = get_object_or_404(Payment, id=payment_id)

    # ---------------------------------------------------
    # VALIDATE / FIX AMOUNT (CRITICAL)
    # ---------------------------------------------------
    try:
        payment.amount = Decimal(payment.amount)
    except (InvalidOperation, TypeError):
        # 🔥 If corrupted data exists, fix it safely
        raise ValueError(
            f"[CRITICAL] Invalid amount on Payment {payment.id}: {payment.amount}"
        )

    # ---------------------------------------------------
    # SET APPROVAL FIELDS (YOUR SYSTEM STANDARD)
    # ---------------------------------------------------
    payment.status = "approved"   # or Payment.STATUS_COMPLETED if defined
    payment.approved_at = now()  # ✅ THIS is your real approval flag

    if approved_by:
        payment.approved_by = approved_by

    payment.save()

    # ---------------------------------------------------
    # UPDATE RELATED PAYMENT REQUEST (SAFE)
    # ---------------------------------------------------
    payment_request = payment.payment_request

    if payment_request:

        try:
            total_paid = Decimal(payment_request.total_paid)
        except (InvalidOperation, TypeError):
            total_paid = Decimal("0.00")

        if total_paid >= payment_request.amount:
            payment_request.status = PaymentRequest.STATUS_CLOSED
            payment_request.save()

    # ---------------------------------------------------
    # AUDIT LOG (IMPORTANT FOR ADMIN TRACEABILITY)
    # ---------------------------------------------------
    
    AuditLog.log_action(
        admin=request.user,
        action=AuditLog.ACTION_PAYMENT_APPROVED,
        target_member=payment.member,
        payment=payment,
         message=f"Payment {payment.id} approved by admin"
    )


    return payment


def create_payment_request(
    *,
    member=None,
    claim=None,
    amount=None,
    description="",
    due_date=None,
    request_type="other",
    payment_method=None,
    ):

    # =========================
    # HARD VALIDATION
    # =========================
    if not payment_method:
        raise ValueError("Payment method is required.")

    if payment_method not in ["manual", "card", "both"]:
        raise ValueError(f"Invalid payment method: {payment_method}")

    if amount is None:
        raise ValueError("Amount is required")

    try:
        amount = Decimal(str(amount))
    except (InvalidOperation, TypeError):
        raise ValueError("Invalid amount")

    if amount <= 0:
        raise ValueError("Amount must be > 0")

    # =========================
    # CREATE OBJECT
    # =========================
    pr = PaymentRequest(
        member=member,
        claim=claim,
        amount=amount,
        description=description,
        due_date=due_date,
        request_type=request_type,
        payment_method=payment_method,
        status="active",
        created_at=timezone.now(),
    )

    pr.save()
    return pr

def create_manual_payment(member, payment_request, proof=None):
    """
    Create or reuse manual payment.

    ✔ Reuses rejected payments
    ✔ Prevents duplicates
    ✔ Keeps DB constraint intact
    """

    payment = Payment.objects.filter(
        member=member,
        payment_request=payment_request
    ).first()

    if payment:
        # ---------------------------------------
        # REUSE REJECTED PAYMENT
        # ---------------------------------------
        if payment.status == Payment.STATUS_REJECTED:
            payment.status = Payment.STATUS_PENDING
            payment.amount = payment_request.amount
            payment.payment_method = "manual"
            payment.external_payment_id = None

        else:
            raise Exception("Payment already exists.")

    else:
        # ---------------------------------------
        # CREATE NEW PAYMENT
        # ---------------------------------------
        payment = Payment.objects.create(
        member=member,
        payment_request=payment_request,
        amount=payment_request.amount,

        # ---------------------------------------
        # IMPORTANT:
        # Inherit type from request
        # ---------------------------------------

        payment_type=payment_request.request_type,

        payment_method="manual",
        status=Payment.STATUS_PENDING
    )

    # ---------------------------------------
    # SAVE PROOF
    # ---------------------------------------
    if proof:
        payment.proof = proof

    payment.save()

    return payment