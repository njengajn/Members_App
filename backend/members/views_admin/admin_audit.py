from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.shortcuts import render
from django.contrib.auth.models import User
from backend.members.models import AuditLog, Member  
import csv
from django.http import HttpResponse
from urllib.parse import urlencode
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import permission_required
from ..models import AuditLog, Member

User = get_user_model()

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

# ==========================================================
# AUDIT & ACTIVITY LOG
# ==========================================================

@permission_required(
    "members.can_view_audit_logs",
    raise_exception=True,
)
def admin_activity_log(request):
    """
    Display the central Audit & Activity page.

    Supports filtering by:

        - Administrator
        - Member
        - Action
        - Risk level
        - Date from
        - Date to

    Results are filtered first and then paginated.

    The template receives only the filtered Page object.
    """

    # ------------------------------------------------------
    # BASE QUERYSET
    # ------------------------------------------------------

    logs = (
        AuditLog.objects
        .select_related(
            "admin",
            "target_member",
            "payment",
        )
        .order_by("-created_at")
    )

    # ------------------------------------------------------
    # READ FILTER VALUES
    # ------------------------------------------------------

    admin_id = request.GET.get(
        "admin",
        "",
    ).strip()

    member_id = request.GET.get(
        "member",
        "",
    ).strip()

    action = request.GET.get(
        "action",
        "",
    ).strip()

    date_from = request.GET.get(
        "date_from",
        "",
    ).strip()

    date_to = request.GET.get(
        "date_to",
        "",
    ).strip()

    risk = request.GET.get(
        "risk",
        "",
    ).strip()

    # ------------------------------------------------------
    # ADMINISTRATOR FILTER
    # ------------------------------------------------------

    if admin_id:
        logs = logs.filter(
            admin_id=admin_id
        )

    # ------------------------------------------------------
    # MEMBER FILTER
    # ------------------------------------------------------

    if member_id:
        logs = logs.filter(
            target_member_id=member_id
        )

    # ------------------------------------------------------
    # ACTION FILTER
    # ------------------------------------------------------

    if action:
        logs = logs.filter(
            action=action
        )

    # ------------------------------------------------------
    # DATE FROM FILTER
    # ------------------------------------------------------

    if date_from:
        logs = logs.filter(
            created_at__date__gte=date_from
        )

    # ------------------------------------------------------
    # DATE TO FILTER
    # ------------------------------------------------------

    if date_to:
        logs = logs.filter(
            created_at__date__lte=date_to
        )

    # ------------------------------------------------------
    # RISK FILTER
    # ------------------------------------------------------

    if risk == "high":

        logs = logs.filter(
            is_high_risk=True
        )

    elif risk == "normal":

        logs = logs.filter(
            is_high_risk=False
        )

    # ------------------------------------------------------
    # PAGINATION
    # ------------------------------------------------------
    #
    # Filtering is completed BEFORE pagination.
    #
    # Do not slice page_obj afterwards.
    #

    paginator = Paginator(
        logs,
        20,
    )

    page_number = request.GET.get(
        "page"
    )

    page_obj = paginator.get_page(
        page_number
    )

    # ------------------------------------------------------
    # FILTER OPTIONS
    # ------------------------------------------------------
    #
    # IMPORTANT:
    # Member uses member_uid, not uid.
    #

    admins = (
        User.objects
        .filter(is_staff=True)
        .order_by(
            "first_name",
            "last_name",
            "username",
        )
    )

    members = (
        Member.objects
        .order_by("member_uid")[:100]
    )

    # ------------------------------------------------------
    # PRESERVE FILTERS DURING PAGINATION
    # ------------------------------------------------------

    filter_params = {
        "admin": admin_id,
        "member": member_id,
        "action": action,
        "risk": risk,
        "date_from": date_from,
        "date_to": date_to,
    }

    filter_params = {
        key: value
        for key, value in filter_params.items()
        if value
    }

    filter_query = urlencode(
        filter_params
    )

    # ------------------------------------------------------
    # RENDER
    # ------------------------------------------------------

    return render(
        request,
        "members/admin/admin_activity_log.html",
        {
            "logs": page_obj,

            "admins": admins,

            "members": members,

            "actions": AuditLog.ACTION_CHOICES,

            "selected_admin": admin_id,

            "selected_member": member_id,

            "selected_action": action,

            "selected_date_from": date_from,

            "selected_date_to": date_to,

            "selected_risk": risk,

            "filter_query": filter_query,
        },
    )


# ==========================================================
# EXPORT AUDIT LOGS
# ==========================================================

@permission_required(
    "members.can_export_audit_logs",
    raise_exception=True,
)
def export_audit_logs(request):
    """
    Export filtered Audit & Activity records as CSV.

    The same filters used by admin_activity_log() are
    applied here so that the CSV contains the records
    represented by the current filter selection.
    """

    # ------------------------------------------------------
    # BASE QUERYSET
    # ------------------------------------------------------

    logs = (
        AuditLog.objects
        .select_related(
            "admin",
            "target_member",
            "payment",
        )
        .order_by("-created_at")
    )

    # ------------------------------------------------------
    # READ FILTER VALUES
    # ------------------------------------------------------

    admin_id = request.GET.get(
        "admin",
        "",
    ).strip()

    member_id = request.GET.get(
        "member",
        "",
    ).strip()

    action = request.GET.get(
        "action",
        "",
    ).strip()

    date_from = request.GET.get(
        "date_from",
        "",
    ).strip()

    date_to = request.GET.get(
        "date_to",
        "",
    ).strip()

    risk = request.GET.get(
        "risk",
        "",
    ).strip()

    # ------------------------------------------------------
    # APPLY ADMINISTRATOR FILTER
    # ------------------------------------------------------

    if admin_id:
        logs = logs.filter(
            admin_id=admin_id
        )

    # ------------------------------------------------------
    # APPLY MEMBER FILTER
    # ------------------------------------------------------

    if member_id:
        logs = logs.filter(
            target_member_id=member_id
        )

    # ------------------------------------------------------
    # APPLY ACTION FILTER
    # ------------------------------------------------------

    if action:
        logs = logs.filter(
            action=action
        )

    # ------------------------------------------------------
    # APPLY DATE FROM FILTER
    # ------------------------------------------------------

    if date_from:
        logs = logs.filter(
            created_at__date__gte=date_from
        )

    # ------------------------------------------------------
    # APPLY DATE TO FILTER
    # ------------------------------------------------------

    if date_to:
        logs = logs.filter(
            created_at__date__lte=date_to
        )

    # ------------------------------------------------------
    # APPLY RISK FILTER
    # ------------------------------------------------------

    if risk == "high":

        logs = logs.filter(
            is_high_risk=True
        )

    elif risk == "normal":

        logs = logs.filter(
            is_high_risk=False
        )

    # ------------------------------------------------------
    # CREATE CSV RESPONSE
    # ------------------------------------------------------

    response = HttpResponse(
        content_type="text/csv"
    )

    response["Content-Disposition"] = (
        'attachment; filename="audit_logs.csv"'
    )

    writer = csv.writer(response)

    # ------------------------------------------------------
    # CSV HEADER
    # ------------------------------------------------------

    writer.writerow(
        [
            "Date",
            "Admin",
            "Member",
            "Action",
            "Description",
            "High Risk",
        ]
    )

    # ------------------------------------------------------
    # CSV DATA
    # ------------------------------------------------------

    for log in logs:

        writer.writerow(
            [
                log.created_at,
                log.admin or "",
                log.target_member or "",
                log.get_action_display(),
                getattr(
                    log,
                    "description",
                    "",
                ),
                (
                    "Yes"
                    if log.is_high_risk
                    else "No"
                ),
            ]
        )

    return response