from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from members.models import EmailOTP


class Command(BaseCommand):
    help = "Delete expired OTPs"

    def handle(self, *args, **kwargs):

        expiry_time = timezone.now() - timedelta(minutes=5)

        deleted, _ = EmailOTP.objects.filter(
            created_at__lt=expiry_time
        ).delete()

        self.stdout.write(f"Deleted {deleted} expired OTPs")
        
