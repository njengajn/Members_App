from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.shortcuts import render
from django.contrib.auth.models import User
from backend.members.models import AuditLog, Member  
import csv
from django.http import HttpResponse

@staff_member_required
def admin_audit_logs(request):
    """
    Audit logs with filters
    """

    logs = AuditLog.objects.select_related("admin", "target_member", "payment").order_by("-created_at")

    # -------------------------
    # FILTERS
    # -------------------------
    admin_id = request.GET.get("admin")
    member_id = request.GET.get("member")
    action = request.GET.get("action")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    if admin_id:
        logs = logs.filter(admin_id=admin_id)

    if member_id:
        logs = logs.filter(target_member_id=member_id)

    if action:
        logs = logs.filter(action=action)

    if date_from:
        logs = logs.filter(created_at__date__gte=date_from)

    if date_to:
        logs = logs.filter(created_at__date__lte=date_to)
        
    paginator = Paginator(logs, 20)
    page = request.GET.get("page")

    logs = paginator.get_page(page)

    return render(request, "members/admin/audit_logs.html", {
        "logs": logs[:100],
        "admins": User.objects.filter(is_staff=True),
        "members": Member.objects.all()[:100],
        "actions": AuditLog.ACTION_CHOICES,
    })


@staff_member_required
def export_audit_logs(request):
    """
    Export audit logs to CSV
    """

    logs = AuditLog.objects.select_related("admin", "target_member", "payment")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="audit_logs.csv"'

    writer = csv.writer(response)
    writer.writerow(["Date", "Admin", "Member", "Action", "Message", "High Risk"])

    for log in logs:
        writer.writerow([
            log.created_at,
            log.admin,
            log.target_member,
            log.get_action_display(),
            log.message,
            log.is_high_risk
        ])

    return response