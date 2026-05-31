# backend/members/context_processors.py
from django.conf import settings

def user_role_context(request):
    """
    Adds `user_role` and `is_member_registered` to every template.
    Roles:
      - admin  -> request.user.is_staff
      - member -> authenticated & has Member record
      - unregistered -> authenticated but no Member record
      - anonymous -> not authenticated
    """
    role = "anonymous"
    is_member_registered = False

    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        if user.is_staff:
            role = "admin"
        else:
            # check for Member objects related to user
            try:
                # replace Member import if circular; lazy import
                from .models import Member
                is_member_registered = Member.objects.filter(user=user).exists()
                role = "member" if is_member_registered else "unregistered"
            except Exception:
                # fallback if models not loaded
                role = "unregistered"
    return {
        "user_role": role,
        "is_member_registered": is_member_registered,
        "APP_NAME": getattr(settings, "APP_NAME", "MembersApp"),
    }
    
    
from .models import Member, MemberDocument


def pending_document_requests(request):

    if not request.user.is_authenticated:
        return {}

    try:
        member = Member.objects.get(user=request.user)

        count = MemberDocument.objects.filter(
            member=member,
            is_requested=True,
            status="pending",
        ).count()

        return {
            "pending_document_requests_count": count
        }

    except Member.DoesNotExist:
        return {
            "pending_document_requests_count": 0
        }
    
