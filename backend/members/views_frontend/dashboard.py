from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.utils import timezone

from backend.members.decorators import member_required
from backend.members.models import (
    PaymentRequest,
    Payment,
    NextOfKin
)


@login_required
@member_required
def member_dashboard(request):
    member = request.user.member
    member.check_can_edit_expiry()

    # ======================================================
    # PAYMENT REQUESTS
    # ======================================================
    payment_requests = (
        PaymentRequest.objects
        .filter(
            Q(viewable_by_all=True) |
            Q(member=member) |
            Q(selected_members=member)
        )
        .prefetch_related("payments", "paid_members")
        .distinct()
        .order_by("-created_at")[:5]
    )

    now = timezone.now()

    # ======================================================
    # PRECOMPUTE STATE (FINAL FIX)
    # ======================================================
    for req in payment_requests:

        # --------------------------------------
        # FORCE USE OF PREFETCHED DATA (NO DB FILTER BUG)
        # --------------------------------------
        member_payments = [
            p for p in req.payments.all()
            if p.member_id == member.id
        ]

        # --------------------------------------
        # STATUS FLAGS (ORDER MATTERS)
        # --------------------------------------
        req.is_pending = any(p.status == Payment.STATUS_PENDING for p in member_payments)

        req.is_paid = any(p.status == Payment.STATUS_COMPLETED for p in member_payments)

        # --------------------------------------
        # CRITICAL: pending overrides everything
        # --------------------------------------
        if req.is_pending:
            req.is_paid = False

        # --------------------------------------
        # OVERDUE (ONLY IF NOT PAID OR PENDING)
        # --------------------------------------
        req.is_overdue_member = (
            not req.is_paid
            and not req.is_pending
            and req.due_date
            and req.due_date < now
        )

        # --------------------------------------
        # ENDING SOON (48 HOURS)
        # --------------------------------------
        req.is_ending_soon = (
            not req.is_paid
            and not req.is_pending
            and not req.is_overdue_member
            and req.due_date
            and (req.due_date - now).total_seconds() <= 172800
        )

    # ======================================================
    # SUPPORT DATA
    # ======================================================
    dependants = member.dependants.all()

    next_of_kin = (
        NextOfKin.objects
        .filter(member=member)
        .first()
    )

    recent_payments = (
        Payment.objects
        .filter(member=member)
        .order_by("-paid_at")[:5]
    )

    recent_claims = (
        member.claims
        .select_related("causer_dependant")
        .order_by("-created_at")[:5]
    )

    # ======================================================
    # CONTEXT
    # ======================================================
    context = {
        "member": member,
        "dependants": dependants,
        "next_of_kin": next_of_kin,
        "recent_payments": recent_payments,
        "recent_claims": recent_claims,

        # Dashboard shows latest 5
        "payment_requests": payment_requests[:30],
        "unpaid_count": payment_requests.count(),
    }

    return render(
        request,
        "members/dashboard/members_dashboard.html",
        context
    )