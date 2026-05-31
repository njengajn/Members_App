# backend/members/views_frontend/base.py
def base_context(request):
    """
    Return a dictionary of context data common to all frontend templates.
    Example: user role, site name, etc.
    """
    user_role = "unregistered"
    if request.user.is_authenticated:
        # Determine user role
        if request.user.is_staff:
            user_role = "admin"
        else:
            # Or fetch member status from the Member model
            from backend.members.models import Member
            try:
                member = Member.objects.get(user=request.user)
                user_role = "member" if member.status == "active" else "unregistered"
            except Member.DoesNotExist:
                user_role = "unregistered"

    return {
        "user_role": user_role,
        "site_name": "MembersPortal",
    }
