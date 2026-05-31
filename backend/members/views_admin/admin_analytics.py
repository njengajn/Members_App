from django.shortcuts import render
from django.db.models import Count, Sum
from backend.members.models import Member, Claim, Payment, PaymentRequest
from .admin_auth import admin_required


@admin_required
def admin_analytics_dashboard(request):
    """
    Admin analytics dashboard.

    Displays system statistics:
    - Member status distribution
    - Claims lifecycle
    - Payments totals
    - Payment request totals
    """

    # Member statistics
    member_stats = Member.objects.values("status").annotate(
        total=Count("id")
    )

    # Claims statistics
    claim_stats = Claim.objects.values("status").annotate(
        total=Count("id")
    )

    # Payment totals
    payments_total = Payment.objects.aggregate(
        total_amount=Sum("amount")
    )

    # Payment request totals
    request_stats = PaymentRequest.objects.values("status").annotate(
        total=Count("id")
    )

    context = {
        "member_stats": list(member_stats),
        "claim_stats": list(claim_stats),
        "request_stats": list(request_stats),
        "payments_total": payments_total,
    }

    return render(
        request,
        "members/admin/admin_analytics_dashboard.html",
        context
    )
