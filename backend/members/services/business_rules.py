from decimal import Decimal

from backend.members.services.domain_events import dispatch_event
from django.utils import timezone
from django.db.models import Q
from backend.members.models import (
    Claim,
    Payment,
    PaymentRequest,
    Member,
    Dependant,
    MembershipStatusHistory
)

"""
Business Rules Engine

Centralizes ALL business rules for:

• Claim lifecycle
• Payment request generation
• Payment validation
• Member / dependant retirement rules
• Compliance checks

Views should call this service instead of implementing logic.
"""

# ==========================================================
# CLAIM LIFECYCLE RULES
# ==========================================================

VALID_CLAIM_TRANSITIONS = {

    "received": ["approved", "rejected"],

    "approved": ["open"],

    "open": ["settled"],

    "settled": [],

    "rejected": []
}


def can_transition_claim(claim, new_status):
    """
    Prevent invalid lifecycle transitions.
    """

    allowed = VALID_CLAIM_TRANSITIONS.get(claim.status, [])

    return new_status in allowed

# ==========================================================
# APPROVE CLAIM
# ==========================================================

def approve_claim(claim):

    if not can_transition_claim(claim, "approved"):
        raise ValueError("Invalid claim lifecycle transition")

    claim.status = "approved"
    claim.save()

    dispatch_event(
        "claim_approved",
        {"claim": claim}
    )

    return claim

# ==========================================================
# CREATE PAYMENT REQUEST
# ==========================================================



# ==========================================================
# MEMBER PAYMENT REQUEST LIST
# ==========================================================

def get_member_payment_requests(member):
    """
    Returns payment requests visible to member.

    Includes:
    • member specific requests
    • global requests
    """

    return PaymentRequest.objects.filter(
        status="active"
    ).filter(
        Q(member=member) | Q(member__isnull=True)
    ).order_by("-created_at")


# ==========================================================
# RECORD PAYMENT
# ==========================================================

# ==========================================================
# CLAIM SETTLEMENT RULES
# ==========================================================

def settle_claim(payment_request):
    """
    Treasurer settles a claim.

    Rules:
    • dependant claim → retire dependant
    • member claim → retire member + dependants
    """

    claim = payment_request.claim

    if not claim:
        raise ValueError("Payment request not linked to claim")

    claim.status = "settled"
    claim.save()

    member = claim.member

    # dependant claim
    if claim.causer_dependant:

        dependant = claim.causer_dependant

        dependant.status = Dependant.STATUS_RETIRED
        dependant.save()

    else:

        from members.services.member_status_service import retire_member

        retire_member(
            member,
            reason="Claim Settled",
        )
    dispatch_event(
        "claim_settled",
        {"claim": claim}
    )

    payment_request.status = "closed"
    payment_request.save()

    return claim

# ==========================================================
# COMPLIANCE TRACKER
# ==========================================================

def get_payment_compliance(payment_request):

    members = Member.objects.filter(status="active")

    paid_members = Payment.objects.filter(
        payment_request=payment_request
    ).values_list("member_id", flat=True)

    paid = members.filter(id__in=paid_members)

    unpaid = members.exclude(id__in=paid_members)

    compliance = 0

    if members.count() > 0:

        compliance = round(
            paid.count() / members.count() * 100,
            2
        )

    return {

        "paid_members": paid,
        "unpaid_members": unpaid,
        "compliance_rate": compliance
    }



