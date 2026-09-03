from django.shortcuts import render
from .admin_auth import admin_required
from backend.members.models import Member, Claim, PaymentRequest, Payment
from backend.members.models import AuditLog
from django.db.models import Q, Case, CharField, Count, Value, When
from backend.members.services.dashboard_metrics import (
    get_claim_metrics,
    get_payment_metrics
)
from django.db.models import Count, Q, F, Case, When, Value, CharField
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.contrib.auth.decorators import user_passes_test


# ======================================================
# ✅ SAFE ADMIN CHECK (RENAMED)
# ======================================================
def is_admin_user(user):
    """
    Prevents naming conflict with decorators.
    """
    return user.is_authenticated and user.is_staff

# ======================================================
# ADMIN DASHBOARD
# ======================================================
@user_passes_test(is_admin_user)
def admin_dashboard(request):
    """
    CLEAN ADMIN DASHBOARD

    ✔ No annotation conflicts
    ✔ Uses model logic
    ✔ Correct lifecycle classification
    """

    now = timezone.now()

    # ======================================================
    # MEMBERS
    # ======================================================


    members_total_members = Member.objects.count()

    members_active = Member.objects.filter(status=Member.STATUS_ACTIVE).count()
    members_pending = Member.objects.filter(status=Member.STATUS_PENDING).count()
    members_approved = Member.objects.filter(status=Member.STATUS_APPROVED).count()
    members_retired = Member.objects.filter(status=Member.STATUS_RETIRED).count()

    # ======================================================
    # CLAIMS
    # ======================================================
    received_claims = Claim.objects.filter(status="received").count()
    approved_claims = Claim.objects.filter(status="approved").count()
    open_claims = Claim.objects.filter(status="open").count()
    rejected_claims = Claim.objects.filter(status="rejected").count()
    settled_claims = Claim.objects.filter(status="settled").count()

    # ======================================================
    # PAYMENT REQUESTS
    # ======================================================
    payment_requests = PaymentRequest.objects.all()

    active_requests = []
    completed_requests = []
    in_progress_requests = []
    pending_requests = []

    for pr in payment_requests:

        # COMPLETED
        if pr.is_completed():
            completed_requests.append(pr)
            continue

        # EXPIRED → treated as completed already
        if pr.due_date < now:
            continue

        # IN PROGRESS
        if pr.total_paid > 0:
            in_progress_requests.append(pr)
        else:
            pending_requests.append(pr)

        # ACTIVE
        if pr.status == PaymentRequest.STATUS_ACTIVE:
            active_requests.append(pr)

    payment_requests_active = len(active_requests)
    completed_payment_requests = len(completed_requests)
    in_progress_requests_count = len(in_progress_requests)
    pending_requests_count = len(pending_requests)

    payment_requests_closed = PaymentRequest.objects.filter(
        status=PaymentRequest.STATUS_CLOSED
    ).count()

    # ======================================================
    # PAYMENTS
    # ======================================================
    completed_payments = Payment.objects.filter(
        status=Payment.STATUS_COMPLETED
    ).count()

    payments_waiting_confirmation = Payment.objects.filter(
        status=Payment.STATUS_PENDING,
        payment_method="manual"
    ).count()

    # ======================================================
    # ADMIN TASKS
    # ======================================================
    claims_waiting_approval = Claim.objects.filter(
        status="received"
    ).count()

    claims_ready_for_payment = Claim.objects.filter(
        status="approved",
        payment_request__isnull=True
    ).count()

    # ======================================================
    # CONTEXT
    # ======================================================
    context = {
        # ======================================================
        # MEMBERS
        # ======================================================

        "members_total_members": members_total_members,
        "members_active": members_active,
        "members_pending": members_pending,
        "members_approved": members_approved,
        "members_retired": members_retired,

        "received_claims": received_claims,
        "approved_claims": approved_claims,
        "open_claims": open_claims,
        "rejected_claims": rejected_claims,
        "settled_claims": settled_claims,

        "payment_requests_active": payment_requests_active,
        "payment_requests_closed": payment_requests_closed,
        "completed_payment_requests": completed_payment_requests,
        "in_progress_requests": in_progress_requests_count,
        "pending_requests": pending_requests_count,

        "completed_payments": completed_payments,
        "payments_waiting_confirmation": payments_waiting_confirmation,

        "claims_waiting_approval": claims_waiting_approval,
        "claims_ready_for_payment": claims_ready_for_payment,
    }

    # ======================================================
    # CHART DATA
    # ======================================================
    payments_by_day = (
        Payment.objects.filter(status=Payment.STATUS_COMPLETED)
        .annotate(day=TruncDate("paid_at"))
        .values("day")
        .annotate(total=Count("id"))
        .order_by("day")
    )

    chart_labels = [str(p["day"]) for p in payments_by_day]
    chart_values = [p["total"] for p in payments_by_day]
    
    return render(
        request,
        "members/admin/admin_dashboard.html",
        context
    ) 

    # ======================================================
    # CONTEXT
    # ======================================================
    context = {

        

        # CHART
        "chart_labels": chart_labels,
        "chart_values": chart_values,
    }

    return render(
        request,
        "members/admin/admin_dashboard.html",
        context
    )


@admin_required
def admin_payment_summary(request):
    """
    Dashboard: totals per request
    """

    requests = PaymentRequest.objects.all()

    data = []

    for req in requests:

        total_paid = Payment.objects.filter(
            payment_request=req,
            status="completed"
        ).count()

        total_members = (
            req.selected_members.count()
            if not req.viewable_by_all
            else Member.objects.filter(status="active").count()
        )

        total_pending = total_members - total_paid

        data.append({
            "request": req,
            "paid": total_paid,
            "pending": total_pending
        })

    return render(
        request,
        "members/admin/admin_payment_summary.html",
        {"data": data}
    )
