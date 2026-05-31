from django.http import JsonResponse
from django.views.decorators.http import require_POST
from backend.members.models import Member, PaymentRequest
from django.db.models import Q


def admin_search_members(request):
    """
    AJAX endpoint → Search members by name, email, phone, or ID.
    """
    query = request.GET.get("q", "").strip()

    if not query:
        return JsonResponse({"status": "error", "message": "Search query required."}, status=400)

    members = Member.objects.filter(
        Q(full_name__icontains=query) |
        Q(email__icontains=query) |
        Q(phone__icontains=query) |
        Q(id_number__icontains=query)
    ).values("id", "full_name", "email", "phone", "id_number")[:20]

    return JsonResponse({
        "status": "ok",
        "count": len(members),
        "results": list(members)
    })


@require_POST
def admin_update_payment_status(request):
    """
    AJAX endpoint → Update payment request status (Pending, Approved, Rejected).
    """
    request_id = request.POST.get("request_id")
    new_status = request.POST.get("status")

    if not request_id or not new_status:
        return JsonResponse({"status": "error", "message": "Missing parameters."}, status=400)

    try:
        payment = PaymentRequest.objects.get(id=request_id)
    except PaymentRequest.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Payment not found."}, status=404)

    if new_status not in ["Pending", "Approved", "Rejected"]:
        return JsonResponse({"status": "error", "message": "Invalid status."}, status=400)

    payment.status = new_status
    payment.save()

    return JsonResponse({
        "status": "ok",
        "message": "Payment status updated.",
        "payment_id": payment.id,
        "new_status": new_status
    })
