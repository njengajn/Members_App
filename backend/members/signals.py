"""
CENTRAL SIGNALS FILE (CLEANED)

Responsibilities:
✔ Sync MemberPaymentStatus
✔ Sync paid_members (UI helper)
✔ Create MemberPaymentStatus records on request creation
✔ Handle claim payment register updates
✔ Send payment receipts

IMPORTANT:
❌ NO lifecycle logic here
❌ NO retirement logic here
→ Those live in payments_lifecycle.py
"""

from django.utils import timezone

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings

from backend.members.models import (
    Claim,
    ClaimRegister,
    Payment,
    Member,
    Dependant,
    PaymentRequest,
    MemberPaymentStatus,
    Notification,
)        
from django.db.models.signals import post_save
from django.dispatch import receiver

from backend.members.models import Member
from backend.members.models import PaymentRequest
#from backend.notifications.models import Notification


# ==========================================================
# CLAIM → SET DERIVED FIELDS
# ==========================================================
@receiver(post_save, sender=Claim)
def populate_claim_fields(sender, instance, created, **kwargs):
    """
    Sets derived fields after claim creation.
    """

    if not created:
        return

    if instance.cause_type == Claim.CLAIM_CAUSER_DEPENDANT:
        if instance.causer_dependant:
            instance.causer_full_name = instance.causer_dependant.full_name
            instance.claimer = f"{instance.member.first_name} {instance.member.surname}"
            instance.claimer_is_next_of_kin = False

    elif instance.cause_type == Claim.CLAIM_CAUSER_MEMBER:
        instance.causer_full_name = f"{instance.member.first_name} {instance.member.surname}"

        nok = getattr(instance.member, "next_of_kin", None)

        if nok:
            instance.claimer = f"{nok.first_name} {nok.surname}"
        else:
            instance.claimer = "Next of Kin (Not Provided)"

        instance.claimer_is_next_of_kin = True

    instance.save(update_fields=[
        "causer_full_name",
        "claimer",
        "claimer_is_next_of_kin",
    ])


# ==========================================================
# PAYMENT REQUEST → INITIALIZE MEMBER STATUS
# ==========================================================
@receiver(post_save, sender=PaymentRequest)
def create_member_payment_statuses(sender, instance, created, **kwargs):
    """
    When a PaymentRequest is created:
    - mark all target members as UNPAID
    """

    if not created:
        return

    if instance.viewable_by_all:
        members_qs = Member.objects.filter(status=Member.STATUS_ACTIVE)
    else:
        members_qs = instance.selected_members.all()

    for m in members_qs:
        MemberPaymentStatus.objects.get_or_create(
            member=m,
            payment_request=instance,
            defaults={"status": MemberPaymentStatus.STATUS_UNPAID}
        )


# ==========================================================
# PAYMENT → SYNC MEMBER STATUS (CORE SIGNAL)
# ==========================================================
@receiver(post_save, sender=Payment)
def update_member_payment_status(sender, instance, **kwargs):
    """
    Runs when a Payment is saved.

    PURPOSE:
    ✔ Mark member as PAID
    ✔ Sync MemberPaymentStatus
    ✔ Sync paid_members (UI helper)
    """

    if instance.status != Payment.STATUS_COMPLETED:
        return

    pr = instance.payment_request

    if not pr:
        return

    status_obj, _ = MemberPaymentStatus.objects.get_or_create(
        member=instance.member,
        payment_request=pr,
    )

    if status_obj.status != MemberPaymentStatus.STATUS_PAID:
        status_obj.status = MemberPaymentStatus.STATUS_PAID
        status_obj.save(update_fields=["status"])

    # UI helper (fast checks)
    pr.paid_members.add(instance.member)


# ==========================================================
# PAYMENT → CLAIM REGISTER UPDATE
# ==========================================================
@receiver(post_save, sender=Payment)
def update_claim_register(sender, instance, **kwargs):
    """
    Adds paid member to ClaimRegister (if claim payment).
    """

    if instance.status != Payment.STATUS_COMPLETED:
        return

    pr = instance.payment_request

    if not pr or pr.request_type != "claim" or not pr.claim:
        return

    register, _ = ClaimRegister.objects.get_or_create(
        claim=pr.claim,
        defaults={"action": "Auto created from payment"},
    )

    register.add_paid_member(instance.member)


# ==========================================================
# PAYMENT → SEND RECEIPT
# ==========================================================
@receiver(post_save, sender=Payment)
def send_payment_receipt(sender, instance, created, **kwargs):
    """
    Sends receipt email (safe in dev with console backend).
    """

    if not created:
        return

    if not instance.member or not hasattr(instance.member, "user"):
        return

    email = instance.member.user.email

    if not email:
        return

    send_mail(
        subject="Payment Receipt",
        message=(
            f"Receipt: {instance.external_payment_id}\n"
            f"Amount: £{instance.amount}"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=True,
    )


# ==========================================================
# MEMBER → PREVENT UID CHANGE
# ==========================================================
@receiver(pre_save, sender=Member)
def prevent_uid_change(sender, instance, **kwargs):
    """
    Prevent member UID from being modified.
    """

    if not instance.pk:
        return

    previous = Member.objects.filter(pk=instance.pk).first()

    if not previous:
        return

    if previous.uid_assigned:
        instance.member_uid = previous.member_uid
        
from django.db.models.signals import post_save
from django.dispatch import receiver

from backend.members.models import Payment, MemberPaymentStatus


@receiver(post_save, sender=Payment)
def sync_payment_status(sender, instance, **kwargs):
    """
    KEEP ALL SYSTEMS IN SYNC
    """

    pr = instance.payment_request
    member = instance.member

    if not pr:
        return

    # -----------------------------------
    # COMPLETED → mark paid everywhere
    # -----------------------------------
    if instance.status == Payment.STATUS_COMPLETED:

        pr.paid_members.add(member)

        status_obj, _ = MemberPaymentStatus.objects.get_or_create(
            member=member,
            payment_request=pr,
        )
        status_obj.status = MemberPaymentStatus.STATUS_PAID
        status_obj.save()

    # -----------------------------------
    # REJECTED → remove from paid
    # -----------------------------------
    elif instance.status == Payment.STATUS_REJECTED:

        pr.paid_members.remove(member)

        status_obj, _ = MemberPaymentStatus.objects.get_or_create(
            member=member,
            payment_request=pr,
        )
        status_obj.status = MemberPaymentStatus.STATUS_UNPAID
        status_obj.save()

@receiver(post_save, sender=Payment)
def handle_subscription_payment(
    sender,
    instance,
    created,
    **kwargs
):
    """
    Automatically reactivate member
    when annual subscription payment
    is completed.
    """

    # =====================================
    # ONLY COMPLETED PAYMENTS
    # =====================================

    if instance.status != Payment.STATUS_COMPLETED:
        return

    payment_request = instance.payment_request

    if not payment_request:
        return

    # =====================================
    # ONLY SUBSCRIPTION REQUESTS
    # =====================================

    if payment_request.request_type != "subscription":
        return

    member = instance.member

    if not member:
        return

    # =====================================
    # MARK REQUEST PAID
    # =====================================

    payment_request.paid_members.add(member)

            # =====================================
            # RESTORE MEMBER SAFELY
            # =====================================

    member.restore()

            # =====================================
            # UPDATE SUBSCRIPTION YEAR
            # =====================================

    member.subscription_year = timezone.now().year

    member.save(
        update_fields=[
            "subscription_year"
            ]
            )

    # =====================================
    # CLOSE REQUEST IF FULLY PAID
    # =====================================

    if payment_request.is_completed():

        payment_request.status = (
            PaymentRequest.STATUS_CLOSED
        )

        payment_request.save()

    # =====================================
    # NOTIFICATION
    # =====================================

    Notification.objects.create(
        user=member.user,
        title="Subscription Payment Approved",
        message=(
            "Your annual subscription payment "
            "has been received successfully."
        ),
        notification_type="payment"
    )