from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test

from backend.members.models import Member
from backend.members.services.admin_actions import (
    restore_member,
    retire_member_manually
)


def admin_required(user):
    return user.is_authenticated and user.is_staff


# ==========================================================
# RESTORE MEMBER (VIEW)
# ==========================================================
@user_passes_test(admin_required)
def restore_member_view(request, member_id):

    member = get_object_or_404(
        Member,
        id=member_id
    )

    reason = request.GET.get(
        "reason",
        "Member restored by administrator"
    )

    restore_member(
        member,
        admin_user=request.user,
        reason=reason,
    )

    messages.success(
        request,
        "Member restored successfully."
    )

    return redirect("members_admin:admin_member_detail", member_id=member.id)


# ==========================================================
# RETIRE MEMBER (VIEW)
# ==========================================================
@user_passes_test(admin_required)
def retire_member_view(request, member_id):

    member = get_object_or_404(Member, id=member_id)

    reason = request.GET.get("reason", "manual_admin_action")

    retire_member_manually(
        member,
        admin_user=request.user,
        reason=reason
    )

    messages.success(request, "Member retired successfully.")

    return redirect("members_admin:admin_member_detail", member_id=member.id)