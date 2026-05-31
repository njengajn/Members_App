from django.http import JsonResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Q

from backend.members.models import Member


@staff_member_required
def admin_member_search(request):
    """
    AJAX MEMBER SEARCH (SCALABLE)

    ✔ supports:
        - first name
        - surname
        - member_uid
    ✔ limited results for performance
    """

    q = request.GET.get("q", "").strip()

    results = []

    if q:
        members = (
            Member.objects
            .filter(status="active")
            .filter(
                Q(first_name__icontains=q) |
                Q(surname__icontains=q) |
                Q(member_uid__icontains=q)
            )
            .order_by("first_name")[:20]  # LIMIT for performance
        )

        for m in members:
            results.append({
                "id": m.id,
                "name": f"{m.first_name} {m.surname}",
                "uid": m.member_uid,
            })

    return JsonResponse({"results": results})