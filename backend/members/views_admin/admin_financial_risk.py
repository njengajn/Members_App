from django.shortcuts import render
from django.db.models import Sum, Count
from django.utils.timezone import now
from backend.members.models import Payment, Claim, Member, PaymentRequest
from .admin_auth import admin_required
import csv
from django.http import HttpResponse


@admin_required
def financial_risk_monitor(request):
    """
    Treasurer financial risk monitoring panel.
    """

    # ---------------------------------
    # TOTAL FUNDS COLLECTED
    # ---------------------------------

    total_funds = (
        Payment.objects
        .filter(status="completed")
        .aggregate(total=Sum("amount"))
        ["total"] or 0
    )

    # ---------------------------------
    # PROJECTED LIABILITIES
    # ---------------------------------

    projected_liabilities = (
        Claim.objects
        .filter(status__in=["approved", "open"])
        .aggregate(total=Sum("amount"))
        ["total"] or 0
    )

    # ---------------------------------
    # RESERVE RATIO
    # ---------------------------------

    if projected_liabilities > 0:
        reserve_ratio = round(total_funds / projected_liabilities, 2)
    else:
        reserve_ratio = 0

    # ---------------------------------
    # FUTURE CLAIM EXPOSURE
    # ---------------------------------

    active_members = Member.objects.filter(status="active").count()

    # simple actuarial assumption
    estimated_claim_rate = 0.05

    average_claim_amount = (
        Claim.objects.aggregate(avg=Sum("amount"))["avg"] or 0
    )

    future_claim_exposure = (
        active_members * estimated_claim_rate * average_claim_amount
    )

    # ---------------------------------
    # PAYMENT DEFAULT RISK
    # ---------------------------------

    active_requests = PaymentRequest.objects.filter(status="active")

    members_with_requests = (
        Member.objects
        .filter(paymentrequest__in=active_requests)
        .distinct()
        .count()
    )

    members_paid = (
        Payment.objects
        .filter(payment_request__in=active_requests, status="completed")
        .values("member")
        .distinct()
        .count()
    )

    if members_with_requests > 0:
        payment_default_risk = round(
            (members_with_requests - members_paid) /
            members_with_requests * 100
        )
    else:
        payment_default_risk = 0

    context = {

        "total_funds": total_funds,
        "projected_liabilities": projected_liabilities,
        "reserve_ratio": reserve_ratio,
        "future_claim_exposure": round(future_claim_exposure, 2),
        "payment_default_risk": payment_default_risk,
    }

    return render(
        request,
        "members/admin/treasurer_financial_risk.html",
        context
    )


@admin_required
def export_financial_risk_csv(request):

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=risk_report.csv"

    writer = csv.writer(response)

    writer.writerow([
        "Metric",
        "Value"
    ])

    # same calculations as dashboard

    total_funds = Payment.objects.filter(
        status="completed"
    ).aggregate(total=Sum("amount"))["total"] or 0

    liabilities = Claim.objects.filter(
        status__in=["approved", "open"]
    ).aggregate(total=Sum("amount"))["total"] or 0

    writer.writerow(["Total Funds", total_funds])
    writer.writerow(["Projected Liabilities", liabilities])

    return response

