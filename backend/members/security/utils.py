# backend/members/security/utils.py

from django.utils import timezone
from datetime import timedelta

from backend.members.models import LoginAttempt, AccountLock, SecurityEvent


def get_client_ip(request):
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0]
    return request.META.get("REMOTE_ADDR")


def is_rate_limited(email):
    """
    Max 5 attempts in 10 minutes
    """
    window = timezone.now() - timedelta(minutes=10)

    attempts = LoginAttempt.objects.filter(
        email=email,
        created_at__gte=window
    ).count()

    return attempts >= 5


def record_login_attempt(request, user, email, success):
    ip = get_client_ip(request)

    LoginAttempt.objects.create(
        user=user,
        email=email,
        ip_address=ip,
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        success=success,
    )

    SecurityEvent.objects.create(
        user=user,
        event_type="login_success" if success else "login_failed",
        ip_address=ip,
    )


def check_account_locked(user):
    try:
        lock = AccountLock.objects.get(user=user)
        return lock.is_locked()
    except AccountLock.DoesNotExist:
        return False


def lock_account(user):
    from django.utils import timezone
    from datetime import timedelta

    lock_time = timezone.now() + timedelta(minutes=15)

    AccountLock.objects.update_or_create(
        user=user,
        defaults={
            "locked_until": lock_time,
            "reason": "Too many failed logins"
        }
    )

    SecurityEvent.objects.create(
        user=user,
        event_type="account_locked"
    )
    
