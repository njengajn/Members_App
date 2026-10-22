import secrets

from django.contrib.auth import authenticate, login, logout, get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
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
from backend.members.utils.validation import validate_member_password
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
    Generate a secure OTP and bind it to the specific user,
    OTP record, and password-reset purpose.
    """

    if request.method != "POST":
        return render(
            request,
            "members/auth/password_reset_request.html",
        )

    # =====================================================
    # VALIDATE EMAIL INPUT
    # =====================================================

    email = (request.POST.get("email") or "").strip()

    if not email:
        messages.error(
            request,
            "Please enter your email address.",
        )
        return redirect("members:password_reset")

    # =====================================================
    # FIND USER
    # =====================================================

    try:
        user = User.objects.get(email__iexact=email)
        email = user.email

    except User.DoesNotExist:
        messages.error(
            request,
            "Instructions will be sent to your email shortly.",
        )
        return redirect("members:password_reset")

    except User.MultipleObjectsReturned:
        messages.error(
            request,
            "We could not verify this email address. Please contact support.",
        )
        return redirect("members:password_reset")

    # =====================================================
    # RATE LIMIT
    # Maximum 3 password-reset OTP requests in 5 minutes.
    # =====================================================

    window = timezone.now() - timedelta(minutes=5)

    otp_attempts = EmailOTP.objects.filter(
        email__iexact=email,
        purpose=EmailOTP.PURPOSE_RESET,
        created_at__gte=window,
    ).count()

    if otp_attempts >= 3:
        messages.error(
            request,
            "Too many attempts. Try again later.",
        )
        return redirect("members:password_reset")

    # =====================================================
    # GENERATE SECURE OTP
    # =====================================================

    generated_otp = str(
        secrets.randbelow(900000) + 100000
    )

    # =====================================================
    # CREATE OTP RECORD
    # =====================================================

    otp_obj = EmailOTP(
        email=email,
        purpose=EmailOTP.PURPOSE_RESET,
    )

    # Preserve the model's existing OTP hashing mechanism.
    otp_obj.set_otp(generated_otp)
    otp_obj.save()

    # =====================================================
    # BIND SESSION TO USER AND OTP
    # =====================================================

    # Remove any previous reset-session binding before replacing it.
    request.session.pop("reset_user_id", None)
    request.session.pop("reset_otp_id", None)
    request.session.pop("reset_purpose", None)

    request.session["reset_user_id"] = user.pk
    request.session["reset_otp_id"] = otp_obj.pk
    request.session["reset_purpose"] = EmailOTP.PURPOSE_RESET

    # =====================================================
    # ORGANISATION BRANDING
    # =====================================================

    branding = None
    member = getattr(user, "member", None)

    if member and member.organization:
        branding = OrganizationBranding.objects.filter(
            organization=member.organization,
        ).first()

    # =====================================================
    # MEMBER FIRST NAME
    # =====================================================

    if member and member.first_name:
        member_first_name = member.first_name.strip()

    elif user.first_name:
        member_first_name = user.first_name.strip()

    else:
        member_first_name = "Member"

    # =====================================================
    # RENDER EMAIL
    # =====================================================

    subject = "KRO Password Reset Code"

    html_content = render_to_string(
        "members/emails/password_reset_otp.html",
        {
            "otp": generated_otp,
            "current_year": timezone.now().year,
            "branding": branding,
            "first_name": member_first_name,
            "logo_url": (
                f"{settings.PUBLIC_SITE_URL}/static/images/favicon.jpg"
            ),
        },
    )

    text_content = (
        f"Your password reset code is: {generated_otp}"
    )

    email_message = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
    )

    email_message.attach_alternative(
        html_content,
        "text/html",
    )

    # =====================================================
    # SEND EMAIL
    # =====================================================

    try:
        email_message.send(fail_silently=False)

    except Exception:
        # Invalidate the newly created code if email delivery fails.
        EmailOTP.objects.filter(
            pk=otp_obj.pk,
            purpose=EmailOTP.PURPOSE_RESET,
            is_used=False,
        ).update(is_used=True)

        # Remove the binding to the undelivered code.
        for key in (
            "reset_user_id",
            "reset_otp_id",
            "reset_purpose",
        ):
            request.session.pop(key, None)

        messages.error(
            request,
            "We could not send the verification code. Please try again later.",
        )
        return redirect("members:password_reset")

    # =====================================================
    # INVALIDATE OLDER UNUSED RESET CODES
    # =====================================================

    # Do this only after successful email delivery so a failed new
    # email does not invalidate a previously delivered code.
    EmailOTP.objects.filter(
        email__iexact=email,
        purpose=EmailOTP.PURPOSE_RESET,
        is_used=False,
    ).exclude(
        pk=otp_obj.pk,
    ).update(
        is_used=True,
    )

    # =====================================================
    # OPTIONAL WHATSAPP DELIVERY
    # =====================================================

    # WhatsApp remains optional and must not undo successful email
    # delivery if the WhatsApp provider is unavailable.
    if member and member.phone:
        try:
            send_whatsapp_otp(
                member.phone,
                generated_otp,
            )
        except Exception:
            pass

    # =====================================================
    # SUCCESS
    # =====================================================

    messages.success(
        request,
        "Verification code sent.",
    )

    return redirect("members:password_reset_verify")


# =========================================================
# PASSWORD RESET VERIFY
# =========================================================

def password_reset_verify(request):
    """
    Step 2:
    Verify reCAPTCHA, verify the session-bound OTP, validate
    the new password and confirmation, and reset the password.

    Security controls:
    - Server-side Google reCAPTCHA verification.
    - OTP bound to the session user, OTP record, and purpose.
    - Unused and unexpired OTP required.
    - Maximum five incorrect OTP submissions per OTP.
    - Existing member password policy enforced.
    - Password confirmation must match.
    - Password update and OTP consumption are transactional.
    """

    MAX_OTP_ATTEMPTS = 5

    RESET_SESSION_KEYS = (
        "reset_user_id",
        "reset_otp_id",
        "reset_purpose",
    )

    template_name = "members/auth/password_reset_verify.html"

    # =====================================================
    # LOAD ORGANISATION BRANDING
    # =====================================================

    branding = None
    session_user_id = request.session.get("reset_user_id")

    if session_user_id:
        try:
            branding_user = User.objects.get(pk=session_user_id)
            branding_member = getattr(
                branding_user,
                "member",
                None,
            )

            if branding_member and branding_member.organization:
                branding = OrganizationBranding.objects.filter(
                    organization=branding_member.organization,
                ).first()

        except User.DoesNotExist:
            # Session validation below handles a missing user.
            pass

    # Use the same uppercase context variable as the existing login
    # and registration CAPTCHA integrations.
    template_context = {
        "branding": branding,
        "RECAPTCHA_SITE_KEY": getattr(
            settings,
            "RECAPTCHA_SITE_KEY",
            "",
        ),
    }

    # =====================================================
    # DISPLAY FORM
    # =====================================================

    if request.method != "POST":
        return render(
            request,
            template_name,
            template_context,
        )

    # =====================================================
    # VALIDATE RESET SESSION
    # =====================================================

    user_id = request.session.get("reset_user_id")
    otp_id = request.session.get("reset_otp_id")
    purpose = request.session.get("reset_purpose")

    if (
        not user_id
        or not otp_id
        or purpose != EmailOTP.PURPOSE_RESET
    ):
        for key in RESET_SESSION_KEYS:
            request.session.pop(key, None)

        messages.error(
            request,
            "Your password reset session has expired. Please request a new code.",
        )
        return redirect("members:password_reset")

    # =====================================================
    # VERIFY GOOGLE reCAPTCHA
    # =====================================================

    # The CAPTCHA widget is not a security check by itself.
    # Validate the response token with Google on the server.
    captcha_response = (
        request.POST.get("g-recaptcha-response") or ""
    ).strip()

    recaptcha_site_key = getattr(
        settings,
        "RECAPTCHA_SITE_KEY",
        "",
    )

    recaptcha_secret = getattr(
        settings,
        "RECAPTCHA_SECRET_KEY",
        "",
    )

    # Fail closed if CAPTCHA is not configured.
    if not recaptcha_site_key or not recaptcha_secret:
        messages.error(
            request,
            "Password reset verification is temporarily unavailable. Please try again later.",
        )
        return redirect("members:password_reset_verify")

    if not captcha_response:
        messages.error(
            request,
            "Please complete reCAPTCHA verification.",
        )
        return redirect("members:password_reset_verify")

    try:
        captcha_response_result = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={
                "secret": recaptcha_secret,
                "response": captcha_response,
            },
            timeout=5,
        )

        # Treat HTTP failures and malformed responses as failed
        # verification instead of allowing the reset to continue.
        captcha_response_result.raise_for_status()
        captcha_result = captcha_response_result.json()

        captcha_valid = (
            captcha_result.get("success") is True
        )

    except (requests.RequestException, ValueError):
        captcha_valid = False

    if not captcha_valid:
        messages.error(
            request,
            "reCAPTCHA verification failed. Please try again.",
        )
        return redirect("members:password_reset_verify")

    # =====================================================
    # READ FORM VALUES
    # =====================================================

    # IMPORTANT: These names match the reset template:
    # name="otp", name="password", name="confirm_password".
    entered_otp = (
        request.POST.get("otp") or ""
    ).strip()

    password1 = request.POST.get("password") or ""
    password2 = request.POST.get("confirm_password") or ""

    # =====================================================
    # CONFIRM PASSWORD MATCH
    # =====================================================

    # A password mismatch is not an incorrect OTP submission.
    # Do not increment the OTP attempt counter or consume the OTP.
    if password1 != password2:
        messages.error(
            request,
            "The passwords do not match. Please enter the same password in both fields.",
        )
        return redirect("members:password_reset_verify")

    # =====================================================
    # VERIFY OTP AND UPDATE PASSWORD
    # =====================================================

    try:
        with transaction.atomic():

            # Resolve the user from the reset session.
            user = User.objects.get(pk=user_id)

            # Retrieve only the OTP issued to this user for this
            # reset session and purpose. Lock the record to protect
            # the attempt counter from concurrent submissions.
            otp_obj = (
                EmailOTP.objects
                .select_for_update()
                .get(
                    pk=otp_id,
                    email__iexact=user.email,
                    purpose=EmailOTP.PURPOSE_RESET,
                    is_used=False,
                )
            )

            # -------------------------------------------------
            # ATTEMPT LIMIT
            # -------------------------------------------------

            if otp_obj.failed_attempts >= MAX_OTP_ATTEMPTS:
                otp_obj.is_used = True
                otp_obj.save(update_fields=["is_used"])
                outcome = "locked"

            # -------------------------------------------------
            # EXPIRY
            # -------------------------------------------------

            elif otp_obj.is_expired():
                otp_obj.is_used = True
                otp_obj.save(update_fields=["is_used"])
                outcome = "expired"

            # -------------------------------------------------
            # OTP FORMAT AND HASH
            # -------------------------------------------------

            elif (
                len(entered_otp) != 6
                or not entered_otp.isascii()
                or not entered_otp.isdigit()
                or not otp_obj.check_otp(entered_otp)
            ):
                otp_obj.failed_attempts += 1

                # Invalidate the OTP immediately on the fifth
                # incorrect submission.
                if otp_obj.failed_attempts >= MAX_OTP_ATTEMPTS:
                    otp_obj.is_used = True

                otp_obj.save(
                    update_fields=[
                        "failed_attempts",
                        "is_used",
                    ]
                )

                outcome = (
                    "locked"
                    if otp_obj.is_used
                    else "incorrect"
                )

            # -------------------------------------------------
            # VALID OTP: APPLY PASSWORD POLICY
            # -------------------------------------------------

            else:
                try:
                    # Reuse the existing server-side validation
                    # function used by the registration workflow.
                    validate_member_password(
                        password1,
                        user=user,
                    )

                except ValidationError as exc:
                    # Invalid passwords do not count as incorrect
                    # OTP attempts. The valid OTP remains available.
                    outcome = "password_invalid"

                    password_error = (
                        exc.messages[0]
                        if exc.messages
                        else "Please choose a valid password."
                    )

                else:
                    # Only update the password after CAPTCHA,
                    # OTP, confirmation, and policy checks succeed.
                    user.set_password(password1)
                    user.save(update_fields=["password"])

                    # Consume the OTP in the same transaction.
                    otp_obj.is_used = True
                    otp_obj.save(update_fields=["is_used"])

                    outcome = "success"

    except (User.DoesNotExist, EmailOTP.DoesNotExist):
        # Reject missing, used, or incorrectly bound OTP records.
        for key in RESET_SESSION_KEYS:
            request.session.pop(key, None)

        messages.error(
            request,
            "This verification code is invalid or no longer available. Please request a new code.",
        )
        return redirect("members:password_reset")

    # =====================================================
    # HANDLE VERIFICATION RESULTS
    # =====================================================

    if outcome == "locked":
        for key in RESET_SESSION_KEYS:
            request.session.pop(key, None)

        messages.error(
            request,
            "Too many incorrect verification attempts. Please request a new code.",
        )
        return redirect("members:password_reset")

    if outcome == "expired":
        for key in RESET_SESSION_KEYS:
            request.session.pop(key, None)

        messages.error(
            request,
            "Your verification code has expired. Please request a new code.",
        )
        return redirect("members:password_reset")

    if outcome == "incorrect":
        messages.error(
            request,
            "Invalid verification code. Please try again.",
        )
        return redirect("members:password_reset_verify")

    if outcome == "password_invalid":
        messages.error(
            request,
            password_error,
        )
        return redirect("members:password_reset_verify")

    if outcome == "success":
        for key in RESET_SESSION_KEYS:
            request.session.pop(key, None)

        messages.success(
            request,
            "Password updated successfully.",
        )
        return redirect("members:login")

    # Defensive fallback.
    messages.error(
        request,
        "We could not complete your password reset. Please request a new code.",
    )
    return redirect("members:password_reset")


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