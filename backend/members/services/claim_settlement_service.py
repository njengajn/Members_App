from urllib import request

from django.utils import timezone
from backend.members.models import Claim, Dependant, MembershipStatusHistory
from backend.members.services.member_status_service import retire_member


def settle_claim(claim):
    """
    Applies business rules after a claim payout.

    1. Mark claim as settled
    2. Retire dependant OR member
    """

    if claim.status == Claim.STATUS_SETTLED:
        return

    # ---------------------------------------
    # MARK CLAIM SETTLED
    # ---------------------------------------

    claim.status = Claim.STATUS_SETTLED
    claim.settled_at = timezone.now()
    claim.save()


    # --------------------------------------------------
    # CLAIM CAUSED BY DEPENDANT
    # --------------------------------------------------

    if claim.cause_type == Claim.CLAIM_CAUSER_DEPENDANT:

        dependant = claim.causer_dependant

        if dependant:
            dependant.status = Dependant.STATUS_RETIRED
            dependant.save()

    # --------------------------------------------------
    # CLAIM CAUSED BY MEMBER
    # --------------------------------------------------

    if claim.cause_type == Claim.CLAIM_CAUSER_MEMBER:

        member = claim.member

        retire_member(
            member,
            reason="Claim Settled"
        )
        
