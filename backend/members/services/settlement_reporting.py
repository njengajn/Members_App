"""
Settlement reporting service.

Provides:
- Contribution breakdown
- Reconciliation
- Ledger export
"""

from decimal import Decimal
from django.db.models import Sum
from backend.members.models import Payment


def get_claim_payment_request(claim):
    """
    Safely fetch the payment request linked to a claim.
    """
    return getattr(claim, "payment_request", None)


def get_contribution_breakdown(claim):
    """
    Returns per-member contribution details.
    """

    pr = get_claim_payment_request(claim)

    if not pr:
        return []

    payments = (
        Payment.objects.filter(
            payment_request=pr,
            status=Payment.STATUS_COMPLETED,
        )
        .select_related("member")
        .order_by("paid_at")
    )

    breakdown = []

    for p in payments:
        breakdown.append({
            "member": p.member,
            "member_name": p.full_name_snapshot,
            "member_uid": p.member_uid_snapshot,
            "amount": p.amount,
            "date": p.paid_at,
            "method": p.payment_method,
        })

    return breakdown


def get_reconciliation_summary(claim):
    """
    Validates financial consistency.
    """

    pr = get_claim_payment_request(claim)

    if not pr:
        return {}

    total = (
        Payment.objects.filter(
            payment_request=pr,
            status=Payment.STATUS_COMPLETED,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    payment_count = Payment.objects.filter(
        payment_request=pr,
        status=Payment.STATUS_COMPLETED,
    ).count()

    unique_members = Payment.objects.filter(
        payment_request=pr,
        status=Payment.STATUS_COMPLETED,
    ).values("member").distinct().count()

    return {
        "total_collected": total,
        "payment_count": payment_count,
        "unique_payers": unique_members,
        "matches_request_total": total == pr.total_paid,
    }


def generate_ledger_rows(claim):
    """
    Generates ledger rows for export.
    """

    pr = get_claim_payment_request(claim)

    if not pr:
        return []

    payments = Payment.objects.filter(
        payment_request=pr,
        status=Payment.STATUS_COMPLETED,
    ).select_related("member")

    rows = []

    for p in payments:
        rows.append([
            str(p.paid_at),
            p.member_uid_snapshot,
            p.full_name_snapshot,
            str(p.amount),
            p.payment_method,
            p.external_payment_id or "MANUAL",
        ])

    return rows