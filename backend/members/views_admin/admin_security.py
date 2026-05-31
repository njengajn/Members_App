from django.shortcuts import render
from backend.members.models import AuditLog, Member
from django.utils.timezone import now, timedelta


def admin_security_dashboard(request):

    last_24h = now() - timedelta(hours=24)

    logs = AuditLog.objects.filter(created_at__gte=last_24h)

    high_risk = logs.filter(
        action__in=[
            AuditLog.ACTION_PAYMENT_REJECTED,
            AuditLog.ACTION_MEMBER_STATUS,
        ]
    )

    locked_accounts = Member.objects.filter(status="locked")

    context = {
        "total_logs": logs.count(),
        "high_risk_count": high_risk.count(),
        "locked_accounts": locked_accounts,
        "recent_logs": logs[:20]
    }

    return render(request, "members/admin/security_dashboard.html", context)