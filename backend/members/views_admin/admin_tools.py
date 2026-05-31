from django.shortcuts import render, redirect
from django.contrib import messages
from backend.members.models import Member
from .admin_auth import admin_required


@admin_required
def bulk_member_activation(request):

    if request.method == "POST":

        member_ids = request.POST.getlist("members")

        Member.objects.filter(
            id__in=member_ids
        ).update(status="active")

        messages.success(
            request,
            f"{len(member_ids)} members activated."
        )

        return redirect("members_admin:bulk_member_activation")

    pending_members = Member.objects.filter(status="pending")

    return render(
        request,
        "members/admin/admin_bulk_member_activation.html",
        {"members": pending_members},
    )
