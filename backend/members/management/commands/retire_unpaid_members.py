from django.core.management.base import BaseCommand
from django.utils import timezone

from backend.members.models import PaymentRequest
from backend.members.services.payment_lifecycle import (
    process_reconciled_payment_request,
)


class Command(BaseCommand):
    """
    Process eligible annual subscription requests after June begins.

    Retirement eligibility and execution are delegated to the shared
    request-specific payment lifecycle service.
    """

    help = (
        "Process eligible overdue annual subscription requests "
        "through the shared payment lifecycle service."
    )

    def handle(self, *args, **kwargs):
        now = timezone.now()

        # Preserve the existing June onwards restriction.
        if now.month < 6:
            self.stdout.write(
                self.style.WARNING(
                    "Retirement period not reached."
                )
            )
            return

        # Preserve the existing current-calendar-year scope.
        # A missing request is not evidence of non-payment.
        requests = PaymentRequest.objects.filter(
            request_type="subscription",
            status=PaymentRequest.STATUS_CLOSED,
            is_reconciled=True,
            due_date__lt=now,
            due_date__year=now.year,
        ).order_by("id")

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
                "Annual subscription retirement processing completed. "
                f"Requests processed: {processed_count}; "
                f"requests skipped: {skipped_count}."
            )
        )