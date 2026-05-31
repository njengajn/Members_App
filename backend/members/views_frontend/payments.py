"""
MEMBER FRONTEND - PAYMENTS MODULE
---------------------------------------------------------
Cleaned and unified.

✔ Single source of truth for payment requests
✔ No conflicting filters
✔ Pending / Paid / Overdue handled correctly
"""

from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q
from django.conf import settings
import stripe

from backend.members.decorators import member_required
from backend.members.models import (
    Member,
    Payment,
    PaymentRequest,
    Claim,
    AuditLog,
)
from backend.members.utils.payments import (
    validate_payment_method,
    log_payment_event
)
from backend.members.services.payment_service import (
    record_payment,
    create_manual_payment
)

stripe.api_key = settings.STRIPE_SECRET_KEY


# ======================================================
# HELPER
# ======================================================
def ensure_active_member(request):
    member = request.user.member

    if member.status != "active":
        messages.error(request, "Your account is not active.")
        return None

    return member

# ======================================================
# PAYMENT REQUEST LIST (SINGLE SOURCE OF TRUTH)
# ======================================================
@login_required
@member_required
def member_payment_requests(request):

    member = ensure_active_member(request)

    if not member:
        return redirect("members:dashboard")

    now = timezone.now()

    # ======================================================
    # FETCH PAYMENT REQUESTS
    # ======================================================
    payment_requests = (

        PaymentRequest.objects

        .filter(
            Q(viewable_by_all=True) |
            Q(member=member) |
            Q(selected_members=member)
        )

        .prefetch_related("payments")

        .distinct()

        .order_by("-created_at")

    )

    # ======================================================
    # COMPUTE MEMBER STATES
    # ======================================================
    for req in payment_requests:

        # --------------------------------------------------
        # MEMBER PAYMENTS FOR THIS REQUEST
        # --------------------------------------------------
        member_payments = [

            p for p in req.payments.all()

            if p.member_id == member.id

        ]

        # --------------------------------------------------
        # COMPLETED PAYMENT
        # --------------------------------------------------
        completed_payment_exists = any(
            p.status == Payment.STATUS_COMPLETED
            for p in member_payments
        )

        # --------------------------------------------------
        # PENDING PAYMENT
        # MEMBER HAS ALREADY SUBMITTED PAYMENT
        # --------------------------------------------------
        pending_payment_exists = any(
            p.status == Payment.STATUS_PENDING
            for p in member_payments
        )

        # --------------------------------------------------
        # PAYMENT REQUEST AWAITING APPROVAL
        # --------------------------------------------------
        req.is_request_pending = (
            req.status == "pending"
        )

        # --------------------------------------------------
        # MEMBER PAYMENT PENDING CONFIRMATION
        # --------------------------------------------------
        req.is_payment_pending = (
            pending_payment_exists
        )

        # --------------------------------------------------
        # FULLY PAID
        # --------------------------------------------------
        req.is_paid = (
            completed_payment_exists
        )

        # --------------------------------------------------
        # MEMBER OVERDUE
        # --------------------------------------------------
        req.is_overdue_member = (

            not completed_payment_exists

            and req.due_date

            and req.due_date < now

            and not pending_payment_exists

        )

        # --------------------------------------------------
        # ENDING SOON
        # --------------------------------------------------
        req.is_ending_soon = (

            req.due_date

            and req.due_date > now

            and (req.due_date - now).days <= 2

        )

    # ======================================================
    # RENDER
    # ======================================================
    return render(
        request,
        "members/payments/members_payment_list.html",
        {
            "payment_requests": payment_requests,
        },
    )

# ======================================================
# PAYMENT REQUEST DETAIL
# ======================================================
@login_required
@member_required
def payment_request_detail(request, pk):

    member = ensure_active_member(request)
    if not member:
        return redirect("members:dashboard")

    payment_request = get_object_or_404(
        PaymentRequest,
        pk=pk,
    )

    return render(
        request,
        "members/payments/members_payment_request_detail.html",
        {"payment_request": payment_request},
    )


# ======================================================
# PAY REQUEST ENTRY POINT
# ======================================================
@login_required
@member_required
def pay_payment_request(request, pk):

    payment_request = get_object_or_404(PaymentRequest, pk=pk)
    member = request.user.member
    
    existing_pending = Payment.objects.filter(
        payment_request=payment_request,
        member=request.user.member,
        status=Payment.STATUS_PENDING
    ).exists()

    if existing_pending:

        messages.warning(
            request,
            "Your payment is awaiting confirmation."
        )

        return redirect(
            "members:member_payment_requests"
        )

    # COMPLETED
    if Payment.objects.filter(
        member=member,
        payment_request=payment_request,
        status=Payment.STATUS_COMPLETED
    ).exists():
        messages.error(request, "You have already paid.")
        return redirect("members:member_payment_requests")

    # PENDING
    if Payment.objects.filter(
        member=member,
        payment_request=payment_request,
        status=Payment.STATUS_PENDING
    ).exists():
        messages.warning(request, "Payment awaiting confirmation.")
        return redirect("members:member_payment_requests")

    # CLOSED / OVERDUE
    if (
        payment_request.status != PaymentRequest.STATUS_ACTIVE
        or payment_request.is_overdue
    ):
        messages.error(request, "This request is no longer payable.")
        return redirect("members:member_payment_requests")

    return render(
        request,
        "members/payments/payment_checkout.html",
        {"payment_request": payment_request},
    )


# ======================================================
# MANUAL PAYMENT
# ======================================================
@login_required
@member_required
def manual_payment_page(request, pk):

    member = ensure_active_member(request)
    if not member:
        return redirect("members:dashboard")

    payment_request = get_object_or_404(PaymentRequest, pk=pk)

    status = payment_request.member_payment_status(member)

    if status == "paid":
        messages.error(request, "Already paid.")
        return redirect("members:member_payment_requests")

    if status == "pending":
        messages.warning(request, "Awaiting confirmation.")
        return redirect("members:member_payment_requests")

    if payment_request.payment_method == PaymentRequest.METHOD_CARD:
        messages.error(request, "Must be paid by card.")
        return redirect("members:member_payment_requests")

    return render(
        request,
        "members/payments/members_manual_payment.html",
        {"payment_request": payment_request},
    )


@login_required
@member_required
def confirm_manual_payment(request, pk):

    member = ensure_active_member(request)
    if not member:
        return redirect("members:dashboard")

    payment_request = get_object_or_404(PaymentRequest, pk=pk)

    status = payment_request.member_payment_status(member)

    if status in ["paid", "pending"]:
        messages.warning(request, "Cannot process payment.")
        return redirect("members:member_payment_requests")

    if request.method == "POST":
        proof = request.FILES.get("proof")

        payment = create_manual_payment(member, payment_request, proof)

        AuditLog.objects.create(
            admin=request.user,
            action="payment_uploaded",
            payment=payment,
        )

        messages.success(request, "Submitted for approval.")

        return redirect("members:member_payment_requests")

    return redirect("members:manual_payment_page", pk=pk)


# ======================================================
# STRIPE
# ======================================================
@login_required
@member_required
def create_stripe_checkout(request, pk):

    member = ensure_active_member(request)
    if not member:
        return redirect("members:dashboard")

    payment_request = get_object_or_404(PaymentRequest, pk=pk)

    status = payment_request.member_payment_status(member)

    if status in ["paid", "pending"]:
        messages.warning(request, "Cannot process payment.")
        return redirect("members:member_payment_requests")

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "gbp",
                "product_data": {"name": payment_request.title},
                "unit_amount": int(payment_request.amount * 100),
            },
            "quantity": 1,
        }],
        mode="payment",
        success_url=request.build_absolute_uri(
            f"/payments/{payment_request.id}/success/"
        ),
        cancel_url=request.build_absolute_uri(
            "/members/payment-requests/"
        )
    )

    return redirect(session.url)


@login_required
@member_required
def stripe_payment_success(request, pk):

    member = ensure_active_member(request)
    if not member:
        return redirect("members:dashboard")

    payment_request = PaymentRequest.objects.get(id=pk)

    record_payment(member, payment_request)

    messages.success(request, "Payment successful.")

    return redirect("members:member_payment_requests")

@login_required
@member_required
def payment_receipt(request, payment_uid):
    """
    Display receipt for completed payment
    """

    payment = get_object_or_404(
        Payment,
        uid=payment_uid,
        member=request.user.member,
        status=Payment.STATUS_COMPLETED,
    )

    return render(
        request,
        "members/payments/receipt.html",
        {"payment": payment},
    )