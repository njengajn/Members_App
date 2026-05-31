from django.core.management.base import BaseCommand
from django.utils import timezone
from backend.members.models import PaymentRequest, MemberPaymentStatus, Member
from backend.members.models import Notification

class Command(BaseCommand):
    help = "Retire members who haven't paid for paymentrequests past due date"

    def handle(self, *args, **options):
        now = timezone.now()
        expired_requests = PaymentRequest.objects.filter(due_date__lt=now)
        for pr in expired_requests:
            # find unpaid member statuses for this payment request
            unpaid_statuses = MemberPaymentStatus.objects.filter(payment_request=pr, status=MemberPaymentStatus.STATUS_UNPAID)
            for mps in unpaid_statuses.select_related('member'):
                member = mps.member
                if member.status != Member.STATUS_RETIRED:
                    # retire member and optionally any dependants (implement your dependant retire logic)
                    member.status = Member.STATUS_RETIRED
                    member.save()
                    self.stdout.write(f"Retired member {member} for missed payment on {pr}")