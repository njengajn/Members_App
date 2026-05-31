"""
Middleware to block retired members.
"""

from django.shortcuts import redirect
from django.contrib import messages
from members.models import Member


class RetiredMemberMiddleware:
    """
    If a member is retired → block access immediately.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        if request.user.is_authenticated:

            try:
                member = request.user.member

                if member.status == Member.STATUS_RETIRED:
                    messages.error(
                        request,
                        "Your membership has been retired for non-compliance.",
                    )
                    return redirect("login")

            except Member.DoesNotExist:
                pass

        return self.get_response(request)