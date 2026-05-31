"""
ADMIN PAYMENT ACTIONS SERVICE

Single source of truth for:
✔ approving payments
✔ rejecting payments

Ensures:
✔ consistent lifecycle
✔ audit logging
✔ member status sync
"""

from django.db import transaction
from backend.members.models import (
    Payment,
    MemberPaymentStatus,
    AuditLog
)


# ==========================================================
# APPROVE PAYMENT
# ==========================================================
@transaction.atomic
def approve_payment(payment, admin_user=None):
    """
    Approve a payment.

    ✔ Sets payment to COMPLETED
    ✔ Updates MemberPaymentStatus
    ✔ Adds to paid_members
    ✔ Creates audit log
    """

    if payment.status == Payment.STATUS_COMPLETED:
        return

    payment.status = Payment.STATUS_COMPLETED
    payment.save(update_fields=["status"])

    pr = payment.payment_request
    member = payment.member

    # ---------------------------------------
    # UPDATE MEMBER PAYMENT STATUS
    # ---------------------------------------
    status_obj, _ = MemberPaymentStatus.objects.get_or_create(
        member=member,
        payment_request=pr,
    )

    status_obj.status = MemberPaymentStatus.STATUS_PAID
    status_obj.save(update_fields=["status"])

    # ---------------------------------------
    # UPDATE MANY-TO-MANY
    # ---------------------------------------
    pr.paid_members.add(member)

    # ---------------------------------------
    # AUDIT LOG
    # ---------------------------------------
    AuditLog.objects.create(
        admin=admin_user,
        action="payment_approved",
        target_member=member,
        payment=payment,
        message=f"Payment approved for request #{pr.id}"
    )


# ==========================================================
# REJECT PAYMENT
# ==========================================================
@transaction.atomic
def reject_payment(payment, admin_user=None, reason=None):
    """
    Reject a payment.

    ✔ Sets payment to REJECTED
    ✔ Updates MemberPaymentStatus to UNPAID
    ✔ Removes from paid_members
    ✔ Creates audit log
    """

    payment.status = Payment.STATUS_REJECTED
    payment.save(update_fields=["status"])

    pr = payment.payment_request
    member = payment.member

    # ---------------------------------------
    # UPDATE MEMBER PAYMENT STATUS
    # ---------------------------------------
    status_obj, _ = MemberPaymentStatus.objects.get_or_create(
        member=member,
        payment_request=pr,
    )

    status_obj.status = MemberPaymentStatus.STATUS_UNPAID
    status_obj.save(update_fields=["status"])

    # ---------------------------------------
    # REMOVE FROM PAID MEMBERS
    # ---------------------------------------
    pr.paid_members.remove(member)

    # ---------------------------------------
    # AUDIT LOG
    # ---------------------------------------
    AuditLog.objects.create(
        admin=admin_user,
        action="payment_rejected",
        target_member=member,
        payment=payment,
        message=f"Payment rejected. Reason: {reason or 'Not provided'}"
    )