from django.core.management.base import BaseCommand
from django.utils import timezone

from backend.members.models import PaymentRequest
from backend.members.services.payment_lifecycle import (
    process_reconciled_payment_request,
)


class Command(BaseCommand):
    help = (
        "Process eligible overdue subscription requests "
        "through the shared payment lifecycle service."
    )

    @staticmethod
    def get_eligible_requests(now):
        """
        Select only requests eligible for automatic subscription
        retirement processing. The shared service performs the
        final eligibility checks for each member.
        """
        return PaymentRequest.objects.filter(
            request_type="subscription",
            status=PaymentRequest.STATUS_CLOSED,
            is_reconciled=True,
            due_date__lt=now,
        ).order_by("id")

    def handle(self, *args, **options):
        now = timezone.now()
        requests = self.get_eligible_requests(now)

        processed_count = 0
        skipped_count = 0

        for payment_request in requests.iterator():
            processed = process_reconciled_payment_request(
                request_id=payment_request.id,
                performed_by=None,
            )

            if processed:
                processed_count += 1
            else:
                skipped_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Subscription retirement processing completed. "
                f"Requests processed: {processed_count}; "
                f"requests skipped: {skipped_count}."
            )
        )