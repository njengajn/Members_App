# backend/members/views_admin/security_dashboard.py

from django.shortcuts import render
from backend.members.models import SecurityEvent


def security_dashboard(request):

    events = SecurityEvent.objects.order_by("-created_at")[:100]

    return render(
        request,
        "members/admin/security_dashboard.html",
        {"events": events},
    )