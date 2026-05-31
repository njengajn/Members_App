# backend/members/utils/payments.py

from django.contrib import messages
from django.utils import timezone
from datetime import datetime
from backend.members.models import Member, PaymentAuditLog, PaymentRequest, Payment


# =========================================================
# PAYMENT METHOD VALIDATION (ROBUST + SAFE)
# =========================================================
def validate_payment_method(request, payment_request, method):
    """
    STRICT ENFORCEMENT

    Handles:
    - manual
    - card
    - both
    """

    allowed = (payment_request.payment_method or "").lower().strip()
    method = method.lower().strip()

    # BOTH → always allowed
    if allowed == "both":
        return True

    # MANUAL ONLY
    if allowed == "manual" and method != "manual":
        messages.error(request, "This payment must be made manually.")
        return False

    # CARD ONLY
    if allowed == "card" and method != "card":
        messages.error(request, "This payment must be made by card.")
        return False

    # fallback safety
    if method != allowed:
        messages.error(request, "Invalid payment method.")
        return False

    return True


# =========================================================
# PREVENT DOUBLE PAYMENT
# =========================================================
def has_already_paid(member, payment_request):
    return Payment.objects.filter(
        member=member,
        payment_request=payment_request
    ).exists()


# =========================================================
# DUE DATE VALIDATION (FIXED)
# =========================================================
def validate_due_date(due_date_str):
    """
    ONLY allow FUTURE dates
    """

    if not due_date_str:
        raise ValueError("Due date is required.")

    try:
        due_date = datetime.strptime(due_date_str, "%Y-%m-%d")
        due_date = timezone.make_aware(due_date)
    except Exception:
        raise ValueError("Invalid due date format.")

    # 🔴 CRITICAL: this must NOT be inside try
    if due_date <= timezone.now():
        raise ValueError("Due date must be in the future.")

    return due_date


# =========================================================
# AUDIT LOGGING
# =========================================================
def log_payment_event(member, payment_request, action, method=None, notes=None):

    PaymentAuditLog.objects.create(
        member=member,
        payment_request=payment_request,
        action=action,
        method=method,
        notes=notes
    )

def get_paid_member_ids(payment_request):
    """
    Returns a set of member IDs who have COMPLETED payments
    for the given PaymentRequest.
    """
    return set(
        payment_request.payments.filter(
            status=Payment.STATUS_COMPLETED
        ).values_list("member_id", flat=True)
    )


def get_eligible_members(payment_request):
    """
    Returns queryset of members eligible to pay this request.
    """
    if payment_request.viewable_by_all:
        return Member.objects.all()
    return payment_request.selected_members.all()


def get_unpaid_members(payment_request):
    """
    Returns queryset of members who have NOT paid.
    """
    paid_ids = get_paid_member_ids(payment_request)
    return get_eligible_members(payment_request).exclude(id__in=paid_ids)


def auto_close_expired_payments():
    """
    AUTO CLOSE EXPIRED REQUESTS

    ✔ Safe to run multiple times
    ✔ Cron / Celery ready
    ✔ No side effects beyond status update
    """

    now = timezone.now()

    expired = PaymentRequest.objects.filter(
        status=PaymentRequest.STATUS_ACTIVE,
        due_date__isnull=False,
        due_date__lt=now
    )

    count = expired.count()

    expired.update(status=PaymentRequest.STATUS_CLOSED)

    return count

