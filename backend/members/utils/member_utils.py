from django.utils import timezone
from backend.members.models import Member

def expire_member_edit_permissions():
    """
    Runs periodically (cron safe)
    """

    members = Member.objects.filter(
        can_edit=True,
        can_edit_expires_at__isnull=False
    )

    for m in members:
        if timezone.now() > m.can_edit_expires_at:
            m.disable_can_edit()
            
