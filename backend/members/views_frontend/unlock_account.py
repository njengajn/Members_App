# backend/members/views_frontend/unlock_account.py

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import get_user_model

from backend.members.models import AccountLock

User = get_user_model()


def unlock_account(request):

    if request.method == "POST":

        email = request.POST.get("email")

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            messages.error(request, "Invalid email.")
            return redirect("members:unlock_account")

        AccountLock.objects.filter(user=user).delete()

        messages.success(request, "Account unlocked. Please login.")
        return redirect("members:login")

    return render(request, "members/auth/unlock_account.html")