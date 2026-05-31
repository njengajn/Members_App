from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from backend.members.models import Member
from backend.members.views import is_admin


@user_passes_test(is_admin)
def members(request, member_id):
    member = get_object_or_404(Member, pk=member_id)

    return render(
        request,
        "members/admin/admin_member_detail.html",
        {"member": member}
    )


def verify_member(request, token):
    """
    Public QR verification endpoint.
    """

    member = get_object_or_404(
        Member,
        verification_token=token
    )

    verification_status = "invalid"

    # =====================================
    # ACTIVE VALID MEMBER
    # =====================================

    if member.is_valid():

        verification_status = "valid"

    # =====================================
    # RETIRED MEMBER
    # =====================================

    elif member.status == Member.STATUS_RETIRED:

        verification_status = "retired"

    return render(
        request,
        "members/verify.html",
        {
            "member": member,
            "verification_status": verification_status,
        }
    )


def verify_memberOnHold13_05_26(request, token):
    """
    QR verification endpoint.
    """

    member = get_object_or_404(
        Member,
        verification_token=token
    )

    verification_status = "invalid"

    # =====================================
    # ACTIVE VALID MEMBER
    # =====================================

    if member.is_valid():

        verification_status = "valid"

    # =====================================
    # RETIRED MEMBER
    # =====================================

    elif member.status == Member.STATUS_RETIRED:

        verification_status = "retired"

    return render(
        request,
        "members/verify.html",
        {
            "member": member,
            "verification_status": verification_status,
        }
    )