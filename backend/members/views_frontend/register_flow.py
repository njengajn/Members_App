from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect
from django.urls import reverse
from django.db import transaction, IntegrityError
from backend.members.models import Member, NextOfKin, Dependant, Address, RegistrationDraft
from django.conf import settings
import requests, random
from datetime import timedelta
from django.utils import timezone
from django.core.mail import send_mail
from backend.members.models import EmailOTP
from backend.members.utils.otp import can_send_otp
from backend.members.utils.otp import can_send_otp, generate_otp
from backend.members.services.notifications import (
    send_html_email
)
from backend.members.utils.ip import (
    get_client_ip
)
from backend.members.utils.validation import (
    validate_email_address,
    validate_member_password,
    clean_uk_mobile,
)
import re
import hashlib
import secrets

otp = generate_otp()

User = get_user_model()

# ======================================================
# REGISTRATION VALIDATION HELPERS
# ======================================================

def _clean(value):
    """
    Safely strip a submitted value.
    """
    return (value or "").strip()

# ==============================================================
# FINAL DEPENDANT VALIDATION
# backend/members/views_frontend/register_flow.py
# ==============================================================

def validate_registration_dependants(
    dependants,
    marital_status,
    parent_statuses,
):
    """
    Final authoritative dependant validation used by Step 5.

    Mother/Father eligibility is determined exclusively by the
    statuses captured in Step 2.

    A Parent dependant is valid only when the corresponding
    Step 2 parent status is ALIVE.

    Parent status stored in an individual dependant dictionary
    is not trusted as the authority.
    """

    errors = []

    valid_relationships = {
        Dependant.TYPE_CHILD,
        Dependant.TYPE_SPOUSE,
        Dependant.TYPE_SIBLING,
        Dependant.TYPE_PARENT,
    }

    parent_statuses = parent_statuses or {}

    mother_status = _clean(
        parent_statuses.get("MOTHER")
    ).upper()

    father_status = _clean(
        parent_statuses.get("FATHER")
    ).upper()

    spouse_count = 0
    mother_count = 0
    father_count = 0

    for number, dependant in enumerate(dependants, start=1):

        if not isinstance(dependant, dict):
            errors.append(
                f"Dependant {number}: Invalid dependant information."
            )
            continue

        relationship = _clean(
            dependant.get("relationship")
        ).upper()

        parent_type = _clean(
            dependant.get("parent_type")
        ).upper()

        country = _clean(
            dependant.get("country")
        )
        county = _clean(
            dependant.get("county")
        )
        sub_county_town = _clean(
            dependant.get("sub_county_town")
        )

        first_name = _clean(
            dependant.get("first_name")
        )
        surname = _clean(
            dependant.get("surname")
        )
        dob = dependant.get("dob")

        # --------------------------------------------------
        # VALID RELATIONSHIP
        # --------------------------------------------------
        if relationship not in valid_relationships:
            errors.append(
                f"Dependant {number}: Please select a valid relationship."
            )
            continue

        # --------------------------------------------------
        # SPOUSE
        # --------------------------------------------------
        if relationship == Dependant.TYPE_SPOUSE:

            spouse_count += 1

            for field, label in (
                (country, "Country"),
                (county, "County"),
                (sub_county_town, "Sub-county / Town"),
            ):
                if not field:
                    errors.append(
                        f"Dependant {number}: {label} is required for a spouse."
                    )

        # --------------------------------------------------
        # SIBLING
        # --------------------------------------------------
        elif relationship == Dependant.TYPE_SIBLING:

            for field, label in (
                (country, "Country"),
                (county, "County"),
                (sub_county_town, "Sub-county / Town"),
            ):
                if not field:
                    errors.append(
                        f"Dependant {number}: {label} is required for a sibling."
                    )

        # --------------------------------------------------
        # PARENT — STEP 2 STATUS IS AUTHORITATIVE
        # --------------------------------------------------
        elif relationship == Dependant.TYPE_PARENT:

            if parent_type not in {
                Dependant.PARENT_MOTHER,
                Dependant.PARENT_FATHER,
            }:
                errors.append(
                    f"Dependant {number}: Please select Mother or Father."
                )
                continue

            if parent_type == Dependant.PARENT_MOTHER:
                mother_count += 1
                authoritative_status = mother_status

            else:
                father_count += 1
                authoritative_status = father_status

            # Never trust the parent_status stored in the dependant.
            # Reconcile it with the status originally captured in Step 2.
            if authoritative_status != Dependant.PARENT_ALIVE:
                errors.append(
                    f"Dependant {number}: This parent cannot be registered "
                    "because their status in Step 2 is not Alive."
                )
                continue

            # --------------------------------------------------
            # ALIVE PARENT DETAILS
            # --------------------------------------------------
            if not first_name:
                errors.append(
                    f"Dependant {number}: First name is required."
                )

            if not surname:
                errors.append(
                    f"Dependant {number}: Surname is required."
                )

            if not dob:
                errors.append(
                    f"Dependant {number}: Date of birth is required."
                )

            for field, label in (
                (country, "Country"),
                (county, "County"),
                (sub_county_town, "Sub-county / Town"),
            ):
                if not field:
                    errors.append(
                        f"Dependant {number}: {label} is required for an Alive parent."
                    )

        # --------------------------------------------------
        # CHILD
        # --------------------------------------------------
        elif relationship == Dependant.TYPE_CHILD:

            if not first_name:
                errors.append(
                    f"Dependant {number}: First name is required."
                )

            if not surname:
                errors.append(
                    f"Dependant {number}: Surname is required."
                )

            if not dob:
                errors.append(
                    f"Dependant {number}: Date of birth is required."
                )

    # ------------------------------------------------------
    # SPOUSE COUNT AND MARITAL STATUS
    # ------------------------------------------------------
    if marital_status == Member.MARITAL_MARRIED:

        if spouse_count != 1:
            errors.append(
                "Married members must register exactly one spouse."
            )

    elif marital_status in {
        Member.MARITAL_SINGLE,
        Member.MARITAL_WIDOWED,
        Member.MARITAL_SEPARATED,
    }:

        if spouse_count:
            errors.append(
                "A spouse can only be registered when marital status is Married."
            )

    else:
        errors.append(
            "Please select a valid marital status."
        )

    # ------------------------------------------------------
    # PARENT COUNT LIMITS
    # ------------------------------------------------------
    if mother_count > 1:
        errors.append(
            "Only one Mother can be registered."
        )

    if father_count > 1:
        errors.append(
            "Only one Father can be registered."
        )

    return errors


def register_step_1_user(request):
    """
    Registration step 1.

    - Prevents authenticated users from registering.
    - Validates username and email.
    - Rejects duplicate usernames and emails before OTP activity.
    - Preserves GDPR, CAPTCHA, password policy and OTP rate limiting.
    - Generates and emails the hashed OTP using the existing service.
    """

    # =================================================
    # AUTHENTICATED USER GUARD
    # =================================================
    if request.user.is_authenticated:
        messages.info(
            request,
            "You are already logged in. You cannot register "
            "another account while logged in."
        )
        return redirect("members:dashboard")

    if request.method == "POST":

        # =================================================
        # READ AND NORMALISE INPUT
        # =================================================
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        confirm = request.POST.get("confirm_password") or ""
        email_input = (request.POST.get("email") or "").strip()

        # =================================================
        # USERNAME FORMAT VALIDATION
        # =================================================
        if (
            not username
            or len(username) > 21
            or not username.isascii()
            or any(
                not (
                    character.isalpha()
                    or character.isdigit()
                    or character in "._-"
                )
                for character in username
            )
        ):
            messages.error(
                request,
                "Username must be 1–21 characters and may contain "
                "only letters, digits, dot (.), underscore (_) or "
                "hyphen (-). No spaces or other special characters "
                "are allowed."
            )
            return redirect("members:register_step_1")

        # =================================================
        # EMAIL VALIDATION AND NORMALISATION
        # =================================================
        try:
            email = validate_email_address(email_input)
            email = email.strip().lower()
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return redirect("members:register_step_1")

        # =================================================
        # PASSWORD CHECKS
        # =================================================
        if password != confirm:
            messages.error(request, "Passwords do not match.")
            return redirect("members:register_step_1")

        try:
            validate_member_password(password)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return redirect("members:register_step_1")

        # =================================================
        # DUPLICATE USERNAME / EMAIL CHECKS
        #
        # These checks MUST remain before:
        # - can_send_otp()
        # - generate_otp()
        # - EmailOTP creation
        # - session registration data
        # - send_html_email()
        # =================================================

        if User.objects.filter(username__iexact=username).exists():
            messages.error(
                request,
                "That username is already in use."
            )
            return redirect("members:register_step_1")

        if User.objects.filter(email__iexact=email).exists():
            messages.error(
                request,
                "An account with this email address already exists."
            )
            return redirect("members:register_step_1")

        if Member.objects.filter(email__iexact=email).exists():
            messages.error(
                request,
                "This email address is already registered as a member."
            )
            return redirect("members:register_step_1")

        # =================================================
        # GDPR CONSENT
        # =================================================
        if not request.POST.get("gdpr_consent"):
            messages.error(
                request,
                "You must agree to the GDPR and data protection policy."
            )
            return redirect("members:register_step_1")

        # =================================================
        # CAPTCHA (DEV BYPASS)
        # =================================================
        if not settings.DEBUG:
            captcha_response = request.POST.get(
                "g-recaptcha-response"
            )

            if not captcha_response:
                messages.error(
                    request,
                    "Please complete CAPTCHA."
                )
                return redirect("members:register_step_1")

        # =================================================
        # RATE LIMIT
        # =================================================
        if not can_send_otp(email):
            messages.error(request, "Too many attempts.")
            return redirect("members:register_step_1")

        # =================================================
        # GENERATE AND STORE OTP
        # =================================================
        otp = generate_otp()

        otp_obj = EmailOTP(
            email=email,
            purpose=EmailOTP.PURPOSE_REGISTRATION,
        )
        otp_obj.set_otp(otp)
        otp_obj.save()

        # =================================================
        # STORE SESSION
        # =================================================
        request.session["reg_user"] = {
            "username": username,
            "email": email,
            # Store only a Django password hash in the session, never plaintext.
            "password_hash": make_password(password),
        }

        # A new registration attempt must not reuse an old
        # successful email-verification marker.
        request.session.pop("reg_verified_email", None)
        request.session.modified = True

        # =================================================
        # SEND BRANDED OTP EMAIL
        # =================================================
        send_html_email(
            recipient=email,
            subject="Verify Your Email",
            template="members/emails/registration_otp.html",
            context={
                "email_title": "Email Verification",
                "first_name": username or "Member",
                "otp": otp,
                "current_year": timezone.now().year,
                "plain_message": (
                    f"Your verification code is: {otp}"
                ),
            },
        )

        messages.success(
            request,
            "Verification code sent to your email."
        )

        return redirect("members:register_verify_email")

    return render(
        request,
        "members/register/register_step_1_user.html",
        {
            "recaptcha_site_key": settings.RECAPTCHA_SITE_KEY,
            "debug": settings.DEBUG,
        },
    )



# ======================================================
# REGISTRATION DRAFT HELPERS
# ======================================================

REGISTRATION_SESSION_KEYS = (
    "reg_user",
    "reg_member",
    "reg_address",
    "reg_nok",
    "reg_dependants",
    "reg_verified_email",
    "registration_draft_id",
)


def _registration_email_is_verified(request, reg_user=None):
    """Require the verification marker to match this registration email."""
    reg_user = reg_user or request.session.get("reg_user") or {}
    email = _clean(reg_user.get("email")).lower()
    verified_email = _clean(
        request.session.get("reg_verified_email")
    ).lower()
    return bool(email and verified_email and email == verified_email)


def _registration_payload_from_session(request):
    """Return only JSON-safe profile data; never include password material."""
    return {
        "reg_member": request.session.get("reg_member", {}) or {},
        "reg_address": request.session.get("reg_address", {}) or {},
        "reg_nok": request.session.get("reg_nok", {}) or {},
        "reg_dependants": request.session.get("reg_dependants", []) or [],
    }


def _registration_step_url_name(step):
    return {
        2: "members:register_step_2",
        3: "members:register_step_3",
        4: "members:register_step_4",
        5: "members:register_step_5",
    }[step]


def _save_registration_draft_response(request, step):
    """Persist the current registration progress and email a secure resume link."""
    reg_user = request.session.get("reg_user") or {}
    email = _clean(reg_user.get("email")).lower()
    username = _clean(reg_user.get("username"))

    if not _registration_email_is_verified(request, reg_user):
        messages.error(
            request,
            "Verify your email address before saving a registration draft.",
        )
        return redirect("members:register_verify_email" if email else "members:register_step_1")

    if not username or not email:
        messages.error(request, "Your registration session is incomplete. Please start again.")
        return redirect("members:register_step_1")

    # Re-check current account conflicts before issuing a resumable draft.
    if User.objects.filter(username__iexact=username).exists():
        messages.error(request, "That username is already in use. Please contact the membership team if you need help.")
        return redirect("members:register_step_1")
    if User.objects.filter(email__iexact=email).exists() or Member.objects.filter(email__iexact=email).exists():
        messages.error(request, "This email address is already registered. Please log in instead.")
        return redirect("members:login")

    raw_token = secrets.token_urlsafe(32)
    draft = RegistrationDraft(
        verified_email=email,
        username=username,
        payload=_registration_payload_from_session(request),
        current_step=step,
        expires_at=timezone.now() + timedelta(days=7),
    )
    draft.set_resume_token(raw_token)
    draft.save()

    resume_url = request.build_absolute_uri(
        reverse("members:resume_registration", kwargs={"token": raw_token})
    )
    try:
        send_html_email(
            recipient=email,
            subject="Resume your membership registration",
            template="members/emails/registration_draft_resume.html",
            context={
                "email_title": "Resume your membership registration",
                "first_name": username or "Member",
                "resume_url": resume_url,
                "expiry_days": 7,
                "current_year": timezone.now().year,
                "plain_message": (
                    f"Your registration draft has been saved. Resume it here: {resume_url}. "
                    "This link expires in 7 days."
                ),
            },
        )
    except Exception:
        # Keep any earlier emailed link valid if delivery of this link fails.
        draft.is_active = False
        draft.save(update_fields=["is_active", "updated_at"])
        messages.error(
            request,
            "Your draft could not be emailed. Please try again. Your current form data remains in this browser session.",
        )
        return redirect(_registration_step_url_name(step))

    # Only invalidate older links after the replacement email was sent.
    RegistrationDraft.objects.filter(
        verified_email__iexact=email,
        username__iexact=username,
        is_active=True,
    ).exclude(pk=draft.pk).update(is_active=False)

    request.session["registration_draft_id"] = draft.pk
    request.session.modified = True
    messages.success(
        request,
        "Your draft has been saved. We have emailed you a secure link to resume within seven days.",
    )
    return redirect(_registration_step_url_name(step))


def resume_registration(request, token):
    """Resume a draft from its emailed token without using the shared OTP page."""
    if request.user.is_authenticated:
        messages.info(request, "You are already logged in.")
        return redirect("members:dashboard")

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    draft = RegistrationDraft.objects.filter(
        resume_token_hash=token_hash,
        is_active=True,
        completed_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).first()

    if not draft or not draft.check_resume_token(token):
        return render(
            request,
            "members/register/registration_draft_resume.html",
            {
                "step_num": 1,
                "token_valid": False,
                "resume_error": "This registration link is invalid, has expired, or has already been replaced. Save a new draft or start again.",
            },
            status=400,
        )

    if request.method == "POST":
        password = request.POST.get("password") or ""
        confirm_password = request.POST.get("confirm_password") or ""

        if password != confirm_password:
            return render(
                request,
                "members/register/registration_draft_resume.html",
                {"step_num": 1, "token_valid": True, "resume_error": "The passwords do not match."},
                status=400,
            )
        try:
            validate_member_password(password)
        except ValidationError as exc:
            return render(
                request,
                "members/register/registration_draft_resume.html",
                {"step_num": 1, "token_valid": True, "resume_error": exc.messages[0]},
                status=400,
            )

        # Do not let a stale draft overwrite a real account created meanwhile.
        if User.objects.filter(username__iexact=draft.username).exists():
            draft.is_active = False
            draft.save(update_fields=["is_active", "updated_at"])
            messages.error(request, "This username is now in use. Please contact the membership team for help.")
            return redirect("members:register_step_1")
        if User.objects.filter(email__iexact=draft.verified_email).exists() or Member.objects.filter(email__iexact=draft.verified_email).exists():
            draft.is_active = False
            draft.save(update_fields=["is_active", "updated_at"])
            messages.error(request, "An account already exists for this email address. Please log in instead.")
            return redirect("members:login")

        payload = draft.payload if isinstance(draft.payload, dict) else {}
        request.session.cycle_key()
        for key in REGISTRATION_SESSION_KEYS:
            request.session.pop(key, None)

        request.session["reg_user"] = {
            "username": draft.username,
            "email": draft.verified_email,
            "password_hash": make_password(password),
        }
        request.session["reg_member"] = payload.get("reg_member", {}) if isinstance(payload.get("reg_member", {}), dict) else {}
        request.session["reg_address"] = payload.get("reg_address", {}) if isinstance(payload.get("reg_address", {}), dict) else {}
        request.session["reg_nok"] = payload.get("reg_nok", {}) if isinstance(payload.get("reg_nok", {}), dict) else {}
        request.session["reg_dependants"] = payload.get("reg_dependants", []) if isinstance(payload.get("reg_dependants", []), list) else []
        request.session["reg_verified_email"] = draft.verified_email.lower()
        request.session["registration_draft_id"] = draft.pk
        request.session.modified = True

        messages.success(request, "Your saved registration has been restored. Continue from where you left off.")
        return redirect(_registration_step_url_name(draft.current_step))

    return render(
        request,
        "members/register/registration_draft_resume.html",
        {"step_num": 1, "token_valid": True, "resume_error": ""},
    )



# =========================================
# VERIFY STEP
# =========================================
def register_verify_email(request):
    """
    STEP VERIFY

    - Check hashed OTP
    - Check expiry
    - Mark OTP used
    - Support OTP resend
    - Use branded HTML emails
    - Remember successful verification for this registration
    """

    email = request.session.get(
        "reg_user",
        {}
    ).get("email")

    username = request.session.get(
        "reg_user",
        {}
    ).get("username")

    if not email:
        return redirect(
            "members:register_step_1"
        )

    email = email.strip().lower()

    # =================================================
    # ALREADY VERIFIED IN THIS REGISTRATION SESSION
    # =================================================

    verified_email = request.session.get(
        "reg_verified_email",
        ""
    )

    if (
        verified_email
        and verified_email.strip().lower() == email
    ):
        messages.info(
            request,
            "Your email has already been verified. "
            "You can continue your registration."
        )

        return redirect(
            "members:register_step_2"
        )

    if request.method == "POST":

        # =================================================
        # RESEND OTP
        # =================================================

        if "resend" in request.POST:

            if not can_send_otp(email):
                messages.error(
                    request,
                    "Too many attempts to send a verification "
                    "code. Please wait before trying again."
                )

                return redirect(
                    "members:register_verify_email"
                )

            # =============================================
            # GENERATE NEW OTP
            # =============================================

            otp = generate_otp()

            otp_obj = EmailOTP(
                email=email,
                purpose=(
                    EmailOTP.PURPOSE_REGISTRATION
                ),
            )

            otp_obj.set_otp(otp)
            otp_obj.save()

            # =============================================
            # SEND NEW BRANDED EMAIL
            # =============================================

            send_html_email(
                recipient=email,
                subject="New Verification Code",
                template=(
                    "members/emails/"
                    "registration_otp.html"
                ),
                context={
                    "email_title": (
                        "Email Verification"
                    ),
                    "first_name": (
                        username or "Member"
                    ),
                    "otp": otp,
                    "current_year": (
                        timezone.now().year
                    ),
                    "plain_message": (
                        f"Your new verification "
                        f"code is: {otp}"
                    ),
                },
            )

            messages.success(
                request,
                "A new verification code has been sent "
                "to your email. Use the latest code."
            )

            return redirect(
                "members:register_verify_email"
            )

        # =================================================
        # VERIFY OTP
        # =================================================

        entered = request.POST.get(
            "otp",
            ""
        ).strip()

        if not entered:
            messages.error(
                request,
                "Enter the verification code, or select "
                "Resend Code to receive a new one."
            )

            return redirect(
                "members:register_verify_email"
            )

        otp_qs = EmailOTP.objects.filter(
            email=email,
            purpose=(
                EmailOTP.PURPOSE_REGISTRATION
            ),
            is_used=False,
        ).order_by("-created_at")

        matched_otp = None

        # =============================================
        # CHECK HASHED OTP
        # =============================================

        for obj in otp_qs:
            if obj.check_otp(entered):
                matched_otp = obj
                break

        # =============================================
        # INVALID OTP
        # =============================================

        if not matched_otp:
            messages.error(
                request,
                "That verification code is invalid or has "
                "already been used. Check your email for "
                "the latest code, or select Resend Code."
            )

            return redirect(
                "members:register_verify_email"
            )

        # =============================================
        # EXPIRED OTP
        # =============================================

        if matched_otp.is_expired():
            messages.error(
                request,
                "That verification code has expired. "
                "Select Resend Code to receive a new one."
            )

            return redirect(
                "members:register_verify_email"
            )

        # =============================================
        # MARK OTP USED
        # =============================================

        matched_otp.is_used = True

        matched_otp.save(
            update_fields=["is_used"]
        )

        # =============================================
        # RECORD SUCCESSFUL VERIFICATION IN SESSION
        # =============================================

        request.session["reg_verified_email"] = email
        request.session.modified = True

        # =============================================
        # SUCCESS
        # =============================================

        messages.success(
            request,
            "Email verified successfully. "
            "You can now continue your registration."
        )

        return redirect(
            "members:register_step_2"
        )

    # =================================================
    # DISPLAY VERIFICATION PAGE
    # =================================================

    return render(
        request,
        "members/register/"
        "register_verify_email.html",
        {
            "step_num": 1,
        },
    )


# ==============================================================
# STEP 2 – MEMBER DETAILS + PARENT STATUS + ADDRESS
# ==============================================================

def register_step_2_member_profile(request):
    """
    Registration Step 2.

    Collects member details, UK mobile phone, marital status, parent
    statuses, and address. Submitted values are cached before validation
    so that an invalid submission does not lose the user's work.

    Parent status is captured here once and reused by Step 4.

    Phone numbers are normalised before duplicate checking so that
    equivalent UK mobile numbers stored in different formats are detected.
    """

    if request.user.is_authenticated:
        messages.info(
            request,
            "You are already logged in. You cannot register another account while logged in."
        )
        return redirect("members:dashboard")

    reg_user = request.session.get("reg_user")
    if not reg_user:
        messages.error(
            request,
            "Your registration session has expired. Please start again."
        )
        return redirect("members:register_step_1")
    if not _registration_email_is_verified(request, reg_user):
        messages.error(request, "Please verify your email address before continuing.")
        return redirect("members:register_verify_email")

    verified_email = _clean(reg_user.get("email")).lower()

    def render_step(
        member_data,
        address_data,
        errors=None,
        phone_error=None,
    ):
        for error in errors or []:
            messages.error(request, error)

        return render(
            request,
            "members/register/register_step_2_member_profile.html",
            {
                "step_num": 2,
                "verified_email": verified_email,
                "member": member_data,
                "address": address_data,
                "marital_status_choices": Member.MARITAL_STATUS_CHOICES,
                "parent_status_choices": Dependant.PARENT_STATUS_CHOICES,
                "phone_error": phone_error or "",
            },
        )

    if request.method == "POST":

        # ----------------------------------------------------------
        # CACHE SUBMITTED VALUES BEFORE VALIDATION
        # ----------------------------------------------------------
        marital_status = _clean(
            request.POST.get("marital_status")
        ).upper()

        mother_status = _clean(
            request.POST.get("mother_status")
        ).upper()

        father_status = _clean(
            request.POST.get("father_status")
        ).upper()

        phone_raw = _clean(request.POST.get("phone"))

        member_cache = {
            "first_name": _clean(request.POST.get("first_name")),
            "middle_name": _clean(request.POST.get("middle_name")),
            "surname": _clean(request.POST.get("surname")),
            "dob": _clean(request.POST.get("dob")),
            "phone": phone_raw,
            "marital_status": marital_status,
            "mother_status": mother_status,
            "father_status": father_status,
        }

        address_cache = {
            "house_number": _clean(request.POST.get("house_number")),
            "line_1": _clean(request.POST.get("line_1")),
            "line_2": _clean(request.POST.get("line_2")),
            "town": _clean(request.POST.get("town")),
            "county": _clean(request.POST.get("county")),
            "postcode": _clean(request.POST.get("postcode")),
            "country": _clean(request.POST.get("country")) or "UK",
        }

        request.session["reg_member"] = member_cache
        request.session["reg_address"] = address_cache
        request.session.modified = True

        if "save_draft" in request.POST:
            return _save_registration_draft_response(request, 2)

        # ----------------------------------------------------------
        # MARITAL STATUS VALIDATION
        # ----------------------------------------------------------
        valid_marital_statuses = {
            Member.MARITAL_SINGLE,
            Member.MARITAL_MARRIED,
            Member.MARITAL_WIDOWED,
            Member.MARITAL_SEPARATED,
        }

        if marital_status not in valid_marital_statuses:
            return render_step(
                member_cache,
                address_cache,
                ["Please select your marital status."],
            )

        # ----------------------------------------------------------
        # UK MOBILE FORMAT VALIDATION
        #
        # Accepted input:
        #   07123456789
        #   +447123456789
        #
        # Spaces, punctuation, letters and other formats are rejected.
        # ----------------------------------------------------------
        valid_local_format = (
            len(phone_raw) == 11
            and phone_raw.startswith("07")
            and phone_raw.isascii()
            and phone_raw.isdigit()
        )

        valid_international_format = (
            len(phone_raw) == 13
            and phone_raw.startswith("+447")
            and phone_raw[1:].isascii()
            and phone_raw[1:].isdigit()
        )

        if not (valid_local_format or valid_international_format):
            phone_error = (
                "That phone number is not in a recognised UK mobile format. "
                "Enter exactly 11 digits beginning 07 (for example, "
                "07123456789), or +447 followed by 9 digits "
                "(for example, +447123456789). Do not include spaces, "
                "letters, or punctuation."
            )

            return render_step(
                member_cache,
                address_cache,
                [phone_error],
                phone_error=phone_error,
            )

        # ----------------------------------------------------------
        # NORMALISE PHONE NUMBER
        # ----------------------------------------------------------
        try:
            phone = clean_uk_mobile(phone_raw)
        except ValidationError as exc:
            phone_error = exc.messages[0]

            return render_step(
                member_cache,
                address_cache,
                [phone_error],
                phone_error=phone_error,
            )

        # ----------------------------------------------------------
        # DUPLICATE PHONE CHECK
        #
        # Compare normalised values, not only the raw database value.
        # This detects equivalent numbers stored in formats such as:
        #   +447123456789
        #   07123456789
        #   +44 7123 456789 (legacy formatted value)
        #
        # Invalid legacy values are ignored rather than preventing
        # registration for unrelated reasons.
        # ----------------------------------------------------------
        duplicate_phone = False

        existing_phones = (
            Member.objects
            .exclude(phone="")
            .exclude(phone__isnull=True)
            .values_list("phone", flat=True)
        )

        for existing_phone in existing_phones:
            try:
                existing_normalised_phone = clean_uk_mobile(
                    existing_phone
                )
            except ValidationError:
                # Ignore legacy values that are not valid UK mobiles.
                continue

            if existing_normalised_phone == phone:
                duplicate_phone = True
                break

        if duplicate_phone:
            phone_error = (
                "This phone number is already registered. "
                "Please use a different phone number."
            )

            # Keep the originally submitted phone in the form so the
            # user can correct it without losing the rest of the form.
            member_cache["phone"] = phone_raw
            request.session["reg_member"] = member_cache
            request.session.modified = True

            return render_step(
                member_cache,
                address_cache,
                [phone_error],
                phone_error=phone_error,
            )

        # Store the centrally normalised phone only after it passes
        # both format validation and duplicate checking.
        member_cache["phone"] = phone

        # ----------------------------------------------------------
        # PARENT STATUS VALIDATION
        # ----------------------------------------------------------
        valid_parent_statuses = {
            Dependant.PARENT_ALIVE,
            Dependant.PARENT_DECEASED,
            Dependant.PARENT_UNKNOWN,
        }

        parent_errors = []

        if mother_status not in valid_parent_statuses:
            parent_errors.append(
                "Please select the status of the Mother."
            )

        if father_status not in valid_parent_statuses:
            parent_errors.append(
                "Please select the status of the Father."
            )

        if parent_errors:
            request.session["reg_member"] = member_cache
            request.session["reg_address"] = address_cache
            request.session.modified = True

            return render_step(
                member_cache,
                address_cache,
                parent_errors,
            )

        # ----------------------------------------------------------
        # SAVE VALIDATED SESSION DATA AND CONTINUE
        # ----------------------------------------------------------
        request.session["reg_member"] = member_cache
        request.session["reg_address"] = address_cache
        request.session.modified = True

        return redirect("members:register_step_3")

    # ----------------------------------------------------------
    # GET: RESTORE CACHED VALUES
    # ----------------------------------------------------------
    return render_step(
        request.session.get("reg_member", {}),
        request.session.get("reg_address", {}),
    )


# ==============================================================
# STEP 3 – NEXT OF KIN
# backend/members/views_frontend/register_flow.py
# ==============================================================


def register_step_3_next_of_kin(request):
    """Collect and validate Next of Kin information for registration."""

    if request.user.is_authenticated:
        messages.info(
            request,
            "You are already logged in. You cannot register another account while logged in."
        )
        return redirect("members:dashboard")

    reg_user = request.session.get("reg_user")
    if not reg_user:
        messages.error(request, "Your registration session has expired. Please start again.")
        return redirect("members:register_step_1")
    if not _registration_email_is_verified(request, reg_user):
        messages.error(request, "Please verify your email address before continuing.")
        return redirect("members:register_verify_email")
    if "reg_member" not in request.session:
        return redirect("members:register_step_2")

    nok = request.session.get("reg_nok", {})
    member_email = (
        request.session.get("reg_user", {}).get("email", "")
        .strip()
        .lower()
    )

    if request.method == "POST":
        first_name = _clean(request.POST.get("first_name"))
        middle_name = _clean(request.POST.get("middle_name"))
        surname = _clean(request.POST.get("surname"))
        relationship = _clean(request.POST.get("relationship"))
        phone_raw = _clean(request.POST.get("phone"))
        email_raw = _clean(request.POST.get("email")).lower()

        if "save_draft" in request.POST:
            request.session["reg_nok"] = {
                "first_name": first_name,
                "middle_name": middle_name,
                "surname": surname,
                "relationship": relationship,
                "phone": phone_raw,
                "email": email_raw,
            }
            request.session.modified = True
            return _save_registration_draft_response(request, 3)

        errors = []
        phone_error = ""
        email_error = ""

        if not first_name:
            errors.append("Please enter the Next of Kin first name.")

        if not surname:
            errors.append("Please enter the Next of Kin surname.")

        if not relationship:
            errors.append("Please select the Next of Kin relationship.")

        # NEXT OF KIN PHONE VALIDATION
        # International formats are accepted. Count digits only;
        # allow +, spaces, parentheses, dots and hyphens.
        # Preserve the entered format; do not normalise to +44.
        allowed_phone_format = re.fullmatch(r"\+?[0-9\s().-]+", phone_raw)
        digit_count = len(re.sub(r"\D", "", phone_raw))

        if not phone_raw:
            phone_error = "Enter a Next of Kin phone number."
        elif not allowed_phone_format:
            phone_error = (
                "The phone number may contain digits and common formatting "
                "characters only. Letters and other characters are not allowed."
            )
        elif not 4 <= digit_count <= 15:
            phone_error = (
                "The Next of Kin phone number must contain between 4 and 15 digits."
            )

        if phone_error:
            errors.append(phone_error)
            phone = ""
        else:
            # Keep the user's international number and formatting as entered.
            phone = phone_raw

        # EMAIL VALIDATION — preserve the existing business rule.
        try:
            nok_email = validate_email_address(email_raw)
        except ValidationError as exc:
            email_error = exc.messages[0]
            errors.append(email_error)
            nok_email = ""

        if nok_email and nok_email.lower() == member_email:
            email_error = (
                "The Next of Kin email address must be different from "
                "your own verified email address."
            )
            errors.append(email_error)

        if errors:
            return render(
                request,
                "members/register/register_step_3_next_of_kin.html",
                {
                    "step_num": 3,
                    "nok": request.POST,
                    "errors": errors,
                    "phone_error": phone_error,
                    "email_error": email_error,
                    "member_email": member_email,
                },
            )

        request.session["reg_nok"] = {
            "first_name": first_name,
            "middle_name": middle_name,
            "surname": surname,
            "relationship": relationship,
            "phone": phone,
            "email": nok_email,
        }
        request.session.modified = True

        return redirect("members:register_step_4")

    return render(
        request,
        "members/register/register_step_3_next_of_kin.html",
        {
            "step_num": 3,
            "nok": nok,
            "member_email": member_email,
            "errors": [],
            "phone_error": "",
            "email_error": "",
        },
    )

def register_step_4_dependants(request):
    """
    Registration Step 4.

    Parent eligibility is determined exclusively by the Mother/Father
    statuses captured in Step 2 and stored in the registration session.

    Only a parent whose Step 2 status is ALIVE may be registered as a
    new dependant.

    Deceased and Unknown parents must not be created as new dependants.
    No parent status is accepted from POST.

    Submitted dependant data is cached before validation errors are
    returned so that the member can correct the information without
    losing the other dependant details.
    """

    # --------------------------------------------------
    # REGISTRATION ACCESS GUARDS
    # --------------------------------------------------
    if request.user.is_authenticated:
        messages.info(
            request,
            "You are already logged in. You cannot register another account while logged in."
        )
        return redirect("members:dashboard")

    reg_user = request.session.get("reg_user")
    if not reg_user:
        messages.error(
            request,
            "Your registration session has expired. Please start again."
        )
        return redirect("members:register_step_1")

    if not _registration_email_is_verified(request, reg_user):
        messages.error(
            request,
            "Please verify your email address before continuing."
        )
        return redirect("members:register_verify_email")

    if "reg_nok" not in request.session:
        return redirect("members:register_step_3")

    # --------------------------------------------------
    # AUTHORITATIVE STEP 2 DATA
    # --------------------------------------------------
    reg_member = request.session.get("reg_member", {})

    marital_status = _clean(
        reg_member.get("marital_status")
    ).upper()

    parent_statuses = {
        "MOTHER": _clean(
            reg_member.get("mother_status")
        ).upper(),
        "FATHER": _clean(
            reg_member.get("father_status")
        ).upper(),
    }

    # --------------------------------------------------
    # PROCESS STEP 4 SUBMISSION
    # --------------------------------------------------
    if request.method == "POST":

        indexes_raw = request.POST.get("dependant_indexes", "")

        # Keep only numeric indexes and remove repeated indexes.
        # A repeated index must never create a second copy of the
        # same submitted dependant.
        indexes = list(dict.fromkeys(
            index.strip()
            for index in indexes_raw.split(",")
            if index.strip().isdigit()
        ))

        dependants = []
        validation_errors = []

        for number, index in enumerate(indexes, start=1):

            # --------------------------------------------------
            # READ THE SUBMITTED DEPENDANT FIELDS
            # --------------------------------------------------
            first = _clean(
                request.POST.get(f"dep_{index}_first")
            )
            middle = _clean(
                request.POST.get(f"dep_{index}_middle")
            )
            surname = _clean(
                request.POST.get(f"dep_{index}_surname")
            )
            relationship = _clean(
                request.POST.get(f"dep_{index}_relation")
            ).upper()
            dob = _clean(
                request.POST.get(f"dep_{index}_dob")
            )
            parent_type = _clean(
                request.POST.get(f"dep_{index}_parent_type")
            ).upper()
            country = _clean(
                request.POST.get(f"dep_{index}_country")
            )
            county = _clean(
                request.POST.get(f"dep_{index}_county")
            )
            sub_county_town = _clean(
                request.POST.get(f"dep_{index}_sub_county_town")
            )

            # Never read parent_status from POST.
            parent_status = ""

            # --------------------------------------------------
            # VALIDATE RELATIONSHIP
            # --------------------------------------------------
            valid_relationships = {
                Dependant.TYPE_CHILD,
                Dependant.TYPE_SPOUSE,
                Dependant.TYPE_SIBLING,
                Dependant.TYPE_PARENT,
            }

            if relationship not in valid_relationships:
                validation_errors.append(
                    f"Please select a valid relationship for Dependant {number}."
                )

            # --------------------------------------------------
            # PARENT ELIGIBILITY — STEP 2 IS AUTHORITATIVE
            # --------------------------------------------------
            if relationship == Dependant.TYPE_PARENT:

                if parent_type not in {"MOTHER", "FATHER"}:
                    validation_errors.append(
                        f"Please select Mother or Father for Parent {number}."
                    )
                else:
                    # Derive the status from Step 2, never from POST.
                    parent_status = parent_statuses.get(
                        parent_type,
                        ""
                    )

                    if parent_status != Dependant.PARENT_ALIVE:
                        validation_errors.append(
                            f"Parent {number} cannot be registered because "
                            "the selected parent's status in Step 2 is not Alive. "
                            "Please review the parent details in Step 2."
                        )

                # --------------------------------------------------
                # ALIVE PARENT DETAILS
                # --------------------------------------------------
                if parent_status == Dependant.PARENT_ALIVE:

                    if not first:
                        validation_errors.append(
                            f"Please enter the first name for Parent {number}."
                        )

                    if not surname:
                        validation_errors.append(
                            f"Please enter the surname for Parent {number}."
                        )

                    if not dob:
                        validation_errors.append(
                            f"Please enter the date of birth for Parent {number}."
                        )

                    if not country:
                        validation_errors.append(
                            f"Please enter the country for Parent {number}."
                        )

                    if not county:
                        validation_errors.append(
                            f"Please enter the county for Parent {number}."
                        )

                    if not sub_county_town:
                        validation_errors.append(
                            f"Please enter the sub-county / town for Parent {number}."
                        )

            # --------------------------------------------------
            # CHILD DETAILS
            # --------------------------------------------------
            elif relationship == Dependant.TYPE_CHILD:

                # Parent-specific data must not be carried by a child.
                parent_type = ""
                parent_status = ""

                # Preserve the existing Child location behaviour.
                country = ""
                county = ""
                sub_county_town = ""

                if not first:
                    validation_errors.append(
                        f"Please enter the first name for Dependant {number}."
                    )

                if not surname:
                    validation_errors.append(
                        f"Please enter the surname for Dependant {number}."
                    )

                if not dob:
                    validation_errors.append(
                        f"Please enter the date of birth for Dependant {number}."
                    )

            # --------------------------------------------------
            # SPOUSE AND SIBLING DETAILS
            # --------------------------------------------------
            elif relationship in {
                Dependant.TYPE_SPOUSE,
                Dependant.TYPE_SIBLING,
            }:

                # These relationships must not carry parent information.
                parent_type = ""
                parent_status = ""

                if not first:
                    validation_errors.append(
                        f"Please enter the first name for {relationship.title()} {number}."
                    )

                if not surname:
                    validation_errors.append(
                        f"Please enter the surname for {relationship.title()} {number}."
                    )

                if not dob:
                    validation_errors.append(
                        f"Please enter the date of birth for {relationship.title()} {number}."
                    )

                if not country:
                    validation_errors.append(
                        f"Please enter the country for {relationship.title()} {number}."
                    )

                if not county:
                    validation_errors.append(
                        f"Please enter the county for {relationship.title()} {number}."
                    )

                if not sub_county_town:
                    validation_errors.append(
                        f"Please enter the sub-county / town for {relationship.title()} {number}."
                    )

            # --------------------------------------------------
            # PRESERVE THIS DEPENDANT IN THE SESSION
            # --------------------------------------------------
            dependants.append({
                "first_name": first,
                "middle_name": middle,
                "surname": surname,
                "relationship": relationship,
                "dob": dob or None,
                "parent_type": parent_type,
                "parent_status": parent_status,
                "country": country,
                "county": county,
                "sub_county_town": sub_county_town,
            })

        # --------------------------------------------------
        # SAVE DRAFT
        # --------------------------------------------------
        if "save_draft" in request.POST:
            request.session["reg_dependants"] = dependants
            request.session.modified = True

            return _save_registration_draft_response(request, 4)

        # --------------------------------------------------
        # DEPENDANT LIMITS
        # --------------------------------------------------
        spouse_count = sum(
            dependant.get("relationship") == Dependant.TYPE_SPOUSE
            for dependant in dependants
        )

        parent_count = sum(
            dependant.get("relationship") == Dependant.TYPE_PARENT
            for dependant in dependants
        )

        mother_count = sum(
            dependant.get("relationship") == Dependant.TYPE_PARENT
            and dependant.get("parent_type") == Dependant.PARENT_MOTHER
            for dependant in dependants
        )

        father_count = sum(
            dependant.get("relationship") == Dependant.TYPE_PARENT
            and dependant.get("parent_type") == Dependant.PARENT_FATHER
            for dependant in dependants
        )

        # --------------------------------------------------
        # SPOUSE LIMITS
        # --------------------------------------------------
        if spouse_count > 1:
            validation_errors.append(
                "Only one spouse can be registered."
            )

        if marital_status == Member.MARITAL_MARRIED:
            if spouse_count == 0:
                validation_errors.append(
                    "Married members must register exactly one spouse."
                )

        elif spouse_count > 0:
            validation_errors.append(
                "A spouse can only be registered when the member's "
                "marital status is Married."
            )

        # --------------------------------------------------
        # PARENT LIMITS
        # --------------------------------------------------
        if parent_count > 2:
            validation_errors.append(
                "A maximum of two parents can be registered."
            )

        if mother_count > 1:
            validation_errors.append(
                "Only one mother can be registered."
            )

        if father_count > 1:
            validation_errors.append(
                "Only one father can be registered."
            )

        # --------------------------------------------------
        # CACHE BEFORE RETURNING VALIDATION ERRORS
        # --------------------------------------------------
        request.session["reg_dependants"] = dependants
        request.session.modified = True

        if validation_errors:
            for error in validation_errors:
                messages.error(request, error)

            return render(
                request,
                "members/register/register_step_4_dependants.html",
                {
                    "step_num": 4,
                    "dependants": dependants,
                    "marital_status": marital_status,
                    "mother_status": parent_statuses.get("MOTHER", ""),
                    "father_status": parent_statuses.get("FATHER", ""),
                },
            )

        return redirect("members:register_step_5")

    # --------------------------------------------------
    # GET — RESTORE SAVED DEPENDANTS
    # --------------------------------------------------
    dependants = request.session.get("reg_dependants", [])

    return render(
        request,
        "members/register/register_step_4_dependants.html",
        {
            "step_num": 4,
            "dependants": dependants,
            "marital_status": marital_status,
            "mother_status": parent_statuses.get("MOTHER", ""),
            "father_status": parent_statuses.get("FATHER", ""),
        },
    )

# ======================================================
# ADDRESS CREATION (DEDUP SAFE)
# ======================================================
def create_address_from_session(request):
    """
    Creates or reuses an Address.
    Prevents duplicates using get_or_create.
    """

    data = request.session.get("reg_address", {})

    # ✅ Safety check
    if not data:
        return None

    address, _ = Address.objects.get_or_create(
        house_number=data.get("house_number", ""),
        line_1=data.get("line_1", ""),
        town=data.get("town", ""),
        postcode=data.get("postcode", ""),
        defaults={
            "line_2": data.get("line_2", ""),
            "county": data.get("county", ""),
            "country": data.get("country", "UK"),
        }
    )

    return address


# ==============================================================
# STEP 5 – CONFIRM & SAVE
# backend/members/views_frontend/register_flow.py
# ==============================================================

@transaction.atomic
def register_step_5_confirmation(request):
    """
    Final registration step.

    Preserves the existing duplicate checks, registration flow,
    User/Address/Member/NextOfKin creation and session cleanup.

    Database creation runs inside a nested atomic block so an
    IntegrityError can be handled without breaking the outer
    transaction.

    Only validated dependants are created.
    All newly registered dependants begin as pending.
    Deceased and Unknown parents are not created as dependants.
    """

    if request.user.is_authenticated:
        messages.info(
            request,
            "You are already logged in. You cannot register "
            "another account while logged in."
        )
        return redirect("members:dashboard")

    reg_user = request.session.get("reg_user")
    reg_member = request.session.get("reg_member")
    reg_nok = request.session.get("reg_nok")
    reg_dependants = request.session.get("reg_dependants", [])

    if not all([reg_user, reg_member, reg_nok]):
        messages.error(
            request,
            "Your registration session is incomplete. "
            "Please start again."
        )
        return redirect("members:register_step_1")
    if not _registration_email_is_verified(request, reg_user):
        messages.error(request, "Please verify your email address before completing registration.")
        return redirect("members:register_verify_email")
    if request.method == "POST" and "save_draft" in request.POST:
        return _save_registration_draft_response(request, 5)

    # ----------------------------------------------------------
    # REGISTRATION EMAIL
    # ----------------------------------------------------------
    registration_email = _clean(
        reg_user.get("email")
    ).lower()

    marital_status = _clean(
        reg_member.get("marital_status")
    ).upper()

    # ----------------------------------------------------------
    # FINAL SERVER-SIDE DEPENDANT VALIDATION
    # ----------------------------------------------------------
    parent_statuses = {
        "MOTHER": _clean(
            reg_member.get("mother_status")
        ).upper(),
        "FATHER": _clean(
            reg_member.get("father_status")
        ).upper(),
    }

    final_errors = validate_registration_dependants(
        dependants=reg_dependants,
        marital_status=marital_status,
        parent_statuses=parent_statuses,
    )

    if final_errors:
        for error in final_errors:
            messages.error(request, error)

        request.session["reg_dependants"] = reg_dependants
        request.session.modified = True

        return redirect("members:register_step_4")

    if request.method == "POST":
        username = _clean(reg_user.get("username"))

        # ------------------------------------------------------
        # FINAL EMAIL VALIDATION
        # ------------------------------------------------------
        try:
            registration_email = validate_email_address(
                registration_email
            )
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return redirect("members:register_step_1")

        # ------------------------------------------------------
        # DUPLICATE CHECKS
        # ------------------------------------------------------
        if User.objects.filter(
            email__iexact=registration_email
        ).exists():
            messages.error(
                request,
                "An account with this email address already "
                "exists. Please log in or use a different "
                "email address."
            )
            return redirect("members:register_step_1")

        if Member.objects.filter(
            email__iexact=registration_email
        ).exists():
            messages.error(
                request,
                "This email address is already registered "
                "as a member."
            )
            return redirect("members:register_step_1")

        if User.objects.filter(
            username__iexact=username
        ).exists():
            messages.error(
                request,
                "That username is already in use."
            )
            return redirect("members:register_step_1")

        # ------------------------------------------------------
        # CREATE ALL REGISTRATION RECORDS ATOMICALLY
        # ------------------------------------------------------
        try:
            with transaction.atomic():

                # USER
                # Current sessions store a Django password hash, not plaintext.
                # The fallback supports a registration session created by an older deployment.
                user = User(
                    username=username,
                    email=registration_email,
                )
                stored_password_hash = reg_user.get("password_hash")
                if stored_password_hash:
                    user.password = stored_password_hash
                else:
                    user.set_password(reg_user.get("password") or "")
                user.save()

                # ADDRESS
                address = create_address_from_session(request)

                # MEMBER
                # Parent statuses are Member registration information.
                # Keep both values when creating the Member.
                member_data = dict(reg_member)

                member = Member.objects.create(
                    user=user,
                    address=address,
                    email=user.email,
                    can_edit=False,
                    gdpr_consent=True,
                    gdpr_consent_at=timezone.now(),
                    gdpr_consent_ip=get_client_ip(request),
                    gdpr_version="v1",
                    **member_data,
                )

                # NEXT OF KIN
                NextOfKin.objects.create(
                    member=member,
                    **reg_nok,
                )

                # --------------------------------------------------
                # DEPENDANTS
                # --------------------------------------------------
                dependants = []

                for dependant_data in reg_dependants:

                    # Work on a copy so that the registration session
                    # remains unchanged if database creation fails.
                    dependant_data = dict(dependant_data)

                    relationship = _clean(
                        dependant_data.get("relationship")
                    ).upper()

                    # Step 5 validation has already confirmed that
                    # every parent is eligible (Alive) using the
                    # authoritative Step 2 session values.
                    #
                    # Parent status belongs to the Member record.
                    # Do not persist it again on a newly-created
                    # Dependant record.
                    dependant_data.pop("parent_status", None)

                    # Never allow a cached/session value to override
                    # the registration status assigned here.
                    dependant_data.pop("status", None)

                    # Every newly registered dependant starts pending.
                    dependant_data["status"] = (
                        Dependant.STATUS_PENDING
                    )

                    dependants.append(
                        Dependant(
                            member=member,
                            **dependant_data,
                        )
                    )

                # Create the validated dependant records together.
                Dependant.objects.bulk_create(dependants)

        except IntegrityError:
            # The inner atomic block has rolled back before
            # execution reaches this handler.
            messages.error(
                request,
                "Registration could not be completed because "
                "some details conflict with existing records "
                "or could not be saved. Please review your "
                "details and try again. Your registration "
                "session has been retained."
            )

            return render(
                request,
                "members/register/register_step_5_confirmation.html",
                {
                    "step_num": 5,
                    "member": reg_member,
                    "verified_email": registration_email,
                    "address": request.session.get(
                        "reg_address", {}
                    ),
                    "nok": reg_nok,
                    "dependants": reg_dependants,
                },
            )

        # ------------------------------------------------------
        # COMPLETE THE DRAFT ONLY AFTER SUCCESSFUL REGISTRATION
        # ------------------------------------------------------
        draft_id = request.session.get("registration_draft_id")
        if draft_id:
            RegistrationDraft.objects.filter(
                pk=draft_id,
                is_active=True,
                completed_at__isnull=True,
            ).update(
                completed_at=timezone.now(),
                is_active=False,
            )

        # ------------------------------------------------------
        # CLEAR REGISTRATION SESSION ONLY AFTER SUCCESS
        # ------------------------------------------------------
        for key in [
            "reg_user",
            "reg_member",
            "reg_nok",
            "reg_dependants",
            "reg_address",
            "reg_verified_email",
            "registration_draft_id",
        ]:
            request.session.pop(key, None)

        messages.success(
            request,
            "Registration completed."
        )

        return redirect("members:login")

    # ----------------------------------------------------------
    # GET: DISPLAY CONFIRMATION PAGE
    # ----------------------------------------------------------
    return render(
        request,
        "members/register/register_step_5_confirmation.html",
        {
            "step_num": 5,
            "member": reg_member,
            "verified_email": registration_email,
            "address": request.session.get("reg_address", {}),
            "nok": reg_nok,
            "dependants": reg_dependants,
        },
    )


# ======================================================
# ENTRY POINTS
# ======================================================

def register_start(request):
    """
    Entry point for registration.
    """

    if request.user.is_authenticated:
        messages.info(
            request,
            "You are already logged in. You cannot register "
            "another account while logged in."
        )
        return redirect("members:dashboard")

    return render(
        request,
        "members/register/register_step_1_user.html",
        {
            "recaptcha_site_key": settings.RECAPTCHA_SITE_KEY,
            "debug": settings.DEBUG,
        },
    )


def register_submit(request):
    """
    Legacy handler (can be removed if unused).
    """
    if request.method == "POST":
        return redirect("members:login")

    return redirect("members:register_step_1")
