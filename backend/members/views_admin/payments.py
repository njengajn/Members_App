"""
ADMIN PAYMENTS VIEWS
---------------------------------------------------------

Handles:

• Approving payments (Treasurer only)
• Viewing payment requests
• Creating payment request from approved claim
• Force closing payment request
• Downloading receipt PDF

All URLs use 'members_admin' namespace consistently.
"""

from decimal import Decimal
from datetime import timedelta

from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
from django.utils import timezone
from django.http import HttpResponse

from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

from backend.members.decorators import admin_required
from backend.members.models import AuditLog, Claim, Member, Payment, PaymentRequest
from backend.members.permissions import is_treasurer
from backend.members.services.payment_service import approve_payment
from backend.members.services.payment_service import record_payment
import json
import logging

from datetime import timedelta
from collections import defaultdict

from backend.members.services.payment_service import create_payment_request

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from datetime import datetime
from backend.members.utils.payments import validate_due_date


# ==========================================================
# APPROVE PAYMENT (Treasurer Only)
# ==========================================================
from django.core.paginator import Paginator
from django.db.models import Q

from django.conf import settings



# ==========================================================
# ADMIN – VIEW ALL COMPLETED PAYMENTS
# ==========================================================
@staff_member_required
def admin_payments_list(request):
    """
    Displays all completed payments across all members.
    """

    payments_list = PaymentRequest.objects.filter(
        status="completed"
    ).select_related("member").order_by("-created_at")

    # Optional search
    search_query = request.GET.get("q")
    if search_query:
        payments_list = payments_list.filter(
            Q(member__user__first_name__icontains=search_query) |
            Q(member__user__last_name__icontains=search_query) |
            Q(member__membership_number__icontains=search_query)
        )

    # Pagination
    paginator = Paginator(payments_list, 25)
    page_number = request.GET.get("page")
    payments = paginator.get_page(page_number)

    context = {
        "payments": payments,
        "search_query": search_query,
    }

    return render(
        request,
        "members/admin/payments/admin_payments.html",
        {"payments": payments},
    )


# ==========================================================
# ADMIN – VIEW SINGLE PAYMENT REQUEST
# ==========================================================
@login_required
@staff_member_required
def admin_view_payment_request(request, pk):
    """
    View details of a single payment request.
    """

    payment = get_object_or_404(PaymentRequest, pk=pk)

    context = {
        "payment": payment,
    }

    return render(
        request,
        "members/admin/payments/admin_view_payment_request.html",
        context
    )


@staff_member_required
def admin_create_payment_request_unused(request):
    
    print("VIEW DB NAME:", settings.DATABASES["default"]["NAME"])

    approved_claims = Claim.objects.filter(status=Claim.STATUS_APPROVED)
    members = Member.objects.filter(status="active").select_related("address")

    grouped_members = defaultdict(list)
    for m in members:
        key = str(m.address) if m.address else "No Address"
        grouped_members[key].append(m)

    if request.method == "POST":

        # ✅ DEBUG MUST BE INSIDE VIEW
        print("POST DATA:", dict(request.POST))

        try:
            payment_method = request.POST.get("payment_method")

            # ✅ STRICT VALIDATION
            if not payment_method:
                raise ValueError("Payment method is required.")

            if payment_method not in ["manual", "card", "both"]:
                raise ValueError(f"Invalid payment method: {payment_method}")

            due_date = validate_due_date(request.POST.get("due_date"))

            amount = request.POST.get("amount")
            description = request.POST.get("description")
            target_mode = request.POST.get("target_mode")

            if not amount:
                raise ValueError("Amount required.")

            if target_mode == "single":
                member = Member.objects.get(id=request.POST.get("member"))

                create_payment_request(
                    member=member,
                    amount=amount,
                    description=description,
                    due_date=due_date,
                    payment_method=payment_method,
                )

            elif target_mode == "multiple":

                pr = create_payment_request(
                    member=None,
                    amount=amount,
                    description=description,
                    due_date=due_date,
                    payment_method=payment_method,
                )

                pr.selected_members.set(request.POST.getlist("selected_members"))

            else:
                create_payment_request(
                    member=None,
                    amount=amount,
                    description=description,
                    due_date=due_date,
                    payment_method=payment_method,
                )

            messages.success(request, "Payment request created.")
            return redirect("members_admin:admin_payments")

        except Exception as e:
            messages.error(request, str(e))

    return render(
        request,
        "members/admin/payments/admin_create_payment_request.html",
        {
            "approved_claims": approved_claims,
            "members": members,
            "grouped_members": dict(grouped_members),
            "today": timezone.now(),
        },
    )


@login_required
@staff_member_required
#@user_passes_test(is_treasurer)
def approve_payment_view(request, pk):
    """
    Admin view wrapper

    Calls service layer function
    """

    approve_payment(payment_id=pk, approved_by=request.user)

    return redirect("members_admin:payments_awaiting_confirmation")
# ==========================================================
# LIST PAYMENT REQUESTS (Admin)
# ==========================================================

@login_required
@staff_member_required
def payment_requests_admin(request):
    """
    View all payment requests.
    """

    payment_requests = (
        PaymentRequest.objects
        .select_related("member", "claim")
        .order_by("-created_at")
    )

    return render(
        request,
        "members/admin/payment_requests.html",
        {"payment_requests": payment_requests},
    )


# ==========================================================
# FORCE CLOSE PAYMENT REQUEST
# ==========================================================

@login_required
@staff_member_required
def admin_force_close_payment_request(request, pk):
    pr = get_object_or_404(PaymentRequest, pk=pk)

    pr.status = PaymentRequest.STATUS_CLOSED
    pr.closed_at = timezone.now()
    pr.save()

    messages.success(request, "Payment request forcibly closed.")
    return redirect("members_admin:payment_requests")


# ==========================================================
# DOWNLOAD RECEIPT PDF
# ==========================================================

@login_required
@staff_member_required
def admin_download_receipt(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="receipt_{payment.reference}.pdf"'
    )

    doc = SimpleDocTemplate(response)
    styles = getSampleStyleSheet()

    content = [
        Paragraph(f"Receipt: {payment.reference}", styles["Heading1"]),
        Paragraph(f"Member: {payment.member.full_name}", styles["Normal"]),
        Paragraph(f"Amount: £{payment.amount}", styles["Normal"]),
        Paragraph(f"Date: {payment.created_at}", styles["Normal"]),
    ]

    doc.build(content)
    return response

# payments/admin_views/payments.py

logger = logging.getLogger(__name__)


@csrf_exempt
def payment_webhook(request):
    """
    Stripe webhook handler
    Stripe webhook endpoint
    URL:
    /admin-panel/payments/webhook/
    Handles:
    - payment success
    - auto reconciliation
    """
    # Only allow POST (Stripe sends POST)
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=400)

    try:
        data = json.loads(request.body)

        logger.info(f"🔥 Webhook received: {data}")

        event_type = data.get("type")

        if event_type == "checkout.session.completed":

            session = data.get("data", {}).get("object", {})
            reference = session.get("client_reference_id")

            from backend.members.models import Payment

            if reference:
                try:
                    payment = Payment.objects.get(
                        reference=reference,
                        status="pending"
                    )

                    payment.status = "completed"
                    payment.is_overdue = False
                    payment.save()

                    logger.info(f"✅ Payment updated: {reference}")

                except Payment.DoesNotExist:
                    logger.warning(f"⚠️ Payment not found: {reference}")

        return JsonResponse({"status": "ok"})

    except Exception as e:
        logger.error(str(e))
        return JsonResponse({"error": str(e)}, status=500)
    

@login_required
@staff_member_required
def payments_awaiting_confirmation(request):
    """
    CORRECT LOGIC FOR YOUR SYSTEM:

    Awaiting confirmation =
    - Payment NOT approved yet
    - approved_at is NULL

    NOT based on:
    - method ❌
    - payment_type ❌ (because yours is claim/other)
    """

    payments = (
        Payment.objects
        .filter(
            approved_at__isnull=True   # ✅ KEY FIX
        )
        .select_related("member", "payment_request")
        .order_by("-id")
    )

    print("DEBUG → awaiting payments:", payments.count())

    return render(
        request,
        "members/admin/payments/awaiting_confirmation.html",
        {"payments": payments}
    )

@login_required
@staff_member_required
def audit_logs(request):

    logs = AuditLog.objects.select_related(
        "user", "payment"
    ).order_by("-created_at")

    return render(
        request,
        "members/admin/audit_logs.html",
        {"logs": logs}
    )

def completed_payment_requests(request):

    now = timezone.now()

    requests = PaymentRequest.objects.filter(
        due_date__lt=now
    )

    return render(
        request,
        "members/admin/completed_payment_requests.html",
        {"requests": requests}
    )

@admin_required
def archive_payment_request(request, pk):
    """
    =====================================================
    ARCHIVE PAYMENT REQUEST
    =====================================================

    Archives a payment request instead of deleting it.

    WHY ARCHIVE INSTEAD OF DELETE?
    -----------------------------------------------------

    - preserves finance history
    - preserves payment relationships
    - preserves audit integrity
    - avoids broken reports
    - prevents accidental data loss

    BUSINESS RULES
    -----------------------------------------------------

    ✔ Active requests can be archived
    ✔ Closed requests can be archived
    ✔ Archived requests become read-only
    ✔ Archived requests are hidden from members
    ✔ Archived requests cannot receive payments
    =====================================================
    """

    # =================================================
    # GET PAYMENT REQUEST
    # =================================================

    payment_request = get_object_or_404(
        PaymentRequest,
        pk=pk
    )

    # =================================================
    # PREVENT REPEATED ARCHIVE
    # =================================================

    if payment_request.status == (
        PaymentRequest.STATUS_ARCHIVED
    ):

        messages.warning(
            request,
            "Payment request already archived."
        )

        return redirect(
            "members_admin:payment_request_detail",
            pk=payment_request.pk
        )

    # =================================================
    # ARCHIVE REQUEST
    # =================================================

    payment_request.status = (
        PaymentRequest.STATUS_ARCHIVED
    )

    payment_request.archived_at = timezone.now()

    payment_request.archived_by = request.user

    payment_request.save()

    # =================================================
    # SUCCESS MESSAGE
    # =================================================

    messages.success(
        request,
        (
            f"Payment request "
            f"#{payment_request.id} archived successfully."
        )
    )

    # =================================================
    # REDIRECT
    # =================================================

    return redirect(
        "members_admin:admin_payments_list"
    )