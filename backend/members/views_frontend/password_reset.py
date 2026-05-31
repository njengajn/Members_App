import random
from django.utils import timezone
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.mail import send_mail

from backend.members.models import EmailOTP

User = get_user_model()


def password_reset_requestMovedToAuth(request):

    if request.method == "POST":

        email = request.POST.get("email")

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            messages.error(request, "Email not found.")
            return redirect("members:password_reset")

        # RATE LIMIT
        window = timezone.now() - timedelta(minutes=5)
        if EmailOTP.objects.filter(email=email, created_at__gte=window).count() >= 3:
            messages.error(request, "Too many attempts.")
            return redirect("members:password_reset")

        otp = str(random.randint(100000, 999999))

        EmailOTP.objects.create(
            email=email,
            otp=otp,
            purpose=EmailOTP.PURPOSE_RESET,
        )

        request.session["reset_user_id"] = user.id

        send_mail(
            "Password Reset Code",
            f"Your code is: {otp}",
            None,
            [email],
            fail_silently=True,
        )

        return redirect("members:password_reset_verify")

    return render(request, "members/auth/password_reset_request.html")


def password_reset_verifyMovedToAuth(request):

    if request.method == "POST":

        otp = request.POST.get("otp")
        password = request.POST.get("password")

        user_id = request.session.get("reset_user_id")

        otp_obj = EmailOTP.objects.filter(
            otp=otp,
            purpose=EmailOTP.PURPOSE_RESET,
            is_used=False
        ).order_by("-created_at").first()

        if not otp_obj:
            messages.error(request, "Invalid code.")
            return redirect("members:password_reset_verify")

        if otp_obj.is_expired():
            messages.error(request, "Code expired.")
            return redirect("members:password_reset")

        user = User.objects.get(id=user_id)
        user.set_password(password)
        user.save()

        otp_obj.is_used = True
        otp_obj.save()

        messages.success(request, "Password updated.")
        return redirect("members:login")

    return render(request, "members/auth/password_reset_verify.html")