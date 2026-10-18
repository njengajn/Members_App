# backend/members/views_admin/admin_payments.py
from django.db import transaction
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone

from backend.members.services.member_status_service import retire_member
from backend.members.services.payment_lifecycle import process_payment_lifecycle, get_pending_payment_approvals
from .admin_auth import admin_required
from backend.members.models import AuditLog, Member, PaymentRequest, Payment, Claim, MembershipStatusHistory
from django.contrib.admin.views.decorators import staff_member_required
from backend.members.services.claim_settlement_service import settle_claim
import csv
from django.http import HttpResponse
from datetime import date, timedelta
from django.core.paginator import Paginator
from django.db.models import Q, Count
from backend.members.services.payment_service import record_payment
from backend.members.services.business_rules import approve_claim
from backend.members.utils.payments import validate_due_date
from backend.members.decorators import admin_required
from django.utils.dateparse import parse_datetime
from backend.members.views_admin import admin_payments
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch

import matplotlib
matplotlib.use("Agg")  # required for server environments
import matplotlib.pyplot as plt
import io
from datetime import datetime
from reportlab.lib import colors
import csv
import matplotlib
matplotlib.use("Agg")
from collections import defaultdict
from reportlab.lib.pagesizes import letter, A4
from backend.members.services.notifications import (send_payment_request_notification)
from io import BytesIO
from django.contrib.staticfiles import finders

@admin_required
def admin_payments_list(request):
    """
    =====================================================
    ADMIN PAYMENT REQUESTS LIST
    =====================================================

    Shows:

    ✔ Active requests
    ✔ Overdue requests
    ✔ Closed requests
    ✔ Archived requests
    ✔ Pending counts
    ✔ Archive access

    BUSINESS RULES
    -----------------------------------------------------

    - Active requests are editable
    - Closed requests are locked
    - Archived requests are read-only
    - Archived requests are hidden from members
    =====================================================
    """

    # =================================================
    # ACTIVE TAB
    # =================================================

    tab = request.GET.get(
        "tab",
        "active"
    )

    now = timezone.now().date()

    # =================================================
    # BASE QUERYSET
    # =================================================

    base_queryset = PaymentRequest.objects.all()

    # =================================================
    # TAB FILTERING
    # =================================================

    if tab == "active":

        payment_requests = base_queryset.filter(
            status=PaymentRequest.STATUS_ACTIVE,
            due_date__gte=now
        )

    elif tab == "overdue":

        payment_requests = base_queryset.filter(
            status=PaymentRequest.STATUS_ACTIVE,
            due_date__lt=now
        )

    elif tab == "closed":

        payment_requests = base_queryset.filter(
            status=PaymentRequest.STATUS_CLOSED
        )

    elif tab == "archived":

        payment_requests = base_queryset.filter(
            status=PaymentRequest.STATUS_ARCHIVED
        )

    else:

        payment_requests = base_queryset.filter(
            status=PaymentRequest.STATUS_ACTIVE
        )

    # =================================================
    # ORDERING
    # =================================================

    payment_requests = payment_requests.order_by(
        "-created_at"
    )

    # =================================================
    # PENDING COUNTS
    # =================================================

    payment_requests = payment_requests.annotate(
        pending_count=Count(
            "payments",
            filter=Q(
                payments__status=Payment.STATUS_PENDING
            )
        )
    )

    # =================================================
    # GLOBAL COUNTS
    # =================================================

    counts = {

        "active": base_queryset.filter(
            status=PaymentRequest.STATUS_ACTIVE,
            due_date__gte=now
        ).count(),

        "overdue": base_queryset.filter(
            status=PaymentRequest.STATUS_ACTIVE,
            due_date__lt=now
        ).count(),

        "closed": base_queryset.filter(
            status=PaymentRequest.STATUS_CLOSED
        ).count(),

        "archived": base_queryset.filter(
            status=PaymentRequest.STATUS_ARCHIVED
        ).count(),
    }

    # =================================================
    # GLOBAL PENDING COUNT
    # =================================================

    pending_total = Payment.objects.filter(
        status=Payment.STATUS_PENDING
    ).count()

    # =================================================
    # TEMPLATE
    # =================================================

    return render(
        request,
        "members/admin/payments/admin_payments_list.html",
        {
            "payment_requests": payment_requests,
            "counts": counts,
            "pending_total": pending_total,
            "tab": tab,
        },
    )
  
@admin_required
def payment_request_detail(request, pk):
    """
    Detailed payment request view
    Shows:
    ✔ Paid members
    ✔ Unpaid members
    ✔ Compliance %
    """
    from backend.members.models import PaymentRequest, Member
    payment_request = PaymentRequest.objects.get(id=pk)

    # ---------------------------------------
    # DETERMINE TARGET MEMBERS
    # ---------------------------------------
    if payment_request.viewable_by_all:
        target_members = Member.objects.filter(status="active")
    else:
        target_members = payment_request.selected_members.all()

    paid_members = payment_request.paid_members.all()

    # ---------------------------------------
    # WHO HASN'T PAID
    # ---------------------------------------
    unpaid_members = target_members.exclude(
        id__in=paid_members.values_list("id", flat=True)
    )

    # ---------------------------------------
    # COMPLIANCE %
    # ---------------------------------------
    total = target_members.count()
    paid = paid_members.count()

    compliance = 0
    if total > 0:
        compliance = int((paid / total) * 100)

    context = {
        "request": payment_request,
        "paid_members": paid_members,
        "unpaid_members": unpaid_members,
        "compliance": compliance,
        "total": total,
        "paid": paid,
    }

    return render(
        request,
        "members/admin/payments/payment_request_detail.html",
        context,
    )


# ==========================
# LIST ALL PAYMENT REQUESTS
# ==========================

@admin_required
def admin_payment_requests(request):
    payment_requests = PaymentRequest.objects.all().order_by("-id")

    return render(
        request,
        "members/admin/payment_requests.html",
        {"payment_requests": payment_requests},
    )


# ==========================
# VIEW SINGLE PAYMENT REQUEST
# ==========================

@admin_required
def admin_view_payment_request(request, pk):
    payment_request = get_object_or_404(PaymentRequest, pk=pk)
    payments = Payment.objects.filter(payment_request=payment_request)

    return render(
        request,
        "members/admin/admin_payment_request_detail.html",
        {
            "payment_request": payment_request,
            "payments": payments,
        },
    )
    
# ======================================================
# PAYMENT REQUEST MEMBER ELIGIBILITY
# ======================================================
def get_payment_request_members(request_type):
    """
    Return the members who may be targeted by a
    payment request of the supplied type.

    BUSINESS RULES
    --------------

    Membership:
        Approved + Active

    Other:
        Approved + Active

    Subscription:
        Active only

    Claim Settlement:
        Active only

    Pending:
        Never eligible for a new payment request.

    Retired:
        Never eligible for a new payment request.

    IMPORTANT
    ---------
    Approved is intentionally NOT treated as Active
    throughout the application.

    Approved is only included here for payment-request
    types that an approved applicant is allowed to pay.
    """

    if request_type in [
        "membership",
        "other",
    ]:

        allowed_statuses = [
            Member.STATUS_APPROVED,
            Member.STATUS_ACTIVE,
        ]

    elif request_type in [
        "subscription",
        "claim",
    ]:

        allowed_statuses = [
            Member.STATUS_ACTIVE,
        ]

    else:

        # Invalid request type = no eligible members.
        allowed_statuses = []

    return Member.objects.filter(
        status__in=allowed_statuses
    ).order_by(
        "first_name",
        "surname",
    )

# ======================================================
# CREATE PAYMENT REQUEST
# ======================================================
@admin_required
def create_payment_request(request):
    """
    =====================================================
    CREATE PAYMENT REQUEST
    =====================================================

    TARGETING

        - All Members
        - Single Member
        - Selected Members

    PAYMENT REQUEST TYPES

        Membership:
            Approved + Active

        Other:
            Approved + Active

        Subscription:
            Active only

        Claim Settlement:
            Active only

    IMPORTANT

        Approved members are included ONLY where
        the payment request type permits it.

        Approved does NOT mean Active.

        Pending and Retired members cannot be
        targeted for new payment requests.

    TARGET VALIDATION

        The queryset is used for BOTH:

            1. displaying eligible members
            2. validating submitted member IDs

        This prevents a manipulated POST request from
        bypassing the status rules.

    PAYMENT REQUEST LIFECYCLE

        ACTIVE -> CLOSED -> ARCHIVED

    Notifications may be enabled or disabled
    per request.
    =====================================================
    """

    # =================================================
    # REQUEST TYPE FOR PAGE DISPLAY
    # =================================================
    #
    # On GET:
    #     This controls which members are displayed.
    #
    # Default:
    #     "other" because that was the existing default
    #     in the template.
    #
    # On POST:
    #     The actual submitted request_type is validated
    #     again below.
    # =================================================

    page_request_type = request.GET.get(
        "request_type",
        "other",
    )


    if page_request_type not in [
        "membership",
        "subscription",
        "claim",
        "other",
    ]:

        page_request_type = "other"


    # =================================================
    # PAGE DATA
    # =================================================

    members = get_payment_request_members(
        page_request_type
    )


    approved_claims = Claim.objects.filter(
        status=Claim.STATUS_APPROVED
    )


    # =================================================
    # FORM SUBMISSION
    # =================================================

    if request.method == "POST":

        try:

            # =========================================
            # REQUEST TYPE
            # =========================================

            request_type = request.POST.get(
                "request_type"
            )


            if request_type not in [
                "membership",
                "subscription",
                "claim",
                "other",
            ]:

                raise ValueError(
                    "Invalid payment request type."
                )


            # =========================================
            # ELIGIBLE MEMBERS FOR THIS REQUEST TYPE
            # =========================================
            #
            # IMPORTANT:
            # This queryset is the authoritative source
            # for target validation.
            # =========================================

            eligible_members = (
                get_payment_request_members(
                    request_type
                )
            )


            # =========================================
            # TARGETING
            # =========================================

            target_mode = request.POST.get(
                "target_mode",
                "all",
            )


            member_id = request.POST.get(
                "member"
            )


            selected_members_ids = (
                request.POST.getlist(
                    "selected_members"
                )
            )


            # =========================================
            # TITLE
            # =========================================

            title = request.POST.get(
                "title",
                ""
            ).strip()


            if not title:

                raise ValueError(
                    "Title is required."
                )


            # =========================================
            # DESCRIPTION
            # =========================================

            description = request.POST.get(
                "description",
                ""
            ).strip()


            # =========================================
            # NOTIFICATIONS
            # =========================================

            send_notifications = (
                request.POST.get(
                    "send_notifications"
                ) == "on"
            )


            # =========================================
            # PAYMENT METHOD
            # =========================================

            payment_method = request.POST.get(
                "payment_method"
            )


            if not payment_method:

                raise ValueError(
                    "Payment method is required."
                )


            if payment_method not in [
                "manual",
                "card",
                "both",
            ]:

                raise ValueError(
                    "Invalid payment method selected."
                )


            # =========================================
            # DUE DATE
            # =========================================

            due_date = validate_due_date(
                request.POST.get(
                    "due_date"
                )
            )


            # =========================================
            # CLAIM
            # =========================================

            claim_id = request.POST.get(
                "claim"
            )


            # =========================================
            # AMOUNT
            # =========================================

            amount = request.POST.get(
                "amount"
            )


            if not amount:

                raise ValueError(
                    "Amount is required."
                )


            try:

                amount = float(amount)

            except Exception:

                raise ValueError(
                    "Amount must be numeric."
                )


            if amount <= 0:

                raise ValueError(
                    "Amount must be greater than zero."
                )


            # =========================================
            # TARGET VALIDATION
            # =========================================
            #
            # SINGLE
            # -------
            # The selected member MUST belong to the
            # request-type-specific eligible queryset.
            #
            # SELECTED
            # --------
            # EVERY submitted member ID MUST belong to
            # the eligible queryset.
            #
            # ALL
            # ---
            # The eligible queryset itself becomes the
            # target population.
            # =========================================

            if target_mode == "single":

                if not member_id:

                    raise ValueError(
                        "Please select a member."
                    )


                if selected_members_ids:

                    raise ValueError(
                        "Single member mode cannot use "
                        "selected members."
                    )


                try:

                    selected_member = (
                        eligible_members.get(
                            id=member_id
                        )
                    )

                except Member.DoesNotExist:

                    raise ValueError(
                        "The selected member is not "
                        "eligible for this type of "
                        "payment request."
                    )


            elif target_mode == "selected":

                if member_id:

                    raise ValueError(
                        "Selected members mode cannot "
                        "use single member."
                    )


                if not selected_members_ids:

                    raise ValueError(
                        "Please select at least one member."
                    )


                # -------------------------------------
                # Remove duplicate IDs from the POST.
                # -------------------------------------

                selected_members_ids = list(
                    dict.fromkeys(
                        selected_members_ids
                    )
                )


                # -------------------------------------
                # Validate EVERY selected member.
                # -------------------------------------

                eligible_selected_count = (
                    eligible_members.filter(
                        id__in=selected_members_ids
                    ).count()
                )


                if (
                    eligible_selected_count
                    != len(selected_members_ids)
                ):

                    raise ValueError(
                        "One or more selected members "
                        "are not eligible for this type "
                        "of payment request."
                    )


            elif target_mode == "all":

                pass


            else:

                raise ValueError(
                    "Invalid target mode."
                )


            # =========================================
            # CLAIM SETTLEMENT
            # =========================================

            claim = None


            if claim_id:

                # A claim payment request should only
                # be used with a Claim Settlement request.
                if request_type != "claim":

                    raise ValueError(
                        "A claim can only be used with "
                        "a Claim Settlement payment request."
                    )


                claim = get_object_or_404(
                    Claim,
                    id=claim_id
                )


                # -------------------------------------
                # Claim must be approved.
                # -------------------------------------

                if claim.status != Claim.STATUS_APPROVED:

                    raise ValueError(
                        "Only approved claims can have "
                        "a Claim Settlement payment request."
                    )


                existing_request = (
                    PaymentRequest.objects.filter(
                        claim=claim,
                        status__in=[
                            PaymentRequest.STATUS_ACTIVE,
                            PaymentRequest.STATUS_CLOSED,
                        ]
                    ).exists()
                )


                if existing_request:

                    raise ValueError(
                        "A payment request already exists "
                        "for this claim."
                    )


                # -------------------------------------
                # The claim member must be Active.
                #
                # Claim payment requests do not allow
                # Approved-only members.
                # -------------------------------------

                if (
                    claim.member is None
                    or
                    claim.member.status
                    != Member.STATUS_ACTIVE
                ):

                    raise ValueError(
                        "The member associated with this "
                        "claim must be Active."
                    )


            # =========================================
            # TARGET CONFIGURATION
            # =========================================

            member = None

            viewable_by_all = False


            if target_mode == "all":

                viewable_by_all = True


            elif target_mode == "single":

                # Use the already validated object.
                member = selected_member


            # =========================================
            # CREATE PAYMENT REQUEST
            # =========================================

            payment_request = (
                PaymentRequest.objects.create(

                    title=title,

                    description=description,

                    request_type=request_type,

                    claim=claim,

                    member=member,

                    amount=amount,

                    due_date=due_date,

                    payment_method=payment_method,

                    send_notifications=send_notifications,

                    status=PaymentRequest.STATUS_ACTIVE,

                    viewable_by_all=viewable_by_all,

                )
            )


            # =========================================
            # SELECTED MEMBERS
            # =========================================

            if selected_members_ids:

                payment_request.selected_members.set(
                    selected_members_ids
                )


            # =========================================
            # DETERMINE RECIPIENTS
            # =========================================
            #
            # Use the SAME eligible queryset that was
            # used to validate the request.
            #
            # This prevents notifications being sent
            # to members who should not receive this
            # type of request.
            # =========================================

            target_members = []


            if target_mode == "all":

                target_members = eligible_members


            elif target_mode == "single":

                target_members = [
                    member
                ]

            elif target_mode == "selected":

                target_members = (
                    payment_request
                    .selected_members
                    .all()
                )


            # =========================================
            # SNAPSHOT TARGET POPULATION
            # =========================================
            # Preserve the members targeted when this
            # payment request was created.
            # =========================================

            payment_request.targeted_members.set(
                target_members
            )


            # =========================================
            # SEND NOTIFICATIONS
            # =========================================


            if payment_request.send_notifications:

                for target_member in target_members:

                    send_payment_request_notification(
                        target_member,
                        payment_request
                    )


            # =========================================
            # SUCCESS
            # =========================================

            messages.success(
                request,
                "Payment request created successfully."
            )


            return redirect(
                "members_admin:admin_payments_list"
            )


        except Member.DoesNotExist:

            messages.error(
                request,
                "Selected member does not exist."
            )


        except Exception as e:

            messages.error(
                request,
                str(e)
            )


    # =================================================
    # INITIAL PAGE LOAD
    # =================================================

    return render(
        request,
        "members/admin/payments/admin_create_payment_request.html",
        {
            "members": members,

            "approved_claims":
                approved_claims,

            "today":
                timezone.now(),

            "selected_request_type":
                page_request_type,
        },
    )

@admin_required
def payment_request_paid_members(request, pk):
    """
    Show members who paid a request.
    """

    payment_request = get_object_or_404(PaymentRequest, id=pk)

    payments = Payment.objects.filter(
        payment_request=payment_request
    ).select_related("member")

    return render(
        request,
        "members/admin/payments/admin_payment_paid_members.html",
        {
            "payment_request": payment_request,
            "payments": payments,
        },
    )

@admin_required
@transaction.atomic
def update_payment_request_status(request, request_id):
    """
    Explicitly update the status of ONE payment request.

    BUSINESS RULES
    ---------------------------------------------------------
    1. Closing affects only this request.
    2. Pending payment approvals block closure.
    3. The administrator performing the close is recorded.
    4. Closing does not trigger retirement.
    5. Reconciliation is a separate operation.
    6. The administrator who closes the request may reconcile it.
    """

    payment_request = get_object_or_404(
        PaymentRequest.objects.select_for_update(),
        id=request_id,
    )

    if request.method != "POST":
        return redirect(
            "members_admin:admin_payments_list",
        )

    new_status = request.POST.get("status")

    if new_status not in [
        PaymentRequest.STATUS_ACTIVE,
        PaymentRequest.STATUS_CLOSED,
    ]:
        messages.error(
            request,
            "Invalid payment request status.",
        )
        return redirect(
            "members_admin:admin_payment_detail",
            payment_request.id,
        )

    # =====================================================
    # CLOSE
    # =====================================================

    if new_status == PaymentRequest.STATUS_CLOSED:

        if payment_request.status == PaymentRequest.STATUS_CLOSED:
            messages.info(
                request,
                "Payment request is already closed.",
            )
            return redirect(
                "members_admin:admin_payment_detail",
                payment_request.id,
            )

        if payment_request.status == PaymentRequest.STATUS_ARCHIVED:
            messages.error(
                request,
                "An archived payment request cannot be closed.",
            )
            return redirect(
                "members_admin:admin_payment_detail",
                payment_request.id,
            )

        # -------------------------------------------------
        # BLOCK CLOSURE WHILE PAYMENT APPROVALS ARE PENDING
        # -------------------------------------------------

        if get_pending_payment_approvals(payment_request).exists():
            messages.warning(
                request,
                (
                    "This payment request cannot be closed while "
                    "payments are awaiting approval. Please approve "
                    "or reject the pending payments for this request "
                    "before closing it."
                ),
            )

            # Redirect to the pending approvals page, identifying
            # the specific payment request that is blocking closure.
            return redirect(
                f"{reverse('members_admin:pending_payments')}"
                f"?payment_request_id={payment_request.id}"
            )

        # -------------------------------------------------
        # CLOSE ONLY THIS REQUEST
        # -------------------------------------------------
        #
        # process_payment_lifecycle() must now perform closure only.
        # It must not retire members or process unrelated requests.
        # -------------------------------------------------

        results = process_payment_lifecycle(
            request_id=payment_request.id,
            performed_by=request.user,
        )

        # Check the service result rather than claiming success
        # if the request was not actually closed.
        result = next(
            (
                item
                for item in results
                if item["request_id"] == payment_request.id
            ),
            None,
        )

        payment_request.refresh_from_db()

        if (
            result
            and result.get("status") == "pending_approvals"
        ) or get_pending_payment_approvals(payment_request).exists():
            messages.warning(
                request,
                (
                    "This request cannot be closed while payment "
                    "approvals are pending. Please resolve them first."
                ),
            )
            return redirect(
                "members_admin:admin_payment_detail",
                payment_request.id,
            )

        if payment_request.status == PaymentRequest.STATUS_CLOSED:
            messages.success(
                request,
                "Payment request closed successfully.",
            )
        else:
            messages.error(
                request,
                "The payment request was not closed. Please try again.",
            )

    # =====================================================
    # REOPEN
    # =====================================================

    elif new_status == PaymentRequest.STATUS_ACTIVE:

        if payment_request.status == PaymentRequest.STATUS_ACTIVE:
            messages.info(
                request,
                "Payment request is already active.",
            )
            return redirect(
                "members_admin:admin_payment_detail",
                payment_request.id,
            )

        payment_request.status = PaymentRequest.STATUS_ACTIVE

        # A reopened request is no longer currently closed.
        # Clear the current closing actor and timestamp.
        payment_request.closed_by = None
        payment_request.closed_at = None

        payment_request.save(
            update_fields=[
                "status",
                "closed_by",
                "closed_at",
                "updated_at",
            ],
        )

        messages.success(
            request,
            "Payment request reopened successfully.",
        )

    return redirect(
        "members_admin:admin_payment_detail",
        payment_request.id,
    )

@admin_required
def payment_compliance_tracker(request, pk):
    """
    Display payment compliance against the historical target-member snapshot.

    Never reconstruct the original target population from current member
    statuses. If the saved snapshot is missing, compliance is unverified.
    """
    payment_request = get_object_or_404(PaymentRequest, pk=pk)

    today = timezone.localdate()
    due_date = payment_request.due_date

    if due_date and hasattr(due_date, "date"):
        due_date = due_date.date()

    is_overdue = bool(due_date and due_date < today)

    # The saved target group is the source of truth for historical reporting.
    target_ids = list(
        payment_request.targeted_members.values_list("pk", flat=True)
    )
    target_snapshot_missing = not target_ids

    # Pending approvals remain visible and are not counted as completed payments.
    pending_payments = get_pending_payment_approvals(
        payment_request
    ).select_related("member").order_by("created_at", "pk")

    # Only completed payments belonging to this request count as paid.
    completed_payments = Payment.objects.filter(
        payment_request=payment_request,
        status=Payment.STATUS_COMPLETED,
    ).exclude(member_id__isnull=True)

    if target_snapshot_missing:
        # Show payment evidence, but do not invent the historical denominator.
        paid_member_ids = set(
            completed_payments.values_list("member_id", flat=True)
        )

        paid_members = Member.objects.filter(
            pk__in=paid_member_ids
        ).order_by("first_name", "surname", "pk")

        unpaid_members = Member.objects.none()

        total_required = None
        total_paid = paid_members.count()
        total_unpaid = None
        compliance = None
        compliance_verified = False

    else:
        required_members = Member.objects.filter(
            pk__in=target_ids
        ).order_by("first_name", "surname", "pk")

        paid_member_ids = set(
            completed_payments.filter(
                member_id__in=target_ids
            ).values_list("member_id", flat=True)
        )

        paid_members = required_members.filter(
            pk__in=paid_member_ids
        )

        unpaid_members = required_members.exclude(
            pk__in=paid_member_ids
        )

        total_required = required_members.count()
        total_paid = paid_members.count()
        total_unpaid = total_required - total_paid

        # A non-empty saved snapshot is required to verify compliance.
        compliance_verified = total_required > 0
        compliance = (
            round((total_paid / total_required) * 100)
            if compliance_verified
            else None
        )

    context = {
        "payment_request": payment_request,
        "paid_members": paid_members,
        "unpaid_members": unpaid_members,
        "pending_payments": pending_payments,
        "total_required": total_required,
        "total_paid": total_paid,
        "total_unpaid": total_unpaid,
        "compliance": compliance,
        "compliance_verified": compliance_verified,
        "target_snapshot_missing": target_snapshot_missing,
        "is_overdue": is_overdue,
    }

    return render(
        request,
        "members/admin/payments/admin_payment_request_detail.html",
        context,
    )

@admin_required
def verify_payment(request, payment_id):
    """
    Approve manual payment
    """
    payment = get_object_or_404(Payment, id=payment_id)

    payment.status = Payment.STATUS_COMPLETED
    payment.reviewed_by = request.user
    payment.reviewed_at = timezone.now()
    payment.save()

    AuditLog.objects.create(
        admin=request.user,
        action="payment_approved",
        payment=payment,
        message="Payment approved by admin"
    )

    messages.success(request, "Payment verified.")

    return redirect("members_admin:payments_awaiting_confirmation")



@admin_required
def reject_payment(request, pk):
    payment = get_object_or_404(Payment, id=pk)

    payment.status = Payment.STATUS_REJECTED
    payment.save()

    AuditLog.objects.create(
        admin=request.user,
        action="payment_rejected",
        payment=payment,
        message=f"Payment rejected by {request.user}"
    )

    messages.error(request, "Payment rejected.")

    return redirect("members_admin:pending_payments")


def settle_claim_payment(request, payment_request_id):
    """
    Treasurer confirms claim payment.

    Automatically applies retirement rules.
    """

    payment_request = PaymentRequest.objects.get(
        id=payment_request_id
    )

    claim = payment_request.claim

    if not claim:
        return redirect(
            "members_admin:admin_payments_list"
        )

    # -----------------------------------
    # MARK CLAIM SETTLED
    # -----------------------------------

    claim.status = "settled"
    claim.save()

    payment_request.status = "closed"
    payment_request.save()

    member = claim.member

    # -----------------------------------
    # CLAIM AGAINST DEPENDANT
    # -----------------------------------

    if claim.causer_dependant:

        dependant = claim.causer_dependant

        dependant.status = "retired"
        dependant.save()

    # -----------------------------------
    # CLAIM AGAINST MEMBER
    # -----------------------------------

    else:

        retire_member(
            member=member,
            reason=f"Claim settled (Claim #{claim.id})",
            performed_by=request.user,
        )

    return redirect(
        "members_admin:admin_claims_list"
    )


@admin_required
def confirm_claim_payment(request, pk):
    """
    Treasurer confirms payment for claim-based request

    ✔ creates payment
    ✔ marks member paid
    ✔ optionally closes request
    """

    payment_request = get_object_or_404(
        PaymentRequest,
        id=pk
    )

    if payment_request.status != PaymentRequest.STATUS_ACTIVE:
        messages.warning(request, "Payment request already closed.")
        return redirect("members_admin:admin_payments_list")

    # ---------------------------------------
    # CLAIM REQUEST → ALL MEMBERS
    # ---------------------------------------
    if payment_request.viewable_by_all:
        messages.warning(request, "Use individual payment approval.")
        return redirect("members_admin:payments_awaiting_confirmation")

    member = payment_request.member

    record_payment(member, payment_request, method="manual")

    messages.success(request, "Claim payment confirmed.")

    return redirect("members_admin:admin_payments_list")

# ======================================================
# EXPORT PAYMENT MEMBERS (CSV)
# ======================================================

@admin_required
def export_payment_members(request, pk):
    """
    Export the payment report for one payment request.

    PRESERVED
    ---------------------------------------------------------
    - Existing CSV structure and filename.
    - Request ID, member UID, member name, amount, status,
      and payment date.
    - Paid and pending totals.
    - Existing payment-date fallback logic.

    HISTORICAL POPULATION RULES
    ---------------------------------------------------------
    - Prefer the saved targeted_members snapshot.
    - Retain members who have since retired.
    - If the snapshot is missing, recover only from records
      associated with this request.
    - Clearly identify a recovered population as unverified.
    - Never substitute today's active members for historical
      targets.

    This export does not modify payments, reconcile the
    request, or trigger member retirement.
    """

    payment_request = get_object_or_404(
        PaymentRequest,
        pk=pk,
    )

    response = HttpResponse(
        content_type="text/csv; charset=utf-8",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="payment_report_{payment_request.id}.csv"'
    )

    writer = csv.writer(response)

    # ---------------------------------------------------------
    # TITLE AND REPORT GENERATION TIME
    # ---------------------------------------------------------
    writer.writerow([
        f"Payment Report: "
        f"{payment_request.title or payment_request.request_type}"
    ])
    writer.writerow([
        "Report Generated",
        timezone.localtime(timezone.now()).strftime(
            "%d/%m/%Y %H:%M:%S"
        ),
    ])
    writer.writerow([])

    # ---------------------------------------------------------
    # DETERMINE THE HISTORICAL TARGET POPULATION
    # ---------------------------------------------------------
    member_ids = set(
        payment_request.targeted_members.values_list(
            "id",
            flat=True,
        )
    )
    target_snapshot_exists = bool(member_ids)

    # Legacy requests may not have a saved target snapshot.
    # Recover only members supported by request-specific records.
    # This does not prove the original target population is complete.
    if not target_snapshot_exists:
        member_ids.update(
            payment_request.paid_members.values_list(
                "id",
                flat=True,
            )
        )
        member_ids.update(
            payment_request.unpaid_members.values_list(
                "id",
                flat=True,
            )
        )
        member_ids.update(
            payment_request.selected_members.values_list(
                "id",
                flat=True,
            )
        )
        member_ids.update(
            Payment.objects.filter(
                payment_request=payment_request,
                status=Payment.STATUS_COMPLETED,
                member__isnull=False,
            ).values_list(
                "member_id",
                flat=True,
            )
        )

    members = Member.objects.filter(
        id__in=member_ids,
    ).order_by(
        "member_uid",
        "id",
    )

    # ---------------------------------------------------------
    # SUMMARY COUNTS
    # ---------------------------------------------------------
    if target_snapshot_exists:
        target_count = len(
            set(
                payment_request.targeted_members.values_list(
                    "id",
                    flat=True,
                )
            )
        )

        paid_count = Payment.objects.filter(
            payment_request=payment_request,
            status=Payment.STATUS_COMPLETED,
            member_id__in=member_ids,
        ).values(
            "member_id",
        ).distinct().count()

        unpaid_count = max(
            0,
            target_count - paid_count,
        )

        writer.writerow(["Target Members", target_count])
        writer.writerow(["Paid Members", paid_count])
        writer.writerow(["Unpaid Members", unpaid_count])
    else:
        paid_count = Payment.objects.filter(
            payment_request=payment_request,
            status=Payment.STATUS_COMPLETED,
            member__isnull=False,
        ).values(
            "member_id",
        ).distinct().count()

        writer.writerow([
            "Target Members",
            "UNVERIFIED",
        ])
        writer.writerow([
            "Paid Members (identified payment evidence)",
            paid_count,
        ])
        writer.writerow([
            "Unpaid Members",
            "UNVERIFIED",
        ])
        writer.writerow([
            "Population Status",
            "UNVERIFIED - historical target snapshot missing",
        ])

    writer.writerow([])

    # ---------------------------------------------------------
    # HEADERS - KEEP THE EXISTING COLUMN STRUCTURE
    # ---------------------------------------------------------
    writer.writerow([
        "Request ID",
        "Member UID",
        "Member Name",
        "Amount",
        "Status",
        "Payment Date",
    ])

    # Warn inside the exported file when the original population
    # cannot be verified.
    if not target_snapshot_exists:
        writer.writerow([
            payment_request.id,
            "",
            "WARNING: historical target snapshot missing",
            "",
            "UNVERIFIED POPULATION",
            "",
        ])

    # ---------------------------------------------------------
    # TOTALS
    # ---------------------------------------------------------
    total_paid = 0.0
    total_pending = 0.0

    # ---------------------------------------------------------
    # EXPORT EACH IDENTIFIED MEMBER
    # ---------------------------------------------------------
    for member in members:
        payment = Payment.objects.filter(
            member=member,
            payment_request=payment_request,
            status=Payment.STATUS_COMPLETED,
        ).order_by(
            "-id",
        ).first()

        if payment:
            status = "paid"
            amount = payment.amount or 0

            payment_date = (
                payment.approved_at
                or payment.paid_at
                or payment.created_at
            )

            date = (
                timezone.localtime(payment_date).strftime(
                    "%d/%m/%Y %H:%M"
                )
                if payment_date
                else "N/A"
            )

            total_paid += float(amount)

        else:
            status = "pending"
            amount = 0.00
            date = ""

            total_pending += float(
                payment_request.amount or 0
            )

        # A recovered population must not be mistaken for a
        # verified historical compliance report.
        if not target_snapshot_exists:
            status = f"{status} - UNVERIFIED POPULATION"

        writer.writerow([
            payment_request.id,
            member.member_uid or "",
            f"{member.first_name} {member.surname}".strip(),
            f"{amount:.2f}",
            status,
            date,
        ])

    # ---------------------------------------------------------
    # TOTALS ROWS
    # ---------------------------------------------------------
    writer.writerow([])

    writer.writerow([
        "",
        "",
        "TOTAL PAID",
        f"{total_paid:.2f}",
        "",
        "",
    ])

    writer.writerow([
        "",
        "",
        "TOTAL PENDING",
        f"{total_pending:.2f}",
        "",
        "",
    ])

    return response

@admin_required
def approve_claim_view(request, claim_id):

    claim = Claim.objects.get(id=claim_id)

    approve_claim(claim)

    return redirect("members_admin:claims")


@admin_required
def admin_mark_payment_paid(request, request_id, member_id):
    """
    Admin manually marks a member as paid.

    FIXES:
    ✔ creates real Payment record
    ✔ prevents duplicate payments
    ✔ updates paid_members automatically via signal
    ✔ integrates with compliance tracking
    """

    payment_request = get_object_or_404(PaymentRequest, id=request_id)
    member = get_object_or_404(Member, id=member_id)

    # ---------------------------------------------------
    # PREVENT DUPLICATE PAYMENT
    # ---------------------------------------------------
    existing = payment_request.payments.filter(
        member=member
    ).exists()

    if existing:
        messages.warning(request, "Member already marked as paid.")
        return redirect(
            "members_admin:payment_request_detail",
            request_id
        )

    try:
        # ---------------------------------------------------
        # CREATE PAYMENT USING SERVICE (IMPORTANT)
        # ---------------------------------------------------
        record_payment(member, payment_request)

        messages.success(request, "Payment recorded successfully.")

    except Exception as e:
        messages.error(request, str(e))

    return redirect(
        "members_admin:payment_request_detail",
        request_id
    )

@admin_required
def update_payment_request(request, pk):
    """
    =====================================================
    ADMIN EDIT PAYMENT REQUEST
    =====================================================

    Allows editing of:

    ✔ Type
    ✔ Title
    ✔ Description
    ✔ Amount
    ✔ Due date
    ✔ Target member(s)

    TARGET OPTIONS
    -----------------------------------------------------

    ✔ All members
    ✔ Selected members
    ✔ Single member

    IMPORTANT BUSINESS RULES
    -----------------------------------------------------

    - ACTIVE requests can be edited
    - CLOSED requests are read-only
    - ARCHIVED requests are read-only

    This protects:

    ✔ finance history
    ✔ reconciliations
    ✔ reports
    ✔ audit integrity
    =====================================================
    """

    # =================================================
    # GET PAYMENT REQUEST
    # =================================================

    payment_request = get_object_or_404(
        PaymentRequest,
        id=pk
    )

    # =================================================
    # PREVENT EDITING CLOSED/ARCHIVED REQUESTS
    # =================================================

    if payment_request.status in [
        PaymentRequest.STATUS_CLOSED,
        PaymentRequest.STATUS_ARCHIVED,
    ]:

        messages.warning(
            request,
            (
                "This payment request is closed "
                "and cannot be changed."
            )
        )

        return redirect(
            "members_admin:payment_request_detail",
            pk=payment_request.pk
        )

    # =================================================
    # ACTIVE MEMBERS
    # =================================================

    members = Member.objects.filter(
        status=Member.STATUS_ACTIVE
    ).order_by(
        "first_name",
        "surname"
    )

    # =================================================
    # PROCESS FORM
    # =================================================

    if request.method == "POST":

        # =============================================
        # BASIC FIELDS
        # =============================================

        payment_request.request_type = request.POST.get(
            "request_type",
            payment_request.request_type
        )

        payment_request.title = request.POST.get(
            "title",
            ""
        ).strip()

        payment_request.description = request.POST.get(
            "description",
            ""
        ).strip()

        payment_request.amount = request.POST.get(
            "amount",
            payment_request.amount
        )

        # =============================================
        # DUE DATE
        # =============================================

        due_date_raw = request.POST.get(
            "due_date"
        )

        if due_date_raw:

            parsed_due_date = parse_datetime(
                due_date_raw
            )

            if parsed_due_date:
                payment_request.due_date = parsed_due_date

        # =============================================
        # TARGET MEMBERS
        # =============================================

        target_type = request.POST.get(
            "target_type"
        )

        # Reset targeting
        payment_request.viewable_by_all = False
        payment_request.member = None

        payment_request.save()

        payment_request.selected_members.clear()

        # ---------------------------------------------
        # ALL MEMBERS
        # ---------------------------------------------

        if target_type == "all":

            payment_request.viewable_by_all = True

        # ---------------------------------------------
        # SINGLE MEMBER
        # ---------------------------------------------

        elif target_type == "single":

            member_id = request.POST.get(
                "member"
            )

            if member_id:

                try:

                    payment_request.member = (
                        Member.objects.get(
                            id=member_id
                        )
                    )

                except Member.DoesNotExist:

                    messages.error(
                        request,
                        "Selected member does not exist."
                    )

                    return redirect(
                        "members_admin:update_payment_request",
                        pk=payment_request.id
                    )

        # ---------------------------------------------
        # SELECTED MEMBERS
        # ---------------------------------------------

        elif target_type == "selected":

            selected_ids = request.POST.getlist(
                "selected_members"
            )

            selected_members = Member.objects.filter(
                id__in=selected_ids,
                status=Member.STATUS_ACTIVE
            )

            payment_request.save()

            payment_request.selected_members.set(
                selected_members
            )

        # =============================================
        # SAVE
        # =============================================

        payment_request.save()

        messages.success(
            request,
            "Payment request updated successfully."
        )

        return redirect(
            "members_admin:admin_payments_list"
        )

    # =================================================
    # TEMPLATE
    # =================================================

    return render(
        request,
        "members/admin/payments/admin_update_payment_request.html",
        {
            "payment_request": payment_request,
            "members": members,
        }
    )

@admin_required
def approve_payment(request, pk):
    payment = get_object_or_404(Payment, id=pk)

    payment.status = Payment.STATUS_COMPLETED
    payment.approved_by = request.user
    payment.approved_at = timezone.now()
    payment.save()

    # mark as paid
    # remove from request list
    if payment.payment_request:
        payment.payment_request.paid_members.add(payment.member)
   
    AuditLog.objects.create(
        admin=request.user,
        action="payment_approved",
        payment=payment,
        message=f"Payment approved by {request.user}"
    )

    messages.success(request, "Payment approved successfully.")

    return redirect("members_admin:pending_payments")

#------------------
#ADMIN LIST — PAYMENTS AWAITING CONFIRMATION
# ------------------------------------------

@admin_required
def payments_awaiting_confirmation(request):
    """
    List ALL manual payments awaiting admin confirmation

    FIXES:
    ✔ used by admin dashboard
    ✔ shows only pending payments
    ✔ correct page instead of payment requests list
    """

    payments = Payment.objects.select_related(
        "member",
        "payment_request"
    ).filter(
        status=Payment.STATUS_PENDING  # ✅ ONLY pending
    ).order_by("-paid_at")

    return render(
        request,
        "members/admin/payments/admin_pending_payments.html",
        {
            "payments": payments
        },
    )
    
    
@admin_required
def admin_pending_payments(request):
    """
    Show all manual payments awaiting admin confirmation
    """
    payments = Payment.objects.filter(
        status="pending",
       
        payment_method="manual"  
    ).select_related("member", "payment_request")

    return render(
        request,
        "members/admin/payments/admin_pending_payments.html",
        {"payments": payments},
    )
    
    
@admin_required
def confirm_manual_payment(request, pk):
    """
    Confirm manual payment (bank transfer)
    ✔ Creates payment with PENDING status
    ✔ Uploads proof
    ✔ Adds audit log
    """

    member = request.user.member
    payment_request = get_object_or_404(PaymentRequest, id=pk)

    if request.method == "POST":
        proof = request.FILES.get("proof")

        try:
            # ---------------------------------------
            # CREATE PAYMENT (MUST BE PENDING)
            # ---------------------------------------
            payment = Payment.objects.create(

            member=member,

            payment_request=payment_request,

            amount=payment_request.amount,

            # ---------------------------------------
            # IMPORTANT:
            # Preserve original request type
            # ---------------------------------------

            payment_type=payment_request.request_type,

            payment_method="manual",

            status="pending",

            external_payment_id=None

        )

            # ---------------------------------------
            # SAVE PROOF
            # ---------------------------------------
            if proof:
                payment.proof = proof
                payment.save()

            # ---------------------------------------
            # AUDIT LOG
            # ---------------------------------------
            AuditLog.objects.create(
                admin=request.user,
                action="payment_uploaded",
                payment=payment,
                message="Manual payment submitted for approval"
            )

            messages.success(
                request,
                "Payment submitted. Awaiting admin confirmation."
            )

        except Exception as e:
            messages.error(request, str(e))

        return redirect("members:member_payment_requests")

    return redirect("members:manual_payment_page", pk=pk)


@admin_required
def close_payment_request(request, pk):
    """
    Manually close a payment request.

    ✔ Allows admin to proceed to reconciliation
    ✔ Prevents lifecycle dead-end
    """

    payment_request = get_object_or_404(PaymentRequest, id=pk)

    # -----------------------------------
    # ALREADY CLOSED
    # -----------------------------------
    if payment_request.status == PaymentRequest.STATUS_CLOSED:
        messages.info(request, "This request is already closed.")
        return redirect("members_admin:admin_payment_detail", pk)

    # -----------------------------------
    # CONFIRMATION STEP
    # -----------------------------------
    if request.method == "POST":

        payment_request.status = PaymentRequest.STATUS_CLOSED
        payment_request.save(update_fields=["status"])

        messages.success(request, "Payment request closed successfully.")

        return redirect("members_admin:admin_payment_detail", pk)

    # -----------------------------------
    # SHOW CONFIRMATION PAGE
    # -----------------------------------
    return render(
        request,
        "members/admin/payments/confirm_close_request.html",
        {
            "payment_request": payment_request
        }
    )

@admin_required
def export_payment_request_pdf(request, pk):
    """
    Export a comprehensive Payment Request PDF report.

    REPORT CONTENT
    ---------------------------------------------------------
    1. Payment Request Details
    2. Payment Summary
       - Active/Required Members
       - Paid Members
       - Unpaid Members
       - Compliance
       - Total Collected
    3. Payment Compliance Chart
    4. Reconciliation Summary, when a claim settlement exists
       - Total Collected
       - Total Deductions
       - Total Paid Out
       - Notes
    5. Itemised Deduction Breakdown
    6. Final Financial Position
    7. Authorisation / Settlement information

    IMPORTANT
    ---------------------------------------------------------
    The member population and compliance calculation MUST
    match the Payment Request Detail page.

    Settlement figures are taken from the existing
    ClaimSettlement properties rather than being independently
    recalculated.
    """

    # =====================================================
    # GET PAYMENT REQUEST
    # =====================================================

    payment_request = get_object_or_404(
        PaymentRequest,
        pk=pk
    )

    # =====================================================
    # DETERMINE THE HISTORICAL REQUIRED MEMBER POPULATION
    # =====================================================

    # A populated target snapshot is the only reliable evidence
    # that the original target population has been recorded.
    target_snapshot_exists = payment_request.targeted_members.exists()

    required_member_ids = set(
        payment_request.targeted_members.values_list(
            "id",
            flat=True,
        )
    )

    # For older requests with no snapshot, gather request-specific
    # evidence for transparency. This candidate population is NOT
    # treated as a verified historical target population.
    if not target_snapshot_exists:
        required_member_ids.update(
            payment_request.paid_members.values_list(
                "id",
                flat=True,
            )
        )

        required_member_ids.update(
            payment_request.unpaid_members.values_list(
                "id",
                flat=True,
            )
        )

        required_member_ids.update(
            payment_request.selected_members.values_list(
                "id",
                flat=True,
            )
        )

        required_member_ids.update(
            Payment.objects.filter(
                payment_request=payment_request,
                status="completed",
            ).values_list(
                "member_id",
                flat=True,
            )
        )

    required_members = Member.objects.filter(
        id__in=required_member_ids,
    )

    # =====================================================
    # PAID MEMBERS
    # =====================================================

    paid_member_ids = set(
        Payment.objects.filter(
            payment_request=payment_request,
            status="completed",
            member_id__in=required_member_ids,
        ).values_list(
            "member_id",
            flat=True,
        )
    )

    paid_members = required_members.filter(
        id__in=paid_member_ids,
    ).distinct()

    # =====================================================
    # MEMBER COUNTS AND COMPLIANCE
    # =====================================================

    total_members = required_members.count()
    paid_count = paid_members.count()
    unpaid_count = max(0, total_members - paid_count)

    # Do not present a compliance percentage unless the original
    # target population is backed by the saved target snapshot.
    compliance = (
        round((paid_count / total_members) * 100)
        if target_snapshot_exists and total_members
        else None
    )

    # =====================================================
    # TOTAL COLLECTED
    # =====================================================

    total_collected = (
        payment_request.total_paid or 0
    )

    # =====================================================
    # FIND CLAIM SETTLEMENT
    #
    # Only claim payment requests have a settlement.
    #
    # The existing project uses:
    #
    #     payment_request.claim.settlement
    #
    # when a settlement exists.
    # =====================================================

    settlement = None

    if payment_request.claim:

        settlement = getattr(
            payment_request.claim,
            "settlement",
            None
        )

    # =====================================================
    # SETTLEMENT FINANCIAL DATA
    #
    # Use the existing settlement properties as the
    # source of truth.
    #
    # total_collected
    # total_deductions
    # amount_paid
    # =====================================================

    settlement_total_collected = 0
    settlement_total_deductions = 0
    settlement_amount_paid = 0
    deduction_items = []

    if settlement:

        settlement_total_collected = (
            settlement.total_collected or 0
        )

        settlement_total_deductions = (
            settlement.total_deductions or 0
        )

        settlement_amount_paid = (
            settlement.amount_paid or 0
        )

        deduction_items = list(
            settlement.deduction_items.all()
        )

    # =====================================================
    # PDF BUFFER
    # =====================================================

    buffer = BytesIO()

    # =====================================================
    # PDF DOCUMENT
    #
    # Use A4 and normal margins so the report can naturally
    # continue onto additional pages when required.
    # =====================================================

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    # =====================================================
    # STYLES
    # =====================================================

    styles = getSampleStyleSheet()

    title_style = styles["Title"]

    heading_style = styles["Heading2"]

    normal_style = styles["Normal"]

    small_style = styles["BodyText"]

    # =====================================================
    # PDF ELEMENTS
    # =====================================================

    elements = []

    # =====================================================
    # REPORT LOGO
    # =====================================================

    logo_path = finders.find(
        "images/logo.png"
    )

    if logo_path:

        logo = Image(
            logo_path,
            width=100,
            height=50,
            hAlign="CENTER",
        )

        elements.append(
            logo
        )

        elements.append(
            Spacer(1, 8)
        )

    # =====================================================
    # REPORT TITLE
    # =====================================================

    elements.append(
        Paragraph(
            "<b>PAYMENT REQUEST REPORT</b>",
            title_style
        )
    )

    elements.append(
        Spacer(1, 12)
    )

    # =====================================================
    # PAYMENT REQUEST DETAILS
    # =====================================================

    request_description = (
        payment_request.description
        if getattr(payment_request, "description", None)
        else "-"
    )

    # -----------------------------------------------------
    # FORMAT DUE DATE
    #
    # Keep the date as YYYY-MM-DD.
    # Show hour and minutes only.
    #
    # Example:
    # 2026-05-03 00:00:00+00:00
    # becomes:
    # 2026-05-03 00:00
    # -----------------------------------------------------

    if payment_request.due_date:

        due_date = payment_request.due_date.strftime(
            "%d/%m/%Y %H:%M"
        )

    else:

        due_date = "-"

    elements.append(
        Paragraph(
            f"<b>Payment Request ID:</b> "
            f"{payment_request.id}",
            normal_style
        )
    )

    elements.append(
        Paragraph(
            f"<b>Payment Type:</b> "
            f"{payment_request.request_type}",
            normal_style
        )
    )

    elements.append(
        Paragraph(
            f"<b>Description:</b> "
            f"{request_description}",
            normal_style
        )
    )

    elements.append(
        Paragraph(
            f"<b>Due Date:</b> "
            f"{due_date}",
            normal_style
        )
    )

    elements.append(
        Spacer(1, 14)
    )

    # =====================================================
    # PAYMENT SUMMARY
    # =====================================================

    elements.append(
        Paragraph(
            "Payment Summary",
            heading_style
        )
    )

    summary_data = [
        ["Description", "Value"],

        [
            "Historical Required Members",
            (
                f"{total_members:,}"
                if target_snapshot_exists
                else "Unverified - target snapshot missing"
            )
        ],

        [
            "Paid Members",
            f"{paid_count:,}"
        ],

        [
            "Unpaid Members",
            (
                f"{unpaid_count:,}"
                if target_snapshot_exists
                else "Unverified"
            )
        ],

        [
            "Compliance",
            f"{compliance}%"
            if compliance is not None
            else "Cannot be verified"
        ],

        [
            "Total Collected",
            f"£{total_collected:,.2f}"
        ],
    ]

    if not target_snapshot_exists:
        elements.append(
            Paragraph(
                "WARNING: The historical target snapshot is missing. "
                "Member counts shown from request-specific records are "
                "not a verified original target population, and compliance "
                "cannot be confirmed.",
                normal_style,
            )
        )
        elements.append(Spacer(1, 8))

    summary_table = Table(
        summary_data,
        colWidths=[360, 130],
        repeatRows=1,
    )

    summary_table.setStyle(
        TableStyle([

            # Header
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.grey
            ),

            (
                "TEXTCOLOR",
                (0, 0),
                (-1, 0),
                colors.white
            ),

            (
                "FONTNAME",
                (0, 0),
                (-1, 0),
                "Helvetica-Bold"
            ),

            # Body
            (
                "FONTNAME",
                (0, 1),
                (-1, -1),
                "Helvetica"
            ),

            (
                "FONTSIZE",
                (0, 0),
                (-1, -1),
                9
            ),

            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.5,
                colors.grey
            ),

            (
                "ALIGN",
                (1, 1),
                (1, -1),
                "RIGHT"
            ),

            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "MIDDLE"
            ),

            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                5
            ),

            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                5
            ),
        ])
    )

    elements.append(
        summary_table
    )

    elements.append(
        Spacer(1, 18)
    )

    # =====================================================
    # PAYMENT COMPLIANCE
    # =====================================================

    elements.append(
        Paragraph(
            "Payment Compliance",
            heading_style
        )
    )

    # -----------------------------------------------------
    # CREATE COMPLIANCE CHART
    # -----------------------------------------------------

    chart_buffer = BytesIO()

    fig, ax = plt.subplots(
        figsize=(4, 4)
    )

    # ---------------------------------------------
    # HANDLE EMPTY DATA SAFELY
    # ---------------------------------------------

    if not target_snapshot_exists or (
        paid_count == 0 and unpaid_count == 0
    ):

        ax.text(
            0.5,
            0.5,
            "Historical target population not verified"
            if not target_snapshot_exists
            else "No member data",
            ha="center",
            va="center",
            wrap=True,
        )

        ax.set_axis_off()

    else:

        labels = [
            "Paid",
            "Unpaid"
        ]

        sizes = [
            paid_count,
            unpaid_count
        ]

        ax.pie(
            sizes,
            labels=labels,
            autopct="%1.0f%%",
            startangle=90
        )

        ax.set_title(
            f"Payment Compliance: {compliance}%"
        )

    fig.tight_layout()

    fig.savefig(
        chart_buffer,
        format="png",
        dpi=150,
        bbox_inches="tight"
    )

    plt.close(fig)

    chart_buffer.seek(0)

    chart_image = Image(
        chart_buffer,
        width=280,
        height=280
    )

    elements.append(
        chart_image
    )

    elements.append(
        Spacer(1, 18)
    )

    # =====================================================
    # CLAIM SETTLEMENT / RECONCILIATION
    #
    # Only display this section when a settlement exists.
    #
    # Ordinary membership/subscription/payment requests
    # therefore retain the normal report without settlement
    # information.
    # =====================================================

    if settlement:

        # =================================================
        # RECONCILIATION SUMMARY
        # =================================================

        elements.append(
            Paragraph(
                "Reconciliation Summary",
                heading_style
            )
        )

        reconciliation_data = [
            ["Description", "Amount (£)"],

            [
                "Total Collected",
                f"{settlement_total_collected:,.2f}"
            ],

            [
                "Total Deductions",
                f"{settlement_total_deductions:,.2f}"
            ],

            [
                "Total Paid Out",
                f"{settlement_amount_paid:,.2f}"
            ],
        ]

        reconciliation_table = Table(
            reconciliation_data,
            colWidths=[360, 130],
            repeatRows=1,
        )

        reconciliation_table.setStyle(
            TableStyle([

                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.grey
                ),

                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, 0),
                    colors.white
                ),

                (
                    "FONTNAME",
                    (0, 0),
                    (-1, 0),
                    "Helvetica-Bold"
                ),

                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.grey
                ),

                (
                    "ALIGN",
                    (1, 1),
                    (1, -1),
                    "RIGHT"
                ),

                (
                    "FONTNAME",
                    (0, 3),
                    (-1, 3),
                    "Helvetica-Bold"
                ),

                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    6
                ),

                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    6
                ),
            ])
        )

        elements.append(
            reconciliation_table
        )

        elements.append(
            Spacer(1, 12)
        )

        # =================================================
        # DEDUCTIONS BREAKDOWN
        # =================================================

        elements.append(
            Paragraph(
                "Deductions Breakdown",
                heading_style
            )
        )

        if deduction_items:

            deduction_data = [
                [
                    "Item",
                    "Amount (£)"
                ]
            ]

            for deduction in deduction_items:

                deduction_data.append(
                    [
                        deduction.title,
                        f"{deduction.amount:,.2f}"
                    ]
                )

            # ---------------------------------------------
            # TOTAL DEDUCTIONS ROW
            # ---------------------------------------------

            deduction_data.append(
                [
                    "TOTAL DEDUCTIONS",
                    f"{settlement_total_deductions:,.2f}"
                ]
            )

            deduction_table = Table(
                deduction_data,
                colWidths=[360, 130],
                repeatRows=1,
            )

            deduction_table.setStyle(
                TableStyle([

                    # Header
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, 0),
                        colors.grey
                    ),

                    (
                        "TEXTCOLOR",
                        (0, 0),
                        (-1, 0),
                        colors.white
                    ),

                    (
                        "FONTNAME",
                        (0, 0),
                        (-1, 0),
                        "Helvetica-Bold"
                    ),

                    # Body
                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.5,
                        colors.grey
                    ),

                    (
                        "ALIGN",
                        (1, 1),
                        (1, -1),
                        "RIGHT"
                    ),

                    (
                        "FONTNAME",
                        (0, -1),
                        (-1, -1),
                        "Helvetica-Bold"
                    ),

                    (
                        "TOPPADDING",
                        (0, 0),
                        (-1, -1),
                        6
                    ),

                    (
                        "BOTTOMPADDING",
                        (0, 0),
                        (-1, -1),
                        6
                    ),
                ])
            )

            elements.append(
                deduction_table
            )

        else:

            elements.append(
                Paragraph(
                    "No deductions recorded.",
                    normal_style
                )
            )

        elements.append(
            Spacer(1, 16)
        )

        # =================================================
        # FINAL FINANCIAL POSITION
        # =================================================

        elements.append(
            Paragraph(
                "Final Financial Position",
                heading_style
            )
        )

        final_financial_data = [

            [
                "Total Collected",
                f"£{settlement_total_collected:,.2f}"
            ],

            [
                "Less: Total Deductions",
                f"£{settlement_total_deductions:,.2f}"
            ],

            [
                "TOTAL PAID OUT",
                f"£{settlement_amount_paid:,.2f}"
            ],
        ]

        final_financial_table = Table(
            final_financial_data,
            colWidths=[360, 130],
        )

        final_financial_table.setStyle(
            TableStyle([

                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.grey
                ),

                (
                    "ALIGN",
                    (1, 0),
                    (1, -1),
                    "RIGHT"
                ),

                (
                    "FONTNAME",
                    (0, 0),
                    (-1, 1),
                    "Helvetica"
                ),

                (
                    "FONTNAME",
                    (0, 2),
                    (-1, 2),
                    "Helvetica-Bold"
                ),

                (
                    "BACKGROUND",
                    (0, 2),
                    (-1, 2),
                    colors.lightgrey
                ),

                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    7
                ),

                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    7
                ),
            ])
        )

        elements.append(
            final_financial_table
        )

        elements.append(
            Spacer(1, 16)
        )

        # =================================================
        # NOTES
        # =================================================

        elements.append(
            Paragraph(
                "Notes",
                heading_style
            )
        )

        notes = (
            settlement.notes
            if settlement.notes
            else "-"
        )

        elements.append(
            Paragraph(
                str(notes),
                normal_style
            )
        )

        elements.append(
            Spacer(1, 14)
        )

        # =================================================
        # AUTHORISATION
        # =================================================

        elements.append(
            Paragraph(
                "Authorisation",
                heading_style
            )
        )

        prepared_by = (
            settlement.prepared_by
            if settlement.prepared_by
            else "-"
        )

        approved_by = (
            settlement.approved_by
            if settlement.approved_by
            else "Pending"
        )

        # -------------------------------------------------
        # FORMAT SETTLEMENT DATE
        #
        # Keep the date as YYYY-MM-DD.
        # Show hour and minutes only.
        #
        # Example:
        # 2026-05-07 00:31:23.176159+00:00
        # becomes:
        # 2026-05-07 00:31
        # -------------------------------------------------

        if settlement.settlement_date:

            settlement_date = (
                settlement.settlement_date.strftime(
                    "%d/%m/%Y %H:%M"
                )
            )

        else:

            settlement_date = "-"

        approval_status = (
            "Finalised"
            if settlement.is_approved
            else "Pending Approval"
        )

        authorisation_data = [

            [
                "Prepared By",
                str(prepared_by)
            ],

            [
                "Approved By",
                str(approved_by)
            ],

            [
                "Settlement Date",
                settlement_date
            ],

            [
                "Status",
                approval_status
            ],
        ]

        authorisation_table = Table(
            authorisation_data,
            colWidths=[180, 310],
        )

        authorisation_table.setStyle(
            TableStyle([

                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.grey
                ),

                (
                    "FONTNAME",
                    (0, 0),
                    (0, -1),
                    "Helvetica-Bold"
                ),

                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP"
                ),

                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    6
                ),

                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    6
                ),
            ])
        )

        elements.append(
            authorisation_table
        )

    # =====================================================
    # BUILD PDF
    # =====================================================

    doc.build(
        elements
    )

    # =====================================================
    # HTTP RESPONSE
    # =====================================================

    buffer.seek(0)

    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/pdf"
    )

    response[
        "Content-Disposition"
    ] = (
        f'inline; '
        f'filename="payment_request_report_'
        f'{payment_request.id}.pdf"'
    )

    return response
