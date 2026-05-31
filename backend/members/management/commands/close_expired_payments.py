from django.core.management.base import BaseCommand
from backend.members.utils.payments import auto_close_expired_payments
from backend.members.models import Notification

class Command(BaseCommand):
    help = "Close expired payment requests"

    def handle(self, *args, **kwargs):
        count = auto_close_expired_payments()
        self.stdout.write(self.style.SUCCESS(f"Closed {count} expired payments"))