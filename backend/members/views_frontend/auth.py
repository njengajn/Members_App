from django.contrib.auth import authenticate, login, logout, get_user_model
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.conf import settings
import requests
from backend.members.security.utils import (
    is_rate_limited,
    record_login_attempt,
    check_account_locked,
    lock_account,
    get_client_ip,
)
from backend.members.models import LoginAttempt
from django.utils import timezone
from datetime import timedelta
import random
from django.contrib.auth.hashers import make_password
from backend.members.models import EmailOTP, MagicLoginToken
from django.core.mail import send_mail
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from backend.members.utils.whatsapp import send_whatsapp_otp
from backend.members.models import OrganizationBranding

User = get_user_model()

# ======================================================
# LOGIN VIEW (FINAL CORRECTED)
# ======================================================
def login_view(request):
    """
    Login with:
    ✔ CAPTCHA enforcement
    ✔ Rate limiting
    ✔ Account lock handling
    ✔ Inactive account messaging (FIXED)
    """

    show_captcha = False
    remaining_attempts = None

    if request.method == "POST":

        username = request.POST.get("username")
        password = request.POST.get("password")

        ip = get_client_ip(request)

        # -----------------------------------------
        # TRACK FAILED ATTEMPTS
        # -----------------------------------------
        window = timezone.now() - timedelta(minutes=10)

        attempts = LoginAttempt.objects.filter(
            email=username,
            created_at__gte=window
        )

        failed_attempts = attempts.filter(success=False).count()
        remaining_attempts = max(0, 5 - failed_attempts)

        # -----------------------------------------
        # CAPTCHA AFTER 3 FAILURES
        # -----------------------------------------
        if failed_attempts >= 3:
            show_captcha = True

            captcha_response = request.POST.get("g-recaptcha-response")

            if not captcha_response:
                messages.error(request, "Please complete CAPTCHA.")
                return render(
                    request,
                    "members/login.html",
                    {
                        "show_captcha": True,
                        "remaining_attempts": remaining_attempts,
                        "RECAPTCHA_SITE_KEY": settings.RECAPTCHA_SITE_KEY,
                    }
                )

            verify = requests.post(
                "https://www.google.com/recaptcha/api/siteverify",
                data={
                    "secret": settings.RECAPTCHA_SECRET_KEY,
                    "response": captcha_response,
                }
            ).json()

            if not verify.get("success"):
                messages.error(request, "CAPTCHA verification failed. Try again.")
                return render(
                    request,
                    "members/login.html",
                    {
                        "show_captcha": True,
                        "remaining_attempts": remaining_attempts,
                        "RECAPTCHA_SITE_KEY": settings.RECAPTCHA_SITE_KEY,
                    }
                )

        # -----------------------------------------
        # HARD RATE LIMIT
        # -----------------------------------------
        if is_rate_limited(username):
            messages.error(request, "Too many attempts. Try again later.")
            return render(
                request,
                "members/login.html",
                {
                    "show_captcha": True,
                    "remaining_attempts": 0,
                    "RECAPTCHA_SITE_KEY": settings.RECAPTCHA_SITE_KEY,
                }
            )

        # -----------------------------------------
        # CHECK USER EXISTS
        # -----------------------------------------
        try:
            user_obj = User.objects.get(username=username)
        except User.DoesNotExist:
            user_obj = None

        # -----------------------------------------
        # INACTIVE ACCOUNT (FIX)
        # -----------------------------------------
        if user_obj and not user_obj.is_active:
            messages.error(request, "Your account is not active. Contact the administrator.")
            return render(
                request,
                "members/login.html",
                {
                    "show_captcha": show_captcha,
                    "remaining_attempts": remaining_attempts,
                    "RECAPTCHA_SITE_KEY": settings.RECAPTCHA_SITE_KEY,
                }
            )

        # -----------------------------------------
        # AUTHENTICATE
        # -----------------------------------------
        user = authenticate(request, username=username, password=password)

        # -----------------------------------------
        # FAILED LOGIN
        # -----------------------------------------
        if not user:

            record_login_attempt(request, None, username, False)

            messages.error(
                request,
                f"Invalid credentials. {remaining_attempts} attempts remaining."
            )

            return render(
                request,
                "members/login.html",
                {
                    "show_captcha": show_captcha,
                    "remaining_attempts": remaining_attempts,
                    "RECAPTCHA_SITE_KEY": settings.RECAPTCHA_SITE_KEY,
                }
            )

        # -----------------------------------------
        # ACCOUNT LOCK CHECK
        # -----------------------------------------
        if check_account_locked(user):
            messages.error(request, "Account locked. Please unlock via email.")
            return redirect("members:login")

        # -----------------------------------------
        # SUCCESS LOGIN
        # -----------------------------------------
        record_login_attempt(request, user, username, True)

        login(request, user)
        return redirect("members:dashboard")

    # -----------------------------------------
    # GET REQUEST
    # -----------------------------------------
    return render(
        request,
        "members/login.html",
        {
            "show_captcha": False,
            "RECAPTCHA_SITE_KEY": settings.RECAPTCHA_SITE_KEY,
        }
    )


# ======================================================
# LOGOUT
# ======================================================
def logout_view(request):
    logout(request)
    return redirect("members:login")

# =========================================================
# PASSWORD RESET REQUEST
# =========================================================

def password_reset_request(request):

    """
    Step 1:
    User enters email.
    System generates secure OTP.
    """

    if request.method == "POST":

        email = request.POST.get("email")

        # =================================================
        # VALIDATE USER
        # =================================================

        try:

            user = User.objects.get(email=email)

        except User.DoesNotExist:

            messages.error(
                request,
                "Email not found."
            )

            return redirect(
                "members:password_reset"
            )

        # =================================================
        # RATE LIMIT
        # Max 3 OTP requests in 5 minutes
        # =================================================

        window = timezone.now() - timedelta(minutes=5)

        otp_attempts = EmailOTP.objects.filter(
            email=email,
            created_at__gte=window
        ).count()

        if otp_attempts >= 3:

            messages.error(
                request,
                "Too many attempts. Try again later."
            )

            return redirect(
                "members:password_reset"
            )

        # =================================================
        # GENERATE OTP
        # =================================================

        generated_otp = str(
            random.randint(100000, 999999)
        )

        # =================================================
        # CREATE OTP OBJECT
        # =================================================

        otp_obj = EmailOTP(
            email=email,
            purpose=EmailOTP.PURPOSE_RESET,
        )

        # HASH OTP
        otp_obj.set_otp(generated_otp)

        otp_obj.save()

        # =================================================
        # STORE USER SESSION
        # =================================================

        request.session["reset_user_id"] = user.id

        # =================================================
        # EMAIL CONTENT
        # =================================================

        subject = "KRO Password Reset Code"

        #logo_url = request.build_absolute_uri(
         #   "/static/images/logo.png"
        #)
        
        branding = None

        member = getattr(user, "member", None)

        if member and member.organization:

            branding = (
                OrganizationBranding.objects.filter(
                    organization=member.organization
                ).first()
            )

        # =================================================
        # MEMBER FIRST NAME
        # =================================================

        member_first_name = ""

        # Prefer Member model first_name
        if member and member.first_name:

            member_first_name = (
                member.first_name.strip()
            )

        # Fallback to Django User first_name
        elif user.first_name:

            member_first_name = (
                user.first_name.strip()
            )

        # Final fallback
        else:

            member_first_name = "Member"

        # =================================================
        # RENDER HTML EMAIL
        # =================================================

        html_content = render_to_string(
        "members/emails/password_reset_otp.html",
        {

            "otp": generated_otp,

            "current_year": timezone.now().year,

            "branding": branding,

            "first_name": member_first_name,

            # =====================================
            # PUBLIC LOGO URL # "https://res.cloudinary.com/dufhgyo4m/image/upload/f_auto,q_auto/logo_xgme9m"
            # =====================================

            "logo_url": (
                "https://i.postimg.cc/6p5Syzg9/logo.png"
            ),
        }
    )

        text_content = (
            f"Your password reset code is: "
            f"{generated_otp}"
        )

        # =================================================
        # CREATE EMAIL
        # =================================================

        email_message = EmailMultiAlternatives(
            subject=subject,

            body=text_content,

            from_email=settings.DEFAULT_FROM_EMAIL,

            to=[email],
        )

        # =================================================
        # ATTACH HTML VERSION
        # =================================================

        email_message.attach_alternative(
            html_content,
            "text/html"
        )

        # =================================================
        # SEND EMAIL
        # =================================================

        email_message.send(
            fail_silently=False
        )

        # =================================================
        # OPTIONAL WHATSAPP OTP
        # =================================================

        member = getattr(user, "member", None)

        if member and member.phone:

            try:

                send_whatsapp_otp(
                    member.phone,
                    generated_otp
                )

            except Exception:
                pass

        # =================================================
        # SUCCESS MESSAGE
        # =================================================

        messages.success(
            request,
            "Verification code sent."
        )

        return redirect(
            "members:password_reset_verify"
        )

    return render(
        request,
        "members/auth/password_reset_request.html"
    )


# =========================================================
# PASSWORD RESET VERIFY
# =========================================================

def password_reset_verify(request):

    """
    Step 2:
    Verify OTP and reset password.
    """

    if request.method == "POST":

        entered_otp = request.POST.get("otp")

        password = request.POST.get("password")

        user_id = request.session.get(
            "reset_user_id"
        )

        # =================================================
        # VALIDATE SESSION
        # =================================================

        if not user_id:

            messages.error(
                request,
                "Password reset session expired."
            )

            return redirect(
                "members:password_reset"
            )

        # =================================================
        # GET LATEST UNUSED OTP
        # =================================================

        otp_obj = (
            EmailOTP.objects.filter(
                purpose=EmailOTP.PURPOSE_RESET,
                is_used=False
            )
            .order_by("-created_at")
            .first()
        )

        # =================================================
        # OTP NOT FOUND
        # =================================================

        if not otp_obj:

            messages.error(
                request,
                "Invalid verification code."
            )

            return redirect(
                "members:password_reset_verify"
            )

        # =================================================
        # OTP EXPIRED
        # =================================================

        if otp_obj.is_expired():

            messages.error(
                request,
                "Verification code expired."
            )

            return redirect(
                "members:password_reset"
            )

        # =================================================
        # VERIFY HASHED OTP
        # =================================================

        if not otp_obj.check_otp(entered_otp):

            messages.error(
                request,
                "Invalid verification code."
            )

            return redirect(
                "members:password_reset_verify"
            )

        # =================================================
        # GET USER
        # =================================================

        try:

            user = User.objects.get(id=user_id)

        except User.DoesNotExist:

            messages.error(
                request,
                "User not found."
            )

            return redirect(
                "members:password_reset"
            )

        # =================================================
        # UPDATE PASSWORD
        # =================================================

        user.set_password(password)

        user.save()

        # =================================================
        # MARK OTP USED
        # =================================================

        otp_obj.is_used = True

        otp_obj.save(
            update_fields=["is_used"]
        )

        # =================================================
        # CLEAR SESSION
        # =================================================

        if "reset_user_id" in request.session:

            del request.session[
                "reset_user_id"
            ]

        messages.success(
            request,
            "Password updated successfully."
        )

        return redirect(
            "members:login"
        )

    return render(
        request,
        "members/auth/password_reset_verify.html"
    )

def magic_login(request, token):

    token_obj = get_object_or_404(
        MagicLoginToken,
        token=token,
        is_used=False
    )

    if token_obj.is_expired():

        return redirect("members:login")

    login(request, token_obj.user)

    token_obj.is_used = True

    token_obj.save(update_fields=["is_used"])

    return redirect("members:dashboard")

from django.shortcuts import get_object_or_404
from django.shortcuts import redirect

from backend.members.models import EmailVerification


def verify_email(request, token):

    verification = get_object_or_404(
        EmailVerification,
        token=token
    )

    verification.is_verified = True

    verification.save(
        update_fields=["is_verified"]
    )

    return redirect("members:login")