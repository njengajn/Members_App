from django.shortcuts import render
from backend.members.models import Claim


def claims_list_admin(request):
    qs = Claim.objects.all().select_related("member")

    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)

    return render(
        request,
        "members/admin/admin_claims_list.html",
        {"claims": qs},
    )
    
def admin_claims_list(request):
    qs = Claim.objects.all().select_related("member")

    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)

    return render(
        request,
        "members/admin/admin_claims_list.html",
        {"claims": qs},
    )

