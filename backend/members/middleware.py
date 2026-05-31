from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse

def incomplete_registration_redirect(get_response):
    """
    Middleware to ensure users complete registration before proceeding.
    to be Attached in settings.py -> MIDDLEWARE list.
    """
    def middleware(request):
        if request.user.is_authenticated:
            # If user has a draft registration stored in session, redirect to final confirmation
            if "draft_member_id" in request.session and not request.path.startswith(reverse("members:register_step_5_confirm")):
                messages.warning(request, "⚠️ Please complete your registration before proceeding.")
                return redirect("members:register_step_5_confirm")
        return get_response(request)
    return middleware


from django.shortcuts import redirect
from django.contrib import messages
from .models import Member


class RetiredMemberMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        if request.user.is_authenticated:

            try:
                member = request.user.member

                if member.status == Member.STATUS_RETIRED:
                    messages.error(
                        request,
                        "Your membership has been retired for non-compliance."
                    )
                    return redirect("login")

            except Member.DoesNotExist:
                pass

        return self.get_response(request)
