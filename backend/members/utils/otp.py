from datetime import timedelta
from django.utils import timezone
from backend.members.models import EmailOTP


def can_send_otp(email):
    """
    Limit: 3 OTPs per 5 minutes
    """
    window = timezone.now() - timedelta(minutes=5)

    return EmailOTP.objects.filter(
        email=email,
        created_at__gte=window
    ).count() < 3
    
    
import random

def generate_otp():
    return str(random.randint(100000, 999999))