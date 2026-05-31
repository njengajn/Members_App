# backend/members/services/event_handlers.py

"""
EVENT HANDLERS

SAFE:
✔ Can import business_rules
✔ Must NOT be imported by business_rules
"""


from backend.members.services.member_status_service import retire_member


def handle_claim_approved(claim, **kwargs):
    """
    When claim is approved → create payment request
    """

    # ✅ LAZY IMPORT (breaks circular dependency completely)
    from backend.members.services.business_rules import create_payment_request_from_claim

    create_payment_request_from_claim(claim)


def handle_payment_completed(payment, **kwargs):
    """
    When payment completes → move claim to 'open'
    """

    claim = getattr(payment.payment_request, "claim", None)

    if claim and claim.status == "approved":
        claim.status = "open"
        claim.save()


def handle_claim_settled(claim, **kwargs):
    """
    When claim settled → retire dependant/member
    """

    if claim.causer_dependant:
        claim.causer_dependant.status = "retired"
        claim.causer_dependant.save()
    else:
        member = claim.member
        retire_member(
            member,
            reason="Claim Settled"
        )
