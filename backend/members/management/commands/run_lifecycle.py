from django.core.management.base import BaseCommand

from backend.members.services.payment_lifecycle import (
    process_payment_lifecycle,
)


class Command(BaseCommand):
    help = "Run payment lifecycle processing"

    def handle(self, *args, **kwargs):
        process_payment_lifecycle()
        self.stdout.write("Lifecycle processed successfully")