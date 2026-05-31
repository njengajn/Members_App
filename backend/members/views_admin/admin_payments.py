# backend/members/views_admin/admin_payments.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone

from backend.members.services.member_status_service import retire_member
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

 
@admin_required
def admin_payment_request_detail(request, pk):

    payment_request = get_object_or_404(PaymentRequest, id=pk)

    return render(
        request,
        "members/admin/payments/admin_payment_request_details.html",
        {
            "payment_request": payment_request
        },
    )


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
def admin_payments_listOnHold28_05_26(request):
    """
    Admin Payment Requests List

    ✔ Shows:
        - Active / Overdue / Closed tabs
        - Pending payment count per request
        - Global pending count
    """

    tab = request.GET.get("tab", "active")
    now = timezone.now()

    # --------------------------------------------------
    # BASE QUERY
    # --------------------------------------------------
    payment_requests = PaymentRequest.objects.all().order_by("-created_at")

    # --------------------------------------------------
    # TAB FILTERING
    # --------------------------------------------------
    if tab == "active":
        payment_requests = payment_requests.filter(
            status=PaymentRequest.STATUS_ACTIVE,
            due_date__gte=now
        )

    elif tab == "overdue":
        payment_requests = payment_requests.filter(
            status=PaymentRequest.STATUS_ACTIVE,
            due_date__lt=now
        )

    elif tab == "closed":
        payment_requests = payment_requests.filter(
            status=PaymentRequest.STATUS_CLOSED
        )

    # --------------------------------------------------
    # ADD PENDING COUNT PER REQUEST (CRITICAL FIX)
    # --------------------------------------------------
    payment_requests = payment_requests.annotate(
        pending_count=Count(
            "payments",
            filter=Q(payments__status=Payment.STATUS_PENDING)
        )
    )

    # --------------------------------------------------
    # GLOBAL COUNTS
    # --------------------------------------------------
    counts = {
        "active": PaymentRequest.objects.filter(
            status=PaymentRequest.STATUS_ACTIVE,
            due_date__gte=now
        ).count(),

        "overdue": PaymentRequest.objects.filter(
            status=PaymentRequest.STATUS_ACTIVE,
            due_date__lt=now
        ).count(),

        "closed": PaymentRequest.objects.filter(
            status=PaymentRequest.STATUS_CLOSED
        ).count(),
    }

    # --------------------------------------------------
    # GLOBAL PENDING COUNT (REUSED)
    # --------------------------------------------------
    pending_total = Payment.objects.filter(
        status=Payment.STATUS_PENDING
    ).count()

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


# ==========================================
# CREATE PAYMENT REQUEST
# ==========================================

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

    PURPOSE

        - Normal Payment Request
        - Claim Settlement

    PAYMENT REQUEST LIFECYCLE

        ACTIVE -> CLOSED -> ARCHIVED

    Claim settlements do NOT alter
    targeting behaviour.

    Notifications may be enabled
    or disabled per request.
    =====================================================
    """

    # =================================================
    # PAGE DATA
    # =================================================

    members = Member.objects.filter(
        status=Member.STATUS_ACTIVE
    ).order_by(
        "first_name",
        "surname",
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
            # OTHER FORM DATA
            # =========================================

            claim_id = request.POST.get(
                "claim"
            )

            request_type = request.POST.get(
                "request_type"
            )

            amount = request.POST.get(
                "amount"
            )

            # =========================================
            # AMOUNT VALIDATION
            # =========================================

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

            if target_mode == "single":

                if not member_id:

                    raise ValueError(
                        "Please select a member."
                    )

                if selected_members_ids:

                    raise ValueError(
                        "Single member mode cannot use selected members."
                    )

                Member.objects.get(
                    id=member_id,
                    status=Member.STATUS_ACTIVE,
                )

            elif target_mode == "selected":

                if member_id:

                    raise ValueError(
                        "Selected members mode cannot use single member."
                    )

                if not selected_members_ids:

                    raise ValueError(
                        "Please select at least one member."
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

                claim = get_object_or_404(
                    Claim,
                    id=claim_id
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
                        "A payment request already exists for this claim."
                    )

            # =========================================
            # TARGET CONFIGURATION
            # =========================================

            member = None
            viewable_by_all = False

            if target_mode == "all":

                viewable_by_all = True

            elif target_mode == "single":

                member = get_object_or_404(
                    Member,
                    id=member_id
                )

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

            target_members = []

            if target_mode == "all":

                target_members = (
                    Member.objects.filter(
                        status=Member.STATUS_ACTIVE
                    )
                )

            elif target_mode == "single":

                target_members = [member]

            elif target_mode == "selected":

                target_members = (
                    payment_request.selected_members.all()
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
            "approved_claims": approved_claims,
            "today": timezone.now(),
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
def update_payment_request_status(request, request_id):

    payment_request = get_object_or_404(PaymentRequest, id=request_id)
    if request.method == "POST":
        new_status = request.POST.get("status")
        if new_status in ["active", "closed"]:
            payment_request.status = new_status
            payment_request.save()
            messages.success(request, "Payment request status updated.")

    return redirect("members_admin:admin_payments_list")



@admin_required
def payment_compliance_tracker(request, pk):

    payment_request = get_object_or_404(PaymentRequest, pk=pk)

    # Convert NOW to DATE
    today = timezone.now().date()

    # Normalize due_date to DATE
    due_date = payment_request.due_date
    if hasattr(due_date, "date"):
        due_date = due_date.date()

    # Check overdue
    is_overdue = False
    if due_date:
        is_overdue = due_date < today

    # Determine required members
    if payment_request.member:
        required_members = Member.objects.filter(id=payment_request.member.id)
    else:
        required_members = Member.objects.filter(status="active")

    # Get payments for this request
    payments = Payment.objects.filter(
        payment_request=payment_request,
        status="completed"
    )

    paid_member_ids = payments.values_list("member_id", flat=True)

    paid_members = Member.objects.filter(id__in=paid_member_ids)

    unpaid_members = required_members.exclude(id__in=paid_member_ids)

    total_required = required_members.count()
    total_paid = paid_members.count()

    compliance = 0
    if total_required > 0:
        compliance = round((total_paid / total_required) * 100)

    context = {
        "payment_request": payment_request,
        "paid_members": paid_members,
        "unpaid_members": unpaid_members,
        "total_required": total_required,
        "total_paid": total_paid,
        "compliance": compliance,
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


@admin_required
def export_payment_compliance_csv(request, pk):

    payment_request = PaymentRequest.objects.get(pk=pk)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="payment_report_{payment_request.id}.csv"'
    )

    writer = csv.writer(response)

    writer.writerow([
        "Member UID",
        "Member Name",
        "Payment Request",
        "Amount",
        "Status",
        "Payment Date"
    ])

    members = Member.objects.filter(status="active")

    for member in members:

        payment = Payment.objects.filter(
            member=member,
            payment_request=payment_request,
            status="completed"
        ).first()

        if payment:
            status = "Paid"
            date = payment.approved_at
        else:
            status = "Not Paid"
            date = ""

        writer.writerow([
            member.member_uid,
            f"{member.first_name} {member.surname}",
            payment_request.request_type,
            payment_request.amount,
            status,
            date
        ])

    return response

from django.http import HttpResponse


@admin_required
def export_payment_members_onHold(request, pk):
    """
    Export paid/unpaid members
    """

    payment_request = get_object_or_404(PaymentRequest, id=pk)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="payment_members.csv"'

    writer = csv.writer(response)
    writer.writerow(['Name', 'Status'])

    members = payment_request.selected_members.all()

    for m in members:
        status = "Paid" if m in payment_request.paid_members.all() else "Unpaid"
        writer.writerow([f"{m.first_name} {m.surname}", status])

    return response

@admin_required
def export_payment_members_onHold(request, pk):
    payment_request = PaymentRequest.objects.get(pk=pk)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="payment_report_{payment_request.id}.csv"'
    )

    writer = csv.writer(response)

    writer.writerow([
        "Member UID",
        "Member Name",
        "Payment Request",
        "Amount",
        "Status",
        "Payment Date"
    ])

    members = Member.objects.filter(status="active")

    for member in members:

        payment = Payment.objects.filter(
            member=member,
            payment_request=payment_request,
            status="completed"
        ).first()

        if payment:
            status = "Paid"
            date = payment.approved_at
        else:
            status = "Not Paid"
            date = ""

        writer.writerow([
            member.member_uid,
            f"{member.first_name} {member.surname}",
            payment_request.request_type,
            payment_request.amount,
            status,
            date
        ])

    return response



@admin_required
def export_payment_membersLater(request, pk):
    """
    Export payment report (CSV)

    ✔ FIXED:
        - unpaid members now show amount = 0.00
        - keeps existing structure (no redesign)
    """

    payment_request = get_object_or_404(PaymentRequest, pk=pk)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="payment_report_{payment_request.id}.csv"'
    )

    writer = csv.writer(response)

    # ======================================================
    # TITLE
    # ======================================================
    writer.writerow([
        f"Payment Report: {payment_request.title or payment_request.request_type}"
    ])
    writer.writerow([])

    # ======================================================
    # HEADERS
    # ======================================================
    writer.writerow([
        "Request ID",
        "Member UID",
        "Member Name",
        "Payment Request",
        "Amount",
        "Status",
        "Payment Date"
    ])

    # ======================================================
    # MEMBER SET (UNCHANGED)
    # ======================================================
    member_set = set()

    paid_members = payment_request.paid_members.all()
    member_set.update(paid_members)

    selected_members = payment_request.selected_members.all()
    member_set.update(selected_members)

    if payment_request.viewable_by_all:
        active_members = Member.objects.filter(status="active")
        member_set.update(active_members)

    members = sorted(member_set, key=lambda m: m.member_uid or "")

    # ======================================================
    # LOOP members
    # ======================================================
    for member in members:

        payment = Payment.objects.filter(
            member=member,
            payment_request=payment_request,
            status="completed"
        ).order_by("-id").first()

        if payment:
            status = "Paid"

            #get actual payment amount
            amount = payment.amount

            payment_date = (
                payment.approved_at
                or payment.paid_at
                or payment.created_at
            )

            if payment_date:
                date = payment_date.strftime("%Y-%m-%d %H:%M")
            else:
                date = "N/A"

        else:
            status = "pending"

            amount = "0.00"

            date = ""

        writer.writerow([
            payment_request.id,
            member.member_uid,
            f"{member.first_name} {member.surname}",
            payment_request.title or payment_request.request_type,
            amount,  
            status,
            date
        ])

    return response

# ======================================================
# EXPORT PAYMENT MEMBERS (CSV)
# ======================================================
@admin_required
def export_payment_members(request, pk):
    """
    Export payment report (CSV)

    ✔ Removed "Payment Request" column
    ✔ Keeps existing structure
    ✔ Fixes unpaid amount → 0.00
    ✔ Adds totals row
    ✔ Uses correct alignment
    """

    payment_request = get_object_or_404(PaymentRequest, pk=pk)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="payment_report_{payment_request.id}.csv"'
    )

    writer = csv.writer(response)

    # ======================================================
    # TITLE
    # ======================================================
    writer.writerow([
        f"Payment Report: {payment_request.title or payment_request.request_type}"
    ])
    writer.writerow([])

    # ======================================================
    # HEADERS (REMOVED PAYMENT REQUEST COLUMN)
    # ======================================================
    writer.writerow([
        "Request ID",
        "Member UID",
        "Member Name",
        "Amount",
        "Status",
        "Payment Date"
    ])

    # ======================================================
    # MEMBER SET
    # ======================================================
    member_set = set()

    member_set.update(payment_request.paid_members.all())
    member_set.update(payment_request.selected_members.all())

    if payment_request.viewable_by_all:
        member_set.update(Member.objects.filter(status="active"))

    members = sorted(member_set, key=lambda m: m.member_uid or "")

    # ======================================================
    # TOTALS
    # ======================================================
    total_paid = 0.0
    total_pending = 0.0

    # ======================================================
    # LOOP
    # ======================================================
    for member in members:

        payment = Payment.objects.filter(
            member=member,
            payment_request=payment_request,
            status="completed"
        ).order_by("-id").first()

        if payment:
            status = "Paid"
            amount = float(payment.amount)
            total_paid += amount

            payment_date = (
                payment.approved_at
                or payment.paid_at
                or payment.created_at
            )

            date = payment_date.strftime("%Y-%m-%d %H:%M") if payment_date else "N/A"

        else:
            status = "pending"
            amount = 0.00
            total_pending += float(payment_request.amount)
            date = ""

        writer.writerow([
            payment_request.id,
            member.member_uid,
            f"{member.first_name} {member.surname}",
            f"{amount:.2f}",
            status,
            date
        ])

    # ======================================================
    # TOTALS ROW
    # ======================================================
    writer.writerow([])

    writer.writerow([
        "",
        "",
        "TOTAL PAID",
        f"{total_paid:.2f}",
        "",
        ""
    ])

    writer.writerow([
        "",
        "",
        "TOTAL PENDING",
        f"{total_pending:.2f}",
        "",
        ""
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
def update_payment_requestOnHold28_05_26(request, pk):
    """
    ADMIN EDIT PAYMENT REQUEST

    Allows editing of:
    -----------------------------------------
    ✔ Type
    ✔ Title
    ✔ Description
    ✔ Amount
    ✔ Due date
    ✔ Target member(s)

    TARGET OPTIONS
    -----------------------------------------
    ✔ All members
    ✔ Selected members
    ✔ Single member
    """

    payment_request = get_object_or_404(
        PaymentRequest,
        id=pk
    )

    members = Member.objects.filter(
        status=Member.STATUS_ACTIVE
    ).order_by("first_name", "surname")

    if request.method == "POST":

        # =================================================
        # BASIC FIELDS
        # =================================================

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

        # =================================================
        # DUE DATE
        # =================================================

        due_date_raw = request.POST.get("due_date")

        if due_date_raw:
            payment_request.due_date = parse_datetime(
                due_date_raw
            )

        # =================================================
        # TARGET MEMBERS
        # =================================================

        target_type = request.POST.get("target_type")

        # RESET TARGETS
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

            member_id = request.POST.get("member")

            if member_id:

                try:
                    payment_request.member = Member.objects.get(
                        id=member_id
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
            
            # =====================================================
            # PREVENT EDITING CLOSED/ARCHIVED REQUESTS
            # =====================================================

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
        # SAVE
        # =================================================

        payment_request.save()

        messages.success(
            request,
            "Payment request updated successfully."
        )

        return redirect(
            "members_admin:admin_payments_list"
        )

    return render(
        request,
        "members/admin/payments/admin_update_payment_request.html",
        {
            "payment_request": payment_request,
            "members": members,
        }
    )

@admin_required
def update_payment_requestOnHold7May26(request, pk):
    """
    ADMIN EDIT PAYMENT REQUEST

    ✔ Title, description, amount
    ✔ Targeting (ALL / selected / single)
    ✔ Safe datetime parsing
    """

    payment_request = get_object_or_404(PaymentRequest, id=pk)

    if request.method == "POST":

        payment_request.title = request.POST.get("title")
        payment_request.description = request.POST.get("description")

        # amount (safe cast)
        try:
            payment_request.amount = float(request.POST.get("amount", 0))
        except ValueError:
            messages.error(request, "Invalid amount.")
            return redirect(request.path)

        # due date
        due_date_raw = request.POST.get("due_date")
        if due_date_raw:
            payment_request.due_date = parse_datetime(due_date_raw)

        # -----------------------------------
        # TARGET LOGIC (IMPORTANT)
        # -----------------------------------
        target_type = request.POST.get("target_type")

        if target_type == "all":
            payment_request.viewable_by_all = True
            payment_request.selected_members.clear()
            payment_request.member = None

        elif target_type == "single":
            member_id = request.POST.get("member_id")
            member = Member.objects.filter(id=member_id).first()

            if member:
                payment_request.viewable_by_all = False
                payment_request.member = member
                payment_request.selected_members.clear()

        elif target_type == "selected":
            member_ids = request.POST.getlist("selected_members")

            members = Member.objects.filter(id__in=member_ids)

            payment_request.viewable_by_all = False
            payment_request.member = None
            payment_request.selected_members.set(members)

        payment_request.save()

        messages.success(request, "Payment request updated.")
        return redirect("members_admin:admin_payments_list")

    members = Member.objects.filter(status="active")

    return render(
        request,
        "members/admin/payments/admin_update_payment_request.html",
        {
            "payment_request": payment_request,
            "members": members,
        },
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
    PROFESSIONAL PAYMENT REQUEST REPORT PDF

    Includes:
    -----------------------------------------
    ✔ request details
    ✔ compliance summary
    ✔ paid/unpaid statistics
    ✔ accounting-style tables
    ✔ compliance pie chart
    """

    payment_request = get_object_or_404(
        PaymentRequest,
        id=pk
    )

    # =====================================================
    # DETERMINE TARGET MEMBERS
    # =====================================================

    if (
        payment_request.viewable_by_all
        and payment_request.member
        and payment_request.member.organization
    ):

        all_members = Member.objects.filter(
            organization=payment_request.member.organization,
            status=Member.STATUS_ACTIVE
        )

    elif payment_request.selected_members.exists():

        all_members = payment_request.selected_members.all()

    elif payment_request.member:

        all_members = Member.objects.filter(
            id=payment_request.member.id
        )

    else:

        all_members = Member.objects.none()

    # =====================================================
    # COUNTS
    # =====================================================

    total_members = all_members.count()

    paid_count = payment_request.paid_members.count()

    unpaid_count = max(
        0,
        total_members - paid_count
    )

    compliance = 0

    if total_members > 0:
        compliance = int(
            (paid_count / total_members) * 100
        )

    total_collected = payment_request.total_paid or 0

    # =====================================================
    # PDF BUFFER
    # =====================================================

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter
    )

    styles = getSampleStyleSheet()

    elements = []

    # =====================================================
    # TITLE
    # =====================================================

    elements.append(
        Paragraph(
            f"<b>Payment Request Report #{payment_request.id}</b>",
            styles["Title"]
        )
    )

    elements.append(Spacer(1, 12))

    # =====================================================
    # SUMMARY TABLE
    # =====================================================

    summary_data = [
        ["Field", "Value"],
        ["Title", payment_request.title],
        ["Type", payment_request.request_type.title()],
        ["Amount", f"£{payment_request.amount}"],
        ["Total Collected", f"£{total_collected}"],
        ["Due Date", str(payment_request.due_date)],
        ["Status", payment_request.status.title()],
        ["Active Members", str(total_members)],
        ["Paid Members", str(paid_count)],
        ["Unpaid Members", str(unpaid_count)],
        ["Compliance", f"{compliance}%"],
    ]

    summary_table = Table(
        summary_data,
        colWidths=[180, 300]
    )

    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.black),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 1, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
    ]))

    elements.append(summary_table)

    elements.append(Spacer(1, 20))

    # =====================================================
    # SAFE PIE CHART
    # =====================================================

    chart_buffer = io.BytesIO()

    fig, ax = plt.subplots(figsize=(4, 4))

    # ---------------------------------------------
    # HANDLE EMPTY DATA SAFELY
    # ---------------------------------------------
    if paid_count == 0 and unpaid_count == 0:

        ax.text(
            0.5,
            0.5,
            "No member data",
            horizontalalignment="center",
            verticalalignment="center",
            fontsize=12
        )

        ax.axis("off")

    else:

        labels = ["Paid", "Unpaid"]

        sizes = [paid_count, unpaid_count]

        ax.pie(
            sizes,
            labels=labels,
            autopct="%1.1f%%",
            startangle=90
        )

        ax.axis("equal")

    plt.tight_layout()

    plt.savefig(
        chart_buffer,
        format="png"
    )

    plt.close()

    chart_buffer.seek(0)

    elements.append(
        Paragraph(
            "<b>Compliance Overview</b>",
            styles["Heading2"]
        )
    )

    elements.append(Spacer(1, 10))

    chart_image = Image(
        chart_buffer,
        width=250,
        height=250
    )

    elements.append(chart_image)

    # =====================================================
    # BUILD PDF
    # =====================================================

    doc.build(elements)

    pdf = buffer.getvalue()

    buffer.close()

    response = HttpResponse(
        content_type="application/pdf"
    )

    response["Content-Disposition"] = (
        f'attachment; filename="payment_request_{payment_request.id}.pdf"'
    )

    response.write(pdf)

    return response


def export_payment_request_pdfOnHold8_5_26(request, pk):
    """
    PROFESSIONAL ACCOUNTING-STYLE PAYMENT REPORT
    """

    payment_request = get_object_or_404(PaymentRequest, id=pk)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)

    elements = []
    styles = getSampleStyleSheet()

    # =========================================
    # DATA PREPARATION
    # =========================================
    total_required = payment_request.amount
    total_collected = payment_request.total_paid

    paid_members = payment_request.paid_members.all()
    paid_count = paid_members.count()

    # -----------------------------------------
    # TOTAL ACTIVE MEMBERS (NEW)
    # -----------------------------------------
    if payment_request.member and payment_request.member.organization:
        active_members = Member.objects.filter(
            organization=payment_request.member.organization,
            status=Member.STATUS_ACTIVE
        )
    else:
        active_members = Member.objects.none()

    total_active_members = active_members.count()

    # -----------------------------------------
    # TARGET MEMBERS (FOR COMPLIANCE)
    # -----------------------------------------
    if payment_request.viewable_by_all:
        target_members = active_members
    elif payment_request.selected_members.exists():
        target_members = payment_request.selected_members.all()
    elif payment_request.member:
        target_members = [payment_request.member]
    else:
        target_members = []

    total_target = len(target_members) if isinstance(target_members, list) else target_members.count()

    unpaid_count = max(0, total_target - paid_count)

    compliance = 0
    if total_target > 0:
        compliance = int((paid_count / total_target) * 100)

    # =========================================
    # TITLE
    # =========================================
    elements.append(Paragraph("PAYMENT RECONCILIATION REPORT", styles["Title"]))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph(f"<b>{payment_request.title}</b>", styles["Heading2"]))
    elements.append(Spacer(1, 6))

    elements.append(Paragraph(f"Type: {payment_request.request_type.title()}", styles["Normal"]))
    elements.append(Paragraph(f"Date Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]))
    elements.append(Spacer(1, 12))

    # =========================================
    # SUMMARY TABLE
    # =========================================
    summary_data = [
        ["Metric", "Value"],
        ["Total Active Members", total_active_members],
        ["Target Members", total_target],
        ["Paid Members", paid_count],
        ["Unpaid Members", unpaid_count],
        ["Required Amount", f"£{total_required}"],
        ["Collected Amount", f"£{total_collected}"],
        ["Compliance", f"{compliance}%"],
    ]

    table = Table(summary_data, colWidths=[250, 150])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 20))

    # =========================================
    # PIE CHART (PROFESSIONAL STYLE)
    # =========================================
    fig, ax = plt.subplots(figsize=(4, 4))

    ax.pie(
        [paid_count, unpaid_count],
        labels=["Paid", "Unpaid"],
        autopct="%1.0f%%",
        startangle=90,
        wedgeprops={"linewidth": 1, "edgecolor": "white"}
    )

    ax.set_title("Compliance Breakdown", fontsize=10)
    ax.axis("equal")

    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, bbox_inches="tight", dpi=150)
    plt.close(fig)

    img_buffer.seek(0)
    elements.append(Image(img_buffer, width=4 * inch, height=3 * inch))
    elements.append(Spacer(1, 20))

    # =========================================
    # DAILY TREND (CLEAN LINE GRAPH)
    # =========================================
    payments = Payment.objects.filter(
        payment_request=payment_request,
        status="completed"
    ).order_by("approved_at")

    daily_totals = defaultdict(float)

    for p in payments:
        if p.approved_at:
            day = p.approved_at.date()
            daily_totals[day] += float(p.amount)

    if daily_totals:
        dates = sorted(daily_totals.keys())
        values = [daily_totals[d] for d in dates]

        fig, ax = plt.subplots(figsize=(5, 3))

        ax.plot(dates, values, linewidth=2)

        ax.set_title("Daily Payment Trend", fontsize=10)
        ax.set_xlabel("Date")
        ax.set_ylabel("Amount (£)")

        ax.grid(True, linestyle="--", linewidth=0.5)

        fig.autofmt_xdate()

        img_buffer2 = io.BytesIO()
        plt.savefig(img_buffer2, bbox_inches="tight", dpi=150)
        plt.close(fig)

        img_buffer2.seek(0)
        elements.append(Image(img_buffer2, width=5 * inch, height=3 * inch))

    # =========================================
    # BUILD PDF
    # =========================================
    doc.build(elements)

    buffer.seek(0)

    return HttpResponse(
        buffer,
        content_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="payment_report_{pk}.pdf"'
        },
    )

