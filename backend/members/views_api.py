from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator

from .models import Member
import json


# --- List Members ---
@login_required
def api_member_list(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    members = Member.objects.all().values(
        "id",
        "full_name",
        "phone",
        "email",
        "status",
        "joined_at",
    )

    return JsonResponse({"members": list(members)}, safe=False)


# --- Member Detail ---
@login_required
def api_member_detail(request, member_id):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    try:
        member = Member.objects.values(
            "id",
            "full_name",
            "phone",
            "email",
            "status",
            "joined_at",
        ).get(id=member_id)
    except Member.DoesNotExist:
        return JsonResponse({"error": "Member not found"}, status=404)

    return JsonResponse(member, safe=False)


# --- Update Member Status ---
@csrf_exempt
@login_required
def api_update_status(request, member_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    try:
        data = json.loads(request.body)
        new_status = data.get("status")

        if new_status not in ["pending", "active", "retired"]:
            return HttpResponseBadRequest("Invalid status")

        member = Member.objects.get(id=member_id)
        member.status = new_status
        member.save()

        return JsonResponse({"success": True, "new_status": new_status})

    except Member.DoesNotExist:
        return JsonResponse({"error": "Member not found"}, status=404)
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")
