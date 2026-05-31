# backend/members/management/commands/expire_payment_requests.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from backend.members.models import PaymentRequest, Payment, Member

class Command(BaseCommand):
    help = "Mark unpaid members as retired for PaymentRequests whose due_date has passed."

    def handle(self, *args, **options):
        now = timezone.now()
        prs = PaymentRequest.objects.filter(status=PaymentRequest.STATUS_ACTIVE, due_date__lt=now)
        for pr in prs:
            # get members who should have paid (either all or selected_members)
            if pr.viewable_by_all:
                # all active members expected
                members = Member.objects.filter(status=Member.STATUS_ACTIVE)
            else:
                members = pr.selected_members.filter(status=Member.STATUS_ACTIVE)

            paid_member_ids = set(pr.payments.values_list("member_id", flat=True))
            for member in members:
                if member.id not in paid_member_ids:
                    member.status = Member.STATUS_RETIRED
                    member.save(update_fields=["status"])
                    self.stdout.write(f"Retired member {member} for unpaid request {pr.id}")

            # optionally mark request closed after processing
            pr.status = PaymentRequest.STATUS_CLOSED
            PaymentRequest.objects.filter(id=pr.id).update(status=PaymentRequest.STATUS_CLOSED)
            self.stdout.write(f"Processed PaymentRequest {pr.id}")
