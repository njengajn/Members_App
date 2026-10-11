from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect
from django.db import transaction, IntegrityError
from backend.members.models import Member, NextOfKin, Dependant, Address
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


def validate_registration_dependants(dependants, marital_status):
    """
    Final authoritative validation used by Step 5.

    Parent status must already be present in each dependant record by
    the time this function runs. Step 4 obtains that status from the
    Mother/Father status captured in Step 2.
    """

    errors = []

    valid_relationships = {
        Dependant.TYPE_CHILD,
        Dependant.TYPE_SPOUSE,
        Dependant.TYPE_SIBLING,
        Dependant.TYPE_PARENT,
    }

    spouse_count = 0
    mother_count = 0
    father_count = 0

    for number, dependant in enumerate(dependants, start=1):
        relationship = _clean(dependant.get("relationship")).upper()
        parent_type = _clean(dependant.get("parent_type")).upper()
        parent_status = _clean(dependant.get("parent_status")).upper()

        country = _clean(dependant.get("country"))
        county = _clean(dependant.get("county"))
        sub_county_town = _clean(dependant.get("sub_county_town"))

        if relationship not in valid_relationships:
            errors.append(
                f"Dependant {number}: Please select a valid relationship."
            )
            continue

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

        elif relationship == Dependant.TYPE_PARENT:
            if parent_type not in {
                Dependant.PARENT_MOTHER,
                Dependant.PARENT_FATHER,
            }:
                errors.append(
                    f"Dependant {number}: Please select Mother or Father."
                )
            elif parent_type == Dependant.PARENT_MOTHER:
                mother_count += 1
            elif parent_type == Dependant.PARENT_FATHER:
                father_count += 1

            if parent_status not in {
                Dependant.PARENT_ALIVE,
                Dependant.PARENT_DECEASED,
                Dependant.PARENT_UNKNOWN,
            }:
                errors.append(
                    f"Dependant {number}: Please select a valid parent status in Step 2."
                )
                continue

            if parent_status == Dependant.PARENT_UNKNOWN:
                # UNKNOWN must contain no identifying/location details.
                forbidden_fields = (
                    "first_name",
                    "middle_name",
                    "surname",
                    "dob",
                    "country",
                    "county",
                    "sub_county_town",
                )

                if any(dependant.get(field) for field in forbidden_fields):
                    errors.append(
                        f"Dependant {number}: An Unknown parent must not contain a name, date of birth or location."
                    )

                continue

            if not dependant.get("first_name"):
                errors.append(
                    f"Dependant {number}: First name is required."
                )

            if not dependant.get("surname"):
                errors.append(
                    f"Dependant {number}: Surname is required."
                )

            if not dependant.get("dob"):
                errors.append(
                    f"Dependant {number}: Date of birth is required."
                )

            if parent_status == Dependant.PARENT_ALIVE:
                for field, label in (
                    (country, "Country"),
                    (county, "County"),
                    (sub_county_town, "Sub-county / Town"),
                ):
                    if not field:
                        errors.append(
                            f"Dependant {number}: {label} is required for a living parent."
                        )
            else:
                dependant["country"] = ""
                dependant["county"] = ""
                dependant["sub_county_town"] = ""

        elif relationship == Dependant.TYPE_CHILD:
            dependant["parent_type"] = ""
            dependant["parent_status"] = ""
            dependant["country"] = ""
            dependant["county"] = ""
            dependant["sub_county_town"] = ""

            if not dependant.get("first_name"):
                errors.append(
                    f"Dependant {number}: First name is required."
                )
            if not dependant.get("surname"):
                errors.append(
                    f"Dependant {number}: Surname is required."
                )
            if not dependant.get("dob"):
                errors.append(
                    f"Dependant {number}: Date of birth is required."
                )

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
        errors.append("Please select a valid marital status.")

    if mother_count > 1:
        errors.append("Only one Mother can be registered.")

    if father_count > 1:
        errors.append("Only one Father can be registered.")

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
            "password": password,
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

    Parent status is NOT collected again here.
    It was captured in Step 2 for Mother and Father and is read from
    reg_member. Step 4 only identifies which parent is being registered.

    UNKNOWN parent rules:
        - Parent type must be Mother or Father.
        - The corresponding Step 2 status must be UNKNOWN.
        - No name, DOB or location may be supplied.

    Alive parent rules:
        - Name and DOB are required.
        - Country, county and sub-county/town are required.

    Deceased parent rules:
        - Name and DOB may be supplied.
        - Parent location is not required.

    All submitted dependant data is cached before validation errors are
    returned so Back/Next navigation does not lose entered information.
    """

    if request.user.is_authenticated:
        messages.info(
            request,
            "You are already logged in. You cannot register another account while logged in."
        )
        return redirect("members:dashboard")

    if "reg_nok" not in request.session:
        return redirect("members:register_step_3")

    reg_member = request.session.get("reg_member", {})
    marital_status = _clean(
        reg_member.get("marital_status")
    ).upper()

    parent_statuses = {
        "MOTHER": _clean(reg_member.get("mother_status")).upper(),
        "FATHER": _clean(reg_member.get("father_status")).upper(),
    }

    if request.method == "POST":
        indexes_raw = request.POST.get("dependant_indexes", "")

        indexes = [
            index.strip()
            for index in indexes_raw.split(",")
            if index.strip().isdigit()
        ]

        dependants = []
        validation_errors = []

        for number, index in enumerate(indexes, start=1):
            first = _clean(request.POST.get(f"dep_{index}_first"))
            middle = _clean(request.POST.get(f"dep_{index}_middle"))
            surname = _clean(request.POST.get(f"dep_{index}_surname"))
            relationship = _clean(
                request.POST.get(f"dep_{index}_relation")
            ).upper()
            dob = _clean(request.POST.get(f"dep_{index}_dob"))
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

            parent_status = ""

            # --------------------------------------------------
            # RELATIONSHIP
            # --------------------------------------------------
            if relationship not in {
                Dependant.TYPE_CHILD,
                Dependant.TYPE_SPOUSE,
                Dependant.TYPE_SIBLING,
                Dependant.TYPE_PARENT,
            }:
                validation_errors.append(
                    f"Please select a valid relationship for Dependant {number}."
                )

            # --------------------------------------------------
            # PARENT STATUS COMES FROM STEP 2
            # --------------------------------------------------
            if relationship == Dependant.TYPE_PARENT:
                if parent_type not in {"MOTHER", "FATHER"}:
                    validation_errors.append(
                        f"Please select Mother or Father for Parent {number}."
                    )
                else:
                    parent_status = parent_statuses.get(parent_type, "")

                    if parent_status not in {
                        Dependant.PARENT_ALIVE,
                        Dependant.PARENT_DECEASED,
                        Dependant.PARENT_UNKNOWN,
                    }:
                        validation_errors.append(
                            f"The status for the selected Parent {number} is missing or invalid. Return to Step 2."
                        )

            # --------------------------------------------------
            # BASIC DETAILS
            # --------------------------------------------------
            is_unknown_parent = (
                relationship == Dependant.TYPE_PARENT
                and parent_status == Dependant.PARENT_UNKNOWN
            )

            if is_unknown_parent:
                # UNKNOWN is deliberate: no identifying or location data.
                first = ""
                middle = ""
                surname = ""
                dob = ""
                country = ""
                county = ""
                sub_county_town = ""

            else:
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
            # NORMALISE CHILD
            # --------------------------------------------------
            if relationship == Dependant.TYPE_CHILD:
                parent_type = ""
                parent_status = ""
                country = ""
                county = ""
                sub_county_town = ""

            # --------------------------------------------------
            # PARENT LOCATION
            # --------------------------------------------------
            if relationship == Dependant.TYPE_PARENT:
                if parent_status == Dependant.PARENT_ALIVE:
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
                elif parent_status in {
                    Dependant.PARENT_DECEASED,
                    Dependant.PARENT_UNKNOWN,
                }:
                    country = ""
                    county = ""
                    sub_county_town = ""

            # --------------------------------------------------
            # SPOUSE / SIBLING LOCATION
            # --------------------------------------------------
            if relationship in {
                Dependant.TYPE_SPOUSE,
                Dependant.TYPE_SIBLING,
            }:
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
        # LIMITS
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

        if spouse_count > 1:
            validation_errors.append("Only one spouse can be registered.")

        if parent_count > 2:
            validation_errors.append("A maximum of two parents can be registered.")

        if mother_count > 1:
            validation_errors.append("Only one mother can be registered.")

        if father_count > 1:
            validation_errors.append("Only one father can be registered.")

        if spouse_count and marital_status != Member.MARITAL_MARRIED:
            validation_errors.append(
                "A spouse can only be registered when the member's marital status is Married."
            )

        # --------------------------------------------------
        # CACHE BEFORE RETURNING ERRORS
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

    Deceased and Unknown parents are created as retired.
    All other dependants begin as pending.
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
    final_errors = validate_registration_dependants(
        dependants=reg_dependants,
        marital_status=marital_status,
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
                user = User.objects.create_user(
                    username=username,
                    email=registration_email,
                    password=reg_user.get("password"),
                )

                # ADDRESS
                address = create_address_from_session(request)

                # MEMBER
                # Mother/Father status belongs to the dependant
                # record, not the Member model.
                member_data = dict(reg_member)
                member_data.pop("mother_status", None)
                member_data.pop("father_status", None)

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

                # DEPENDANTS
                dependants = []

                for dependant_data in reg_dependants:
                    dependant_data = dict(dependant_data)

                    relationship = _clean(
                        dependant_data.get("relationship")
                    ).upper()

                    parent_status = _clean(
                        dependant_data.get("parent_status")
                    ).upper()

                    # UNKNOWN and DECEASED parents must be retired.
                    if (
                        relationship == Dependant.TYPE_PARENT
                        and parent_status in {
                            Dependant.PARENT_UNKNOWN,
                            Dependant.PARENT_DECEASED,
                        }
                    ):
                        dependant_data["status"] = (
                            Dependant.STATUS_RETIRED
                        )
                    else:
                        dependant_data["status"] = (
                            Dependant.STATUS_PENDING
                        )

                    dependants.append(
                        Dependant(
                            member=member,
                            **dependant_data,
                        )
                    )

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
        # CLEAR REGISTRATION SESSION ONLY AFTER SUCCESS
        # ------------------------------------------------------
        for key in [
            "reg_user",
            "reg_member",
            "reg_nok",
            "reg_dependants",
            "reg_address",
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
