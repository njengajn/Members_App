# =========================================================
# backend/members/services/notifications.py
# =========================================================

"""
Centralized notification system.

Handles:
- HTML email notifications
- WhatsApp notifications
- Branding
- Payment warnings
- Retirement alerts
- Activation alerts
- Payment request alerts
- Payment confirmation alerts
- Payment rejection alerts
- Stripe payment alerts
"""

import os

from django.conf import settings
import json
from django.core.mail import (
    EmailMultiAlternatives,
)
from django.template.loader import (
    render_to_string
)
from django.utils import timezone
from twilio.rest import Client
from backend.members.models import (
    Member,
    MemberPaymentStatus,
    PaymentRequest,
)
# =========================================================
# SAFE PAYMENT PORTAL URL
# =========================================================

PAYMENTS_URL = getattr(

        settings,

        "PAYMENTS_PORTAL_URL",

        "http://127.0.0.1:8000/payments"
    )

# =========================================================
# WHATSAPP SENDER
# =========================================================

def send_whatsapp_message(
    phone_number,
    message,
):
    """
    Send WhatsApp message using Twilio.
    """

    if not phone_number:

        print(
            "WhatsApp skipped: "
            "No phone number."
        )

        return

    try:

        phone_number = str(
            phone_number
        ).strip()

        # =================================================
        # UK NUMBER FIX
        # =================================================

        if phone_number.startswith("0"):

            phone_number = (
                "+44" + phone_number[1:]
            )

        client = Client(

            settings.TWILIO_ACCOUNT_SID,

            settings.TWILIO_AUTH_TOKEN,
        )
        
        print(
            "FROM:",
            f"whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}"
        )

        print(
            "TO:",
            f"whatsapp:{phone_number}"
        )

        response = client.messages.create(

            body=message,

            from_=(
                "whatsapp:"
                f"{settings.TWILIO_WHATSAPP_NUMBER}"
            ),

            to=f"whatsapp:{phone_number}",
        )

        print(
            "WhatsApp sent:",
            response.sid
        )

    except Exception as e:

        print(
            "WhatsApp error:",
            str(e)
        )


# =========================================================
# BASE EMAIL SENDER
# =========================================================

def send_html_email(
    *,
    recipient,
    subject,
    template,
    context,
):
    """
    Central reusable HTML email sender.
    """

    if not recipient:

        print(
            "Email skipped: "
            "No recipient."
        )

        return

    try:

        # =================================================
        # PUBLIC LOGO URL
        # =================================================

        context["logo_url"] = (
            "https://i.postimg.cc/6p5Syzg9/logo.png"
        )

        # =================================================
        # PAYMENT PORTAL URL
        # =================================================

        context["payments_url"] = (
            PAYMENTS_URL
        )

        # =================================================
        # RENDER HTML
        # =================================================

        html_content = render_to_string(
            template,
            context
        )

        # =================================================
        # TEXT FALLBACK
        # =================================================

        text_content = (
            context.get("plain_message")
            or subject
        )

        # =================================================
        # CREATE EMAIL
        # =================================================

        email_message = EmailMultiAlternatives(

            subject=subject,

            body=text_content,

            from_email=settings.DEFAULT_FROM_EMAIL,

            to=[recipient],

        )

        # =================================================
        # ATTACH HTML VERSION
        # =================================================

        email_message.attach_alternative(
            html_content,
            "text/html"
        )

        # =================================================
        # SEND
        # =================================================
        
        print("EMAIL_HOST_USER:", settings.EMAIL_HOST_USER)

        print(
            "EMAIL_HOST_PASSWORD_EXISTS:",
            bool(settings.EMAIL_HOST_PASSWORD)
        )

        print(
            "DEFAULT_FROM_EMAIL:",
            settings.DEFAULT_FROM_EMAIL
        )

        email_message.send(
            fail_silently=False
        )

        print(
            "Email sent:",
            recipient
        )

    except Exception as e:

        import traceback

        print(
            "\nEMAIL ERROR:\n"
        )

        traceback.print_exc()

# =========================================================
# SEND WHATSAPP TEMPLATE MESSAGE
# =========================================================

def send_whatsapp_template_message(
    *,
    phone_number,
    template_sid,
    variables,
):
    """
    Send approved WhatsApp template message.
    """

    if not phone_number:

        print(
            "WhatsApp skipped: "
            "No phone number."
        )

        return

    try:

        # =================================================
        # CLEAN NUMBER
        # =================================================

        phone_number = str(
            phone_number
        ).strip()

        # =================================================
        # UK FORMAT FIX
        # =================================================

        if phone_number.startswith("0"):

            phone_number = (
                "+44" + phone_number[1:]
            )

        # =================================================
        # CREATE CLIENT
        # =================================================

        client = Client(

            settings.TWILIO_ACCOUNT_SID,

            settings.TWILIO_AUTH_TOKEN,
        )

        # =================================================
        # SEND TEMPLATE
        # =================================================

        response = client.messages.create(

            content_sid=template_sid,

            content_variables=json.dumps(
                variables
            ),

            from_=(
                "whatsapp:"
                f"{settings.TWILIO_WHATSAPP_NUMBER}"
            ),

            to=f"whatsapp:{phone_number}",
        )

    except Exception:

        import traceback

        traceback.print_exc()

# =========================================================
# PAYMENT REQUEST CREATED
# =========================================================

def send_payment_request_notification(
    member,
    payment_request,
):
    """
    Notify member of new payment request.
    """

    payment_reference = (
        f"PR-"
        f"{str(payment_request.uid)[:8].upper()}"
    )

    # =====================================================
    # EMAIL
    # =====================================================

    if member.email:

        print(
            "Sending payment request email to:",
            member.email
        )

        send_html_email(

            recipient=member.email,

            subject="New Payment Request",

            template=(
                "members/emails/"
                "payment_request_created.html"
            ),

            context={

                "email_title": (
                    "Payment Request Created"
                ),

                "first_name": (
                    member.first_name
                    or "Member"
                ),

                "member": member,

                "payment_request": (
                    payment_request
                ),

                "payment_reference": (
                    payment_reference
                ),

                "current_year": (
                    timezone.now().year
                ),

                "plain_message": (

                    f"Payment Request Created\n\n"

                    f"Reference:\n"
                    f"{payment_reference}\n\n"

                    f"Title:\n"
                    f"{payment_request.title}\n\n"

                    f"Description:\n"
                    f"{payment_request.description}\n\n"

                    f"Amount:\n"
                    f"£{payment_request.amount}\n\n"

                    f"Due Date:\n"
                    f"{payment_request.due_date:%d %b %Y}\n\n"

                    f"Pay Online:\n"
                    f"{PAYMENTS_URL}\n\n"

                    f"Thank you for your "
                    f"continued support.\n\n"

                    f"KRO Welfare Management"
                ),
            },
        )

    # =====================================================
    # WHATSAPP TEMPLATE
    # =====================================================

    if member.phone:

        print(
            "PAYMENT TEMPLATE SID:",
            settings
            .TWILIO_PAYMENT_REQUEST_TEMPLATE_SID
        )

        send_whatsapp_template_message(

            phone_number=member.phone,

            template_sid=(
                settings
                .TWILIO_PAYMENT_REQUEST_TEMPLATE_SID
            ),

            variables={

                "1": (
                    member.first_name
                    or "Member"
                ),

                "2": payment_reference,

                "3": (
                    payment_request.description
                    or "Payment Request"
                ),

                "4": str(
                    payment_request.amount
                ),

                "5": (
                    payment_request
                    .due_date
                    .strftime("%d %b %Y")
                ),

                "6": PAYMENTS_URL,
            },
        )

# =========================================================
# PAYMENT CONFIRMED
# =========================================================

def send_payment_confirmed_notification(
    payment
    ):
    """
    Notify member after payment approval.
    """

    member = payment.member

    payment_reference = (
        f"PR-"
        f"{str(payment.payment_request.uid)[:8].upper()}"
    )

    # =====================================================
    # EMAIL
    # =====================================================

    if member.email:

        send_html_email(

            recipient=member.email,

            subject="Payment Confirmed",

            template=(
                "members/emails/"
                "payment_confirmed.html"
            ),

            context={

                "email_title": (
                    "Payment Confirmed"
                ),

                "first_name": (
                    member.first_name
                    or "Member"
                ),

                "payment": payment,

                "payment_reference": (
                    payment_reference
                ),

                "current_year": (
                    timezone.now().year
                ),

                "plain_message": (

                    f"Payment Confirmed\n\n"

                    f"Reference:\n"
                    f"{payment_reference}\n\n"

                    f"Description:\n"
                    f"{payment.payment_request.description}\n\n"

                    f"Amount:\n"
                    f"£{payment.amount}\n\n"

                    f"Thank you for your "
                    f"continued support.\n\n"

                    f"KRO Welfare Management"
                ),
            },
        )

    # =====================================================
    # WHATSAPP
    # =====================================================

    if member.phone:

        # =====================================================
        # WHATSAPP TEMPLATE
        # =====================================================

        if member.phone:

            send_whatsapp_template_message(

                phone_number=member.phone,

                template_sid=(
                    settings
                    .TWILIO_PAYMENT_CONFIRMED_TEMPLATE_SID
                ),

                variables={

                    "1": (
                        member.first_name
                        or "Member"
                    ),

                    "2": payment_reference,

                    "3": (
                        payment.payment_request.description
                        or "Payment"
                    ),

                    "4": str(
                        payment.amount
                    ),
                },
            )


# =========================================================
# PAYMENT REJECTED
# =========================================================

def send_payment_rejected_notification(
    payment
    ):
    """
    Notify member after payment rejection.
    """

    member = payment.member

    payment_reference = (
        f"PR-"
        f"{str(payment.payment_request.uid)[:8].upper()}"
    )

    # =====================================================
    # EMAIL
    # =====================================================

    if member.email:

        send_html_email(

            recipient=member.email,

            subject="Payment Rejected",

            template=(
                "members/emails/"
                "payment_rejected.html"
            ),

            context={

                "email_title": (
                    "Payment Rejected"
                ),

                "first_name": (
                    member.first_name
                    or "Member"
                ),

                "payment": payment,

                "payment_reference": (
                    payment_reference
                ),

                "current_year": (
                    timezone.now().year
                ),

                "plain_message": (

                    f"Payment Rejected\n\n"

                    f"Reference:\n"
                    f"{payment_reference}\n\n"

                    f"Description:\n"
                    f"{payment.payment_request.description}\n\n"

                    f"Amount:\n"
                    f"£{payment.amount}\n\n"

                    f"Please contact support.\n\n"

                    f"KRO Welfare Management"
                ),
            },
        )

    # =====================================================
    # WHATSAPP
    # =====================================================

    if member.phone:

        # =====================================================
        # WHATSAPP TEMPLATE
        # =====================================================

        if member.phone:

            send_whatsapp_template_message(

                phone_number=member.phone,

                template_sid=(
                    settings
                    .TWILIO_PAYMENT_REJECTED_TEMPLATE_SID
                ),

                variables={

                    "1": (
                        member.first_name
                        or "Member"
                    ),

                    "2": payment_reference,

                    "3": (
                        payment.payment_request.description
                        or "Payment"
                    ),

                    "4": str(
                        payment.amount
                    ),
                },
            )


# =========================================================
# STRIPE PAYMENT COMPLETED
# =========================================================

def send_stripe_payment_completed_notification(
    payment
    ):
    """
    Notify after successful Stripe payment.
    """

    member = payment.member

    payment_reference = (
        f"PR-"
        f"{str(payment.payment_request.uid)[:8].upper()}"
    )

    # =====================================================
    # EMAIL
    # =====================================================

    if member.email:

        send_html_email(

            recipient=member.email,

            subject="Stripe Payment Successful",

            template=(
                "members/emails/payments/"
                "stripe_payment_completed.html"
            ),

            context={

                "email_title": (
                    "Payment Successful"
                ),

                "first_name": (
                    member.first_name
                    or "Member"
                ),

                "payment": payment,

                "payment_reference": (
                    payment_reference
                ),

                "current_year": (
                    timezone.now().year
                ),

                "plain_message": (

                    f"Stripe Payment Successful\n\n"

                    f"Reference:\n"
                    f"{payment_reference}\n\n"

                    f"Description:\n"
                    f"{payment.payment_request.description}\n\n"

                    f"Amount:\n"
                    f"£{payment.amount}\n\n"

                    f"Thank you for your "
                    f"continued support.\n\n"

                    f"KRO Welfare Management"
                ),
            },
        )

    # =====================================================
    # WHATSAPP
    # =====================================================

    if member.phone:

        # =====================================================
        # WHATSAPP TEMPLATE
        # =====================================================

        if member.phone:

            send_whatsapp_template_message(

                phone_number=member.phone,

                template_sid=(
                    settings
                    .TWILIO_STRIPE_PAYMENT_TEMPLATE_SID
                ),

                variables={

                    "1": (
                        member.first_name
                        or "Member"
                    ),

                    "2": payment_reference,

                    "3": (
                        payment.payment_request.description
                        or "Stripe Payment"
                    ),

                    "4": str(
                        payment.amount
                    ),
                },
            )


# =========================================================
# 24H WARNING ALERTS
# =========================================================

def send_24h_warning_notifications():

    """
    Notify members they are about to
    be retired in 24h.
    """

    now = timezone.now()

    soon = now + timezone.timedelta(hours=24)

    at_risk = MemberPaymentStatus.objects.filter(

        status=MemberPaymentStatus.STATUS_UNPAID,

        payment_request__due_date__range=(
            now,
            soon
        ),

        payment_request__request_type__in=[
            "claim",
            "subscription",
            "other",
        ],

        payment_request__status=(
            PaymentRequest.STATUS_ACTIVE
        ),

    ).select_related(
        "member",
        "payment_request",
    )

    for ms in at_risk:

        member = ms.member

        payment_request = ms.payment_request

        # =================================================
        # EMAIL
        # =================================================

        if member.email:

            send_html_email(

                recipient=member.email,

                subject=(
                    "⚠ Payment Due - "
                    "Risk of Retirement"
                ),

                template=(
                    "members/emails/"
                    "payment_due_warning.html"
                ),

                context={

                    "email_title": (
                        "Payment Due Warning"
                    ),

                    "first_name": (
                        member.first_name
                        or "Member"
                    ),

                    "member": member,

                    "payment_request": (
                        payment_request
                    ),

                    "current_year": (
                        timezone.now().year
                    ),

                    "plain_message": (
                        "Your membership "
                        "may be retired "
                        "within 24 hours."
                    ),
                },
            )

        # =================================================
        # WHATSAPP
        # =================================================

        if member.phone:

            send_whatsapp_message(

                member.phone,

                (
                    f"KRO NOTICE\n\n"

                    f"Your payment request "
                    f"is overdue and your "
                    f"membership may be retired "
                    f"within 24 hours.\n\n"

                    f"Amount:\n"
                    f"£{payment_request.amount}\n\n"

                    f"Due Date:\n"
                    f"{payment_request.due_date:%d %b %Y}\n\n"

                    f"Pay Online:\n"
                    f"{PAYMENTS_URL}"
                ),
            )


# =========================================================
# RETIREMENT ALERT
# =========================================================

def send_retirement_notification(
    member
    ):
    """
    Notify member after retirement.
    """

    # =====================================================
    # EMAIL
    # =====================================================

    if member.email:

        send_html_email(

            recipient=member.email,

            subject="Account Retired",

            template=(
                "members/emails/"
                "member_retired.html"
            ),

            context={

                "email_title": (
                    "Membership Retired"
                ),

                "first_name": (
                    member.first_name
                    or "Member"
                ),

                "member": member,

                "reason": (
                    member.retired_reason
                    or "Non-compliance"
                ),

                "current_year": (
                    timezone.now().year
                ),

                "plain_message": (
                    "Your membership "
                    "has been retired."
                ),
            },
        )

    # =====================================================
    # WHATSAPP
    # =====================================================

    if member.phone:

        # =====================================================
        # WHATSAPP TEMPLATE
        # =====================================================

        if member.phone:

            send_whatsapp_template_message(

                phone_number=member.phone,

                template_sid=(
                    settings
                    .TWILIO_MEMBER_RETIRED_TEMPLATE_SID
                ),

                variables={

                    "1": (
                        member.first_name
                        or "Member"
                    ),

                    "2": (
                        member.retired_reason
                        or "Non-compliance"
                    ),
                },
            )


# =========================================================
# MEMBER ACTIVATION ALERT
# =========================================================

def send_member_activation_notification(
    member
    ):
    """
    Notify member after activation.
    """

    # =====================================================
    # EMAIL
    # =====================================================

    if member.email:

        send_html_email(

            recipient=member.email,

            subject="Membership Activated",

            template=(
                "members/emails/"
                "member_activated.html"
            ),

            context={

                "email_title": (
                    "Membership Activated"
                ),

                "first_name": (
                    member.first_name
                    or "Member"
                ),

                "member": member,

                "current_year": (
                    timezone.now().year
                ),

                "plain_message": (
                    f"Your member ID is "
                    f"{member.member_uid}"
                ),
            },
        )

    # =====================================================
    # WHATSAPP
    # =====================================================

    if member.phone:

        # =====================================================
        # WHATSAPP TEMPLATE
        # =====================================================

        if member.phone:

            send_whatsapp_template_message(

                phone_number=member.phone,

                template_sid=(
                    settings
                    .TWILIO_MEMBER_ACTIVATED_TEMPLATE_SID
                ),

                variables={

                    "1": (
                        member.first_name
                        or "Member"
                    ),

                    "2": (
                        member.member_uid
                        or "Pending"
                    ),
                },
            )
        
