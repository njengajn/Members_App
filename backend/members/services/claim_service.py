from django.db import transaction
from backend.members.models import Claim, PaymentRequest
from django.utils import timezone
from django.core.exceptions import ValidationError
from backend.members.models import Claim, PaymentRequest, AuditLog, ClaimRecord, Member, Dependant
from django.core.exceptions import PermissionDenied, ValidationError


@transaction.atomic


class ClaimService:
    """
    Central authority for all claim state transitions.
    Views MUST call this instead of changing status directly.
    """

    @staticmethod
    @transaction.atomic
    def approve_claim(claim: Claim, *, by_user):
        """
        Approve a RECEIVED claim → OPEN
        """
        if claim.status != Claim.STATUS_RECEIVED:
            raise ValidationError("Only received claims can be approved.")

        claim.status = Claim.STATUS_OPEN
        claim.save(update_fields=["status"])

        ClaimService._ensure_claim_record(claim)

    @staticmethod
    @transaction.atomic
    def settle_claim(claim: Claim, *, by_user):
        """
        Settle an OPEN claim → SETTLED
        """
        if claim.status != Claim.STATUS_OPEN:
            raise ValidationError("Only open claims can be settled.")

        claim.status = Claim.STATUS_SETTLED
        claim.save(update_fields=["status"])

        ClaimService._apply_settlement_rules(claim)

    # -----------------------------
    # INTERNAL HELPERS
    # -----------------------------

    @staticmethod
    def _ensure_claim_record(claim: Claim):
        if hasattr(claim, "record"):
            return

        if claim.cause_type == Claim.CLAIM_CAUSER_MEMBER:
            causer_name = str(
                claim.member.user.get_full_name()
                or claim.member.user.username
            )
        elif claim.cause_type == Claim.CLAIM_CAUSER_DEPENDANT and claim.causer_dependant:
            causer_name = claim.causer_dependant.full_name
        else:
            causer_name = claim.claimer

        ClaimRecord.objects.create(
            claim=claim,
            causer_name=causer_name,
            claimant=claim.member,
        )

    @staticmethod
    def _apply_settlement_rules(claim: Claim):
        record = getattr(claim, "record", None)
        if record and not record.settlement_date:
            record.settlement_date = timezone.now()
            record.save(update_fields=["settlement_date"])

        if claim.cause_type == Claim.CLAIM_CAUSER_MEMBER:
            member = claim.member
            member.status = Member.STATUS_RETIRED
            member.save(update_fields=["status"])

            member.dependants.update(status=Dependant.STATUS_RETIRED)

        elif claim.cause_type == Claim.CLAIM_CAUSER_DEPENDANT:
            dep = claim.causer_dependant
            if dep:
                dep.status = Dependant.STATUS_RETIRED
                dep.save(update_fields=["status"])


