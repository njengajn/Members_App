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
# ACTIVE MEMBER ONLY
# ======================================================
def ensure_active_member(request):
    """
    Ensure the current member is ACTIVE.

    This helper remains intentionally strict.

    It must continue to be used by functionality
    that requires an active membership, such as:

        - claims
        - claim eligibility
        - other Active-only member resources

    IMPORTANT:
        Approved is NOT treated as Active here.
    """

    member = request.user.member


    if member.status != "active":

        messages.error(
            request,
            "Your account is not active."
        )

        return None


    return member

# ======================================================
# PAYMENT-ELIGIBLE MEMBER
# ======================================================
def ensure_payment_member(request):
    """
    Ensure the current member is allowed to enter
    the payment workflow.

    Payment workflow access is broader than Active-only
    membership access.

    Allowed:

        APPROVED
        ACTIVE

    Not allowed:

        PENDING
        RETIRED

    IMPORTANT:
        This helper only establishes access to the
        payment workflow.

        It does NOT mean an Approved member can pay
        every type of payment request.

        The payment request itself must still be
        targeted to the member and must be an allowed
        request type.
    """

    member = request.user.member


    if member.status not in [
        "approved",
        "active",
    ]:

        messages.error(
            request,
            "Your account is not eligible to make payments."
        )

        return None


    return member

# ======================================================
# PAYMENT REQUEST ACCESS
# ======================================================
def get_member_payment_request(member, pk):
    """
    Return a payment request only when the request is
    actually available to the current member.

    TARGETING RULE
    --------------

    The member must be:

        - the single targeted member, OR
        - included in selected_members, OR
        - included because viewable_by_all=True

    STATUS RULE
    -----------

    Approved members may access:

        - Membership
        - Other

    Active members may access:

        - Membership
        - Subscription
        - Claim
        - Other

    Pending and Retired members are rejected before
    this helper is called.
    """

    member_target = (
        Q(viewable_by_all=True)
        |
        Q(member=member)
        |
        Q(selected_members=member)
    )


    if member.status == "approved":

        allowed_request_types = [
            "membership",
            "other",
        ]

    else:

        # Active members retain the existing broader
        # payment-request access.
        allowed_request_types = [
            "membership",
            "subscription",
            "claim",
            "other",
        ]


    return get_object_or_404(
        PaymentRequest.objects.filter(
            member_target,
            request_type__in=allowed_request_types,
            status=PaymentRequest.STATUS_ACTIVE,
        ).distinct(),
        pk=pk,
    )

# ======================================================
# PAYMENT REQUEST LIST
# ======================================================
@login_required
@member_required
def member_payment_requests(request):
    """
    Display payment requests available to the current
    member.

    Approved members:
        Membership + Other only.

    Active members:
        All applicable payment request types.

    Existing targeting behaviour is preserved:
        - viewable_by_all
        - directly targeted member
        - selected_members
    """

    member = ensure_payment_member(request)


    if not member:

        return redirect(
            "members:dashboard"
        )


    now = timezone.now()


    # ==================================================
    # TARGETING
    # ==================================================

    targeted_requests = (
        Q(viewable_by_all=True)
        |
        Q(member=member)
        |
        Q(selected_members=member)
    )


    # ==================================================
    # REQUEST TYPE ACCESS
    # ==================================================

    if member.status == "approved":

        allowed_request_types = [
            "membership",
            "other",
        ]

    else:

        allowed_request_types = [
            "membership",
            "subscription",
            "claim",
            "other",
        ]


    # ==================================================
    # FETCH PAYMENT REQUESTS
    # ==================================================

    payment_requests = (
        PaymentRequest.objects
        .filter(
            targeted_requests,
            request_type__in=allowed_request_types,
            status=PaymentRequest.STATUS_ACTIVE,
        )
        .prefetch_related("payments")
        .distinct()
        .order_by("-created_at")
    )


    # ==================================================
    # COMPUTE MEMBER STATES
    # ==================================================

    for req in payment_requests:

        # ------------------------------------------------
        # MEMBER PAYMENTS FOR THIS REQUEST
        # ------------------------------------------------

        member_payments = [
            p
            for p in req.payments.all()
            if p.member_id == member.id
        ]


        # ------------------------------------------------
        # COMPLETED PAYMENT
        # ------------------------------------------------

        completed_payment_exists = any(
            p.status == Payment.STATUS_COMPLETED
            for p in member_payments
        )


        # ------------------------------------------------
        # PENDING PAYMENT
        # ------------------------------------------------

        pending_payment_exists = any(
            p.status == Payment.STATUS_PENDING
            for p in member_payments
        )


        # ------------------------------------------------
        # PAYMENT REQUEST AWAITING APPROVAL
        # ------------------------------------------------

        req.is_request_pending = (
            req.status == "pending"
        )


        # ------------------------------------------------
        # MEMBER PAYMENT PENDING CONFIRMATION
        # ------------------------------------------------

        req.is_payment_pending = (
            pending_payment_exists
        )


        # ------------------------------------------------
        # FULLY PAID
        # ------------------------------------------------

        req.is_paid = (
            completed_payment_exists
        )


        # ------------------------------------------------
        # MEMBER OVERDUE
        # ------------------------------------------------

        req.is_overdue_member = (

            not completed_payment_exists

            and req.due_date

            and req.due_date < now

            and not pending_payment_exists

        )


        # ------------------------------------------------
        # ENDING SOON
        # ------------------------------------------------

        req.is_ending_soon = (

            req.due_date

            and req.due_date > now

            and (req.due_date - now).days <= 2

        )


    # ==================================================
    # RENDER
    # ==================================================

    return render(
        request,
        "members/payments/members_payment_list.html",
        {
            "payment_requests":
                payment_requests,
        },
    )

# ======================================================
# PAYMENT REQUEST DETAIL
# ======================================================
@login_required
@member_required
def payment_request_detail(request, pk):
    """
    Display a payment request only if the current member
    is authorised to access it.

    This repeats the targeting check at the detail level
    so a member cannot bypass the payment-list security
    simply by changing the URL.
    """

    member = ensure_payment_member(request)


    if not member:

        return redirect(
            "members:dashboard"
        )


    payment_request = get_member_payment_request(
        member,
        pk,
    )


    return render(
        request,
        "members/payments/members_payment_request_detail.html",
        {
            "payment_request":
                payment_request,
        },
    )

# ======================================================
# PAY REQUEST ENTRY POINT
# ======================================================
@login_required
@member_required
def pay_payment_request(request, pk):
    """
    Entry point for paying a payment request.

    Approved members may enter this workflow only for:

        - Membership
        - Other

    Active members may enter for all applicable
    payment request types.

    The payment request is also checked against
    the member's targeting permissions.
    """

    member = ensure_payment_member(request)


    if not member:

        return redirect(
            "members:dashboard"
        )


    # ==================================================
    # AUTHORISED PAYMENT REQUEST
    # ==================================================

    payment_request = get_member_payment_request(
        member,
        pk,
    )


    # ==================================================
    # EXISTING PENDING PAYMENT
    # ==================================================

    existing_pending = Payment.objects.filter(
        payment_request=payment_request,
        member=member,
        status=Payment.STATUS_PENDING,
    ).exists()


    if existing_pending:

        messages.warning(
            request,
            "Your payment is awaiting confirmation."
        )

        return redirect(
            "members:member_payment_requests"
        )


    # ==================================================
    # COMPLETED
    # ==================================================

    if Payment.objects.filter(
        member=member,
        payment_request=payment_request,
        status=Payment.STATUS_COMPLETED,
    ).exists():

        messages.error(
            request,
            "You have already paid."
        )

        return redirect(
            "members:member_payment_requests"
        )


    # ==================================================
    # PENDING
    # ==================================================

    if Payment.objects.filter(
        member=member,
        payment_request=payment_request,
        status=Payment.STATUS_PENDING,
    ).exists():

        messages.warning(
            request,
            "Payment awaiting confirmation."
        )

        return redirect(
            "members:member_payment_requests"
        )


    # ==================================================
    # CLOSED / OVERDUE
    # ==================================================

    if (
        payment_request.status
        != PaymentRequest.STATUS_ACTIVE
        or payment_request.is_overdue
    ):

        messages.error(
            request,
            "This request is no longer payable."
        )

        return redirect(
            "members:member_payment_requests"
        )


    # ==================================================
    # CHECK PAYMENT METHOD
    # ==================================================

    return render(
        request,
        "members/payments/payment_checkout.html",
        {
            "payment_request":
                payment_request,
        },
    )

# ======================================================
# MANUAL PAYMENT
# ======================================================
@login_required
@member_required
def manual_payment_page(request, pk):
    """
    Display the manual payment page.

    Approved members may use this for Membership and
    Other payment requests.

    Subscription and Claim requests remain unavailable
    to Approved members because get_member_payment_request()
    enforces the request-type rule.
    """

    member = ensure_payment_member(request)


    if not member:

        return redirect(
            "members:dashboard"
        )


    payment_request = get_member_payment_request(
        member,
        pk,
    )


    # ==================================================
    # MEMBER PAYMENT STATUS
    # ==================================================

    status = payment_request.member_payment_status(
        member
    )


    if status == "paid":

        messages.error(
            request,
            "Already paid."
        )

        return redirect(
            "members:member_payment_requests"
        )


    if status == "pending":

        messages.warning(
            request,
            "Awaiting confirmation."
        )

        return redirect(
            "members:member_payment_requests"
        )


    # ==================================================
    # PAYMENT METHOD
    # ==================================================

    if (
        payment_request.payment_method
        == PaymentRequest.METHOD_CARD
    ):

        messages.error(
            request,
            "Must be paid by card."
        )

        return redirect(
            "members:member_payment_requests"
        )


    return render(
        request,
        "members/payments/members_manual_payment.html",
        {
            "payment_request":
                payment_request,
        },
    )

# ======================================================
# CONFIRM MANUAL PAYMENT
# ======================================================
@login_required
@member_required
def confirm_manual_payment(request, pk):
    """
    Submit proof for a manual payment.

    Approved members are permitted where the payment
    request itself is eligible for Approved status.
    """

    member = ensure_payment_member(request)


    if not member:

        return redirect(
            "members:dashboard"
        )


    payment_request = get_member_payment_request(
        member,
        pk,
    )


    # ==================================================
    # MEMBER PAYMENT STATUS
    # ==================================================

    status = payment_request.member_payment_status(
        member
    )


    if status in [
        "paid",
        "pending",
    ]:

        messages.warning(
            request,
            "Cannot process payment."
        )

        return redirect(
            "members:member_payment_requests"
        )


    # ==================================================
    # PAYMENT METHOD
    # ==================================================

    if (
        payment_request.payment_method
        == PaymentRequest.METHOD_CARD
    ):

        messages.error(
            request,
            "This request must be paid by card."
        )

        return redirect(
            "members:member_payment_requests"
        )


    # ==================================================
    # POST
    # ==================================================

    if request.method == "POST":

        proof = request.FILES.get(
            "proof"
        )


        payment = create_manual_payment(
            member,
            payment_request,
            proof,
        )


        AuditLog.objects.create(
            admin=request.user,
            action="payment_uploaded",
            payment=payment,
        )


        messages.success(
            request,
            "Submitted for approval."
        )


        return redirect(
            "members:member_payment_requests"
        )


    return redirect(
        "members:manual_payment_page",
        pk=pk,
    )

# ======================================================
# STRIPE CHECKOUT
# ======================================================
@login_required
@member_required
def create_stripe_checkout(request, pk):
    """
    Create a Stripe Checkout session.

    Approved members are allowed only for eligible
    payment request types.

    Active members retain the existing behaviour.
    """

    member = ensure_payment_member(request)


    if not member:

        return redirect(
            "members:dashboard"
        )


    payment_request = get_member_payment_request(
        member,
        pk,
    )


    # ==================================================
    # MEMBER PAYMENT STATUS
    # ==================================================

    status = payment_request.member_payment_status(
        member
    )


    if status in [
        "paid",
        "pending",
    ]:

        messages.warning(
            request,
            "Cannot process payment."
        )

        return redirect(
            "members:member_payment_requests"
        )


    # ==================================================
    # PAYMENT METHOD
    # ==================================================

    if payment_request.payment_method == (
        PaymentRequest.METHOD_MANUAL
    ):

        messages.error(
            request,
            "This request must be paid manually."
        )

        return redirect(
            "members:member_payment_requests"
        )


    # ==================================================
    # STRIPE CHECKOUT
    # ==================================================

    session = stripe.checkout.Session.create(

        payment_method_types=[
            "card"
        ],

        line_items=[

            {
                "price_data": {

                    "currency": "gbp",

                    "product_data": {
                        "name":
                            payment_request.title
                    },

                    "unit_amount":
                        int(
                            payment_request.amount * 100
                        ),

                },

                "quantity": 1,

            }

        ],

        mode="payment",

        success_url=request.build_absolute_uri(
            f"/payments/{payment_request.id}/success/"
        ),

        cancel_url=request.build_absolute_uri(
            "/members/payment-requests/"
        ),

    )


    return redirect(
        session.url
    )

# ======================================================
# STRIPE PAYMENT SUCCESS
# ======================================================
@login_required
@member_required
def stripe_payment_success(request, pk):
    """
    Handle successful Stripe payment return.

    The payment request is revalidated against the
    member before recording the payment.
    """

    member = ensure_payment_member(request)


    if not member:

        return redirect(
            "members:dashboard"
        )


    payment_request = get_member_payment_request(
        member,
        pk,
    )


    # ==================================================
    # PREVENT DUPLICATE PAYMENT
    # ==================================================

    if Payment.objects.filter(
        member=member,
        payment_request=payment_request,
        status=Payment.STATUS_COMPLETED,
    ).exists():

        messages.warning(
            request,
            "You have already paid."
        )

        return redirect(
            "members:member_payment_requests"
        )


    # ==================================================
    # RECORD PAYMENT
    # ==================================================

    record_payment(
        member,
        payment_request,
    )


    messages.success(
        request,
        "Payment successful."
    )


    return redirect(
        "members:member_payment_requests"
    )

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