from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import render, redirect
from django.db import transaction
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

otp = generate_otp()

User = get_user_model()


def register_step_1_user(request):
    """
    Registration step 1.

    - validates registration
    - generates OTP
    - sends branded verification email
    """

    if request.method == "POST":

        username = request.POST.get("username")
        password = request.POST.get("password")
        confirm = request.POST.get("confirm_password")
        email = request.POST.get("email")

        # =================================================
        # GDPR CONSENT
        # =================================================

        gdpr_consent = request.POST.get("gdpr_consent")

        if not gdpr_consent:

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
        # PASSWORD CHECK
        # =================================================

        if password != confirm:

            messages.error(
                request,
                "Passwords do not match."
            )

            return redirect("members:register_step_1")

        # =================================================
        # DUPLICATE USERNAME / EMAIL CHECK
        # =================================================

        # Existing Django username
        if User.objects.filter(username__iexact=username).exists():

            messages.error(
                request,
                "That username is already in use."
            )

            return redirect("members:register_step_1")

        # Existing Django user email
        if User.objects.filter(email__iexact=email).exists():

            messages.error(
                request,
                "An account with this email address already exists."
            )

            return redirect("members:register_step_1")

        # Existing member email (extra safety)
        if Member.objects.filter(email__iexact=email).exists():

            messages.error(
                request,
                "This email address is already registered as a member."
            )

            return redirect("members:register_step_1")

        # =================================================
        # RATE LIMIT
        # =================================================

        if not can_send_otp(email):

            messages.error(
                request,
                "Too many attempts."
            )

            return redirect("members:register_step_1")

        # =================================================
        # GENERATE OTP
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

        # =================================================
        # SEND OTP EMAIL
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
                "plain_message": f"Your verification code is: {otp}",
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

    ✔ Check hashed OTP
    ✔ Check expiry
    ✔ Mark used
    ✔ Resend supported
    ✔ Uses branded HTML emails
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

    if request.method == "POST":

        # =================================================
        # RESEND OTP
        # =================================================

        if "resend" in request.POST:

            if not can_send_otp(email):

                messages.error(
                    request,
                    "Too many attempts."
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
                        f"Your new "
                        f"verification code "
                        f"is: {otp}"
                    ),
                },
            )

            messages.success(
                request,
                "New verification code sent."
            )

            return redirect(
                "members:register_verify_email"
            )

        # =================================================
        # VERIFY OTP
        # =================================================

        entered = request.POST.get("otp")

        otp_qs = EmailOTP.objects.filter(

            email=email,

            purpose=(
                EmailOTP.PURPOSE_REGISTRATION
            ),

            is_used=False

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
                "Invalid code."
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
                "Code expired."
            )

            return redirect(
                "members:register_verify_email"
            )

        # =============================================
        # MARK USED
        # =============================================

        matched_otp.is_used = True

        matched_otp.save(
            update_fields=["is_used"]
        )

        # =============================================
        # SUCCESS
        # =============================================

        messages.success(
            request,
            "Email verified successfully."
        )

        return redirect(
            "members:register_step_2"
        )
    
    return render(

        request,

        "members/register/"
        "register_verify_email.html",

        {
            "step_num": 1,
        },
    )

# ======================================================
# STEP 2 – MEMBER DETAILS + ADDRESS
# ======================================================
def register_step_2_member_profile(request):
    """
    STEP 2

    Collects:

    • Personal details
    • Date of birth
    • Phone
    • Address

    The verified email always comes from
    request.session["reg_user"].
    """

    if "reg_user" not in request.session:
        messages.error(
            request,
            "Your registration session has expired. Please start again."
        )
        return redirect("members:register_step_1")

    verified_email = request.session["reg_user"]["email"]

    if request.method == "POST":

        request.session["reg_member"] = {

            "first_name": request.POST["first_name"],

            "middle_name": request.POST.get(
                "middle_name",
                "",
            ),

            "surname": request.POST["surname"],

            # NEW
            "dob": request.POST["dob"],

            # RESTORED
            "phone": request.POST.get(
                "phone",
                "",
            ),
        }

        request.session["reg_address"] = {

            "house_number": request.POST.get(
                "house_number",
                "",
            ),

            "line_1": request.POST.get(
                "line_1",
                "",
            ),

            "line_2": request.POST.get(
                "line_2",
                "",
            ),

            "town": request.POST.get(
                "town",
                "",
            ),

            "county": request.POST.get(
                "county",
                "",
            ),

            "postcode": request.POST.get(
                "postcode",
                "",
            ),

            "country": request.POST.get(
                "country",
                "UK",
            ),
        }

        return redirect("members:register_step_3")

    return render(

        request,

        "members/register/register_step_2_member_profile.html",

        {

            "step_num": 2,

            "verified_email": verified_email,

        },
    )

# ======================================================
# STEP 3 – NEXT OF KIN
# ======================================================
def register_step_3_next_of_kin(request):
    """
    Collects Next of Kin information.

    - Stores Next of Kin information in the registration session.
    - Restores cached information when returning to Step 3.
    - Prevents Next of Kin email from being the same as
      the registering member's email.
    """

    if "reg_member" not in request.session:
        return redirect("members:register_step_2")

    if request.method == "POST":

        # =================================================
        # READ NEXT OF KIN EMAIL
        # =================================================

        nok_email = request.POST.get(
            "email",
            "",
        ).strip().lower()

        # =================================================
        # GET REGISTERING MEMBER EMAIL
        # =================================================

        member_email = request.session.get(
            "reg_user",
            {},
        ).get(
            "email",
            "",
        ).strip().lower()

        # =================================================
        # NEXT OF KIN EMAIL VALIDATION
        # =================================================

        if not nok_email:

            messages.error(
                request,
                "Please enter the Next of Kin email address."
            )

            return redirect(
                "members:register_step_3"
            )

        # =================================================
        # NEXT OF KIN EMAIL MUST DIFFER FROM MEMBER EMAIL
        # =================================================

        if nok_email == member_email:

            messages.error(
                request,
                "The Next of Kin email address must be different from your own email address."
            )

            return redirect(
                "members:register_step_3"
            )

        # =================================================
        # STORE NEXT OF KIN IN SESSION
        # =================================================

        request.session["reg_nok"] = {

            "first_name": request.POST["first_name"],

            "middle_name": request.POST.get(
                "middle_name",
                "",
            ),

            "surname": request.POST["surname"],

            "relationship": request.POST["relationship"],

            "phone": request.POST.get(
                "phone",
                "",
            ),

            "email": nok_email,

        }

        request.session.modified = True

        # =================================================
        # CONTINUE TO STEP 4
        # =================================================

        return redirect(
            "members:register_step_4"
        )

    # =====================================================
    # GET – RESTORE CACHED NEXT OF KIN
    # =====================================================

    nok = request.session.get(
        "reg_nok",
        {},
    )

    return render(
        request,
        "members/register/register_step_3_next_of_kin.html",
        {
            "step_num": 3,
            "nok": nok,
        },
    )

# ======================================================
# STEP 4 – DEPENDANTS
# ======================================================
def register_step_4_dependants(request):
    """
    Collects multiple dependants dynamically.

    - Requires dependant DOB.
    - Validates required dependant information server-side.
    - Stores dependant information in the registration session.
    - Restores cached dependant information when returning to Step 4.
    """

    if "reg_nok" not in request.session:
        return redirect("members:register_step_3")

    if request.method == "POST":

        # =================================================
        # DYNAMIC DEPENDANT PARSING
        # =================================================

        indexes_raw = request.POST.get(
            "dependant_indexes",
            ""
        )

        indexes = [
            index.strip()
            for index in indexes_raw.split(",")
            if index.strip().isdigit()
        ]

        dependants = []

        for index in indexes:

            first = request.POST.get(
                f"dep_{index}_first",
                ""
            ).strip()

            middle = request.POST.get(
                f"dep_{index}_middle",
                ""
            ).strip()

            surname = request.POST.get(
                f"dep_{index}_surname",
                ""
            ).strip()

            relationship = request.POST.get(
                f"dep_{index}_relation",
                ""
            ).strip()

            dob = request.POST.get(
                f"dep_{index}_dob"
            )

            # =================================================
            # REQUIRED FIELD VALIDATION
            # =================================================

            if not first:

                messages.error(
                    request,
                    "Please enter the first name for every dependant."
                )

                return redirect(
                    "members:register_step_4"
                )

            if not surname:

                messages.error(
                    request,
                    "Please enter the surname for every dependant."
                )

                return redirect(
                    "members:register_step_4"
                )

            if not dob:

                messages.error(
                    request,
                    "Please enter the date of birth for every dependant."
                )

                return redirect(
                    "members:register_step_4"
                )

            if not relationship:

                messages.error(
                    request,
                    "Please select the relationship for every dependant."
                )

                return redirect(
                    "members:register_step_4"
                )

            # =================================================
            # STORE VALID DEPENDANT
            # =================================================

            dependants.append({
                "first_name": first,
                "middle_name": middle,
                "surname": surname,
                "relationship": relationship,
                "dob": dob,
            })

        # =================================================
        # CACHE DEPENDANTS IN SESSION
        # =================================================

        request.session["reg_dependants"] = dependants
        request.session.modified = True

        return redirect(
            "members:register_step_5"
        )

    # =====================================================
    # GET – RESTORE CACHED DEPENDANTS
    # =====================================================

    dependants = request.session.get(
        "reg_dependants",
        []
    )

    return render(
        request,
        "members/register/register_step_4_dependants.html",
        {
            "step_num": 4,
            "dependants": dependants,
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


# ======================================================
# STEP 5 – CONFIRM & SAVE
# ======================================================

@transaction.atomic
def register_step_5_confirmation(request):
    """
    Final registration step.
    """

    reg_user = request.session.get("reg_user")
    reg_member = request.session.get("reg_member")
    reg_nok = request.session.get("reg_nok")
    reg_dependants = request.session.get(
        "reg_dependants",
        [],
    )

    if not all([reg_user, reg_member, reg_nok]):
        return redirect("members:register_step_1")

    if request.method == "POST":

            # -------------------------
            # DUPLICATE CHECKS
            # -------------------------

            # Existing Django User
            if User.objects.filter(email__iexact=reg_user["email"]).exists():

                messages.error(
                    request,
                    "An account with this email address already exists. Please log in or use a different email address."
                )

                return redirect("members:register_step_1")


            # Existing Member
            if Member.objects.filter(email__iexact=reg_user["email"]).exists():

                messages.error(
                    request,
                    "This email address is already registered as a member."
                )

                return redirect("members:register_step_1")


            # Existing Username
            if User.objects.filter(username__iexact=reg_user["username"]).exists():

                messages.error(
                    request,
                    "That username is already in use."
                )

                return redirect("members:register_step_1")


            # -------------------------
            # CREATE USER
            # -------------------------

            user = User.objects.create_user(

                username=reg_user["username"],

                email=reg_user["email"],

                password=reg_user["password"],
            )

            # -------------------------
            # ADDRESS
            # -------------------------
            address = create_address_from_session(request)

            # -------------------------
            # MEMBER
            # -------------------------
            member = Member.objects.create(
                user=user,
                address=address,
                email=user.email,
                can_edit=False,
                gdpr_consent=True,
                gdpr_consent_at=timezone.now(),
                gdpr_consent_ip=get_client_ip(request),
                gdpr_version="v1",
                **reg_member,
            )

            # -------------------------
            # NEXT OF KIN
            # -------------------------
            NextOfKin.objects.create(
                member=member,
                **reg_nok,
            )

            # -------------------------
            # DEPENDANTS
            # -------------------------
            dependants = [
                Dependant(member=member, **d)
                for d in reg_dependants
            ]

            Dependant.objects.bulk_create(dependants)

        # -------------------------
        # CLEAR SESSION
        # -------------------------
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
                "Registration completed.",
            )

            return redirect("members:login")

    return render(

        request,

        "members/register/register_step_5_confirmation.html",

        {

            "step_num": 5,

            "member": reg_member,

            "verified_email": reg_user["email"],

            "address": request.session.get(
                "reg_address",
                {},
            ),

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
    return render(
        request,
        "members/register/register_step_1_user.html"
    )

def register_submit(request):
    """
    Legacy handler (can be removed if unused).
    """
    if request.method == "POST":
        return redirect("members:login")

    return redirect("members:register_step_1")
