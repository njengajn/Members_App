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

# ======================================================
# REGISTRATION VALIDATION HELPERS
# ======================================================

def _clean(value):
    """
    Safely strip a submitted value.
    """
    return (value or "").strip()


def validate_registration_dependants(
    dependants,
    marital_status,
):
    """
    Validate the complete dependant collection.

    This is the authoritative server-side validation.
    Browser/JavaScript validation is supplementary only.

    Rules
    ------------------------------------------------------
    • Married:
        exactly one spouse.

    • Single / Widowed / Separated:
        no spouse.

    • Maximum one Mother.
    • Maximum one Father.

    • Parent:
        parent type required.
        parent status required.

    • Living parent:
        country, county and sub-county/town required.

    • Deceased parent:
        location is not required.

    • Spouse:
        location required.

    • Sibling:
        location required.

    • Child:
        parent-specific fields are cleared.
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

    for number, dependant in enumerate(
        dependants,
        start=1,
    ):

        relationship = _clean(
            dependant.get("relationship")
        ).upper()

        parent_type = _clean(
            dependant.get("parent_type")
        ).upper()

        parent_status = _clean(
            dependant.get("parent_status")
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

        if relationship not in valid_relationships:

            errors.append(
                f"Dependant {number}: "
                "Please select a valid relationship."
            )

            continue

        # --------------------------------------------------
        # SPOUSE
        # --------------------------------------------------

        if relationship == Dependant.TYPE_SPOUSE:

            spouse_count += 1

            if not country:
                errors.append(
                    f"Dependant {number}: "
                    "Country is required for a spouse."
                )

            if not county:
                errors.append(
                    f"Dependant {number}: "
                    "County is required for a spouse."
                )

            if not sub_county_town:
                errors.append(
                    f"Dependant {number}: "
                    "Sub-county / Town is required for a spouse."
                )

        # --------------------------------------------------
        # SIBLING
        # --------------------------------------------------

        elif relationship == Dependant.TYPE_SIBLING:

            if not country:
                errors.append(
                    f"Dependant {number}: "
                    "Country is required for a sibling."
                )

            if not county:
                errors.append(
                    f"Dependant {number}: "
                    "County is required for a sibling."
                )

            if not sub_county_town:
                errors.append(
                    f"Dependant {number}: "
                    "Sub-county / Town is required for a sibling."
                )

        # --------------------------------------------------
        # PARENT
        # --------------------------------------------------

        elif relationship == Dependant.TYPE_PARENT:

            if parent_type not in {
                Dependant.PARENT_MOTHER,
                Dependant.PARENT_FATHER,
            }:
                errors.append(
                    f"Dependant {number}: "
                    "Please select Mother or Father."
                )

            else:

                if parent_type == Dependant.PARENT_MOTHER:
                    mother_count += 1

                elif parent_type == Dependant.PARENT_FATHER:
                    father_count += 1

            if parent_status not in {
                Dependant.PARENT_ALIVE,
                Dependant.PARENT_DECEASED,
            }:
                errors.append(
                    f"Dependant {number}: "
                    "Please select the parent status."
                )

            elif parent_status == Dependant.PARENT_ALIVE:

                if not country:
                    errors.append(
                        f"Dependant {number}: "
                        "Country is required for a living parent."
                    )

                if not county:
                    errors.append(
                        f"Dependant {number}: "
                        "County is required for a living parent."
                    )

                if not sub_county_town:
                    errors.append(
                        f"Dependant {number}: "
                        "Sub-county / Town is required for a living parent."
                    )

        # --------------------------------------------------
        # CHILD
        # --------------------------------------------------

        elif relationship == Dependant.TYPE_CHILD:

            # Child must not carry parent-only information.
            dependant["parent_type"] = ""
            dependant["parent_status"] = ""

            dependant["country"] = ""
            dependant["county"] = ""
            dependant["sub_county_town"] = ""

    # ======================================================
    # SPOUSE / MARITAL STATUS
    # ======================================================

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
                "A spouse can only be registered when "
                "marital status is Married."
            )

    else:

        errors.append(
            "Please select a valid marital status."
        )

    # ======================================================
    # PARENT LIMITS
    # ======================================================

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
    • Marital status
    • Address

    All submitted data is cached in the registration
    session so Back/Next navigation does not lose data.
    """

    if "reg_user" not in request.session:

        messages.error(
            request,
            "Your registration session has expired. "
            "Please start again."
        )

        return redirect(
            "members:register_step_1"
        )

    verified_email = request.session[
        "reg_user"
    ]["email"]

    if request.method == "POST":

        marital_status = _clean(
            request.POST.get("marital_status")
        ).upper()

        valid_marital_statuses = {
            Member.MARITAL_SINGLE,
            Member.MARITAL_MARRIED,
            Member.MARITAL_WIDOWED,
            Member.MARITAL_SEPARATED,
        }

        # --------------------------------------------------
        # MARITAL STATUS VALIDATION
        # --------------------------------------------------

        if marital_status not in valid_marital_statuses:

            messages.error(
                request,
                "Please select your marital status."
            )

            return render(
                request,
                "members/register/"
                "register_step_2_member_profile.html",
                {
                    "step_num": 2,
                    "verified_email": verified_email,
                    "member": request.POST,
                    "address": request.POST,
                },
            )

        # --------------------------------------------------
        # MEMBER DATA
        # --------------------------------------------------

        request.session["reg_member"] = {

            "first_name": _clean(
                request.POST.get("first_name")
            ),

            "middle_name": _clean(
                request.POST.get("middle_name")
            ),

            "surname": _clean(
                request.POST.get("surname")
            ),

            "dob": request.POST.get("dob"),

            "phone": _clean(
                request.POST.get("phone")
            ),

            "marital_status": marital_status,
        }

        # --------------------------------------------------
        # ADDRESS
        # --------------------------------------------------

        request.session["reg_address"] = {

            "house_number": _clean(
                request.POST.get("house_number")
            ),

            "line_1": _clean(
                request.POST.get("line_1")
            ),

            "line_2": _clean(
                request.POST.get("line_2")
            ),

            "town": _clean(
                request.POST.get("town")
            ),

            "county": _clean(
                request.POST.get("county")
            ),

            "postcode": _clean(
                request.POST.get("postcode")
            ),

            "country": _clean(
                request.POST.get("country")
            ) or "UK",
        }

        request.session.modified = True

        return redirect(
            "members:register_step_3"
        )

    # ------------------------------------------------------
    # GET – RESTORE CACHE
    # ------------------------------------------------------

    return render(
        request,
        "members/register/"
        "register_step_2_member_profile.html",
        {
            "step_num": 2,
            "verified_email": verified_email,
            "member": request.session.get(
                "reg_member",
                {},
            ),
            "address": request.session.get(
                "reg_address",
                {},
            ),
            "marital_status_choices": Member.MARITAL_STATUS_CHOICES,
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
    Collect multiple dependants dynamically.

    Business rules enforced here:

    - Relationship must be CHILD, SPOUSE, SIBLING or PARENT.
    - Spouse is allowed only when member is Married.
    - Maximum one spouse.
    - Maximum two parents in total.
    - Maximum one Mother.
    - Maximum one Father.
    - Parent type is required for a parent.
    - Parent status is required for a parent.
    - Location is required for Spouse and Sibling.
    - Location is required for an Alive Parent.
    - Location is not required for Child.
    - Location is not required for Deceased Parent.

    Browser validation is only a convenience.
    The server-side checks here are authoritative.

    Submitted dependant information is cached before
    validation errors are returned so that the user's
    information is not lost.
    """

    # ======================================================
    # STEP ACCESS
    # ======================================================

    if "reg_nok" not in request.session:

        return redirect(
            "members:register_step_3"
        )


    # ======================================================
    # POST
    # ======================================================

    if request.method == "POST":

        # ==================================================
        # DYNAMIC DEPENDANT PARSING
        # ==================================================

        indexes_raw = request.POST.get(
            "dependant_indexes",
            "",
        )

        indexes = [
            index.strip()
            for index in indexes_raw.split(",")
            if index.strip().isdigit()
        ]

        dependants = []

        validation_errors = []


        # ==================================================
        # PARSE EACH DEPENDANT
        # ==================================================

        for number, index in enumerate(
            indexes,
            start=1,
        ):

            first = _clean(
                request.POST.get(
                    f"dep_{index}_first"
                )
            )

            middle = _clean(
                request.POST.get(
                    f"dep_{index}_middle"
                )
            )

            surname = _clean(
                request.POST.get(
                    f"dep_{index}_surname"
                )
            )

            relationship = _clean(
                request.POST.get(
                    f"dep_{index}_relation"
                )
            ).upper()

            dob = _clean(
                request.POST.get(
                    f"dep_{index}_dob"
                )
            )

            parent_type = _clean(
                request.POST.get(
                    f"dep_{index}_parent_type"
                )
            ).upper()

            parent_status = _clean(
                request.POST.get(
                    f"dep_{index}_parent_status"
                )
            ).upper()

            country = _clean(
                request.POST.get(
                    f"dep_{index}_country"
                )
            )

            county = _clean(
                request.POST.get(
                    f"dep_{index}_county"
                )
            )

            sub_county_town = _clean(
                request.POST.get(
                    f"dep_{index}_sub_county_town"
                )
            )


            # ==================================================
            # BASIC VALIDATION
            # ==================================================

            if not first:

                validation_errors.append(
                    f"Please enter the first name for "
                    f"Dependant {number}."
                )


            if not surname:

                validation_errors.append(
                    f"Please enter the surname for "
                    f"Dependant {number}."
                )


            if not dob:

                validation_errors.append(
                    f"Please enter the date of birth for "
                    f"Dependant {number}."
                )


            if not relationship:

                validation_errors.append(
                    f"Please select the relationship for "
                    f"Dependant {number}."
                )


            # ==================================================
            # VALID RELATIONSHIP
            # ==================================================

            if relationship not in {
                "CHILD",
                "SPOUSE",
                "SIBLING",
                "PARENT",
            }:

                validation_errors.append(
                    f"Invalid relationship selected for "
                    f"Dependant {number}."
                )


            # ==================================================
            # NORMALISE IRRELEVANT FIELDS
            # ==================================================

            if relationship != "PARENT":

                parent_type = ""
                parent_status = ""


            if relationship == "CHILD":

                country = ""
                county = ""
                sub_county_town = ""


            # ==================================================
            # CACHE SUBMITTED DATA
            # ==================================================

            dependants.append({

                "first_name": first,

                "middle_name": middle,

                "surname": surname,

                "relationship": relationship,

                "dob": dob,

                "parent_type": parent_type,

                "parent_status": parent_status,

                "country": country,

                "county": county,

                "sub_county_town": sub_county_town,

            })


        # ==================================================
        # SAVE CACHE BEFORE VALIDATION
        # ==================================================

        request.session["reg_dependants"] = dependants
        request.session.modified = True


        # ==================================================
        # BASIC VALIDATION ERRORS
        # ==================================================

        if validation_errors:

            for error in validation_errors:

                messages.error(
                    request,
                    error,
                )

            return render(
                request,
                "members/register/"
                "register_step_4_dependants.html",
                {
                    "step_num": 4,
                    "dependants": dependants,
                    "marital_status": (
                        request.session
                        .get("reg_member", {})
                        .get("marital_status", "")
                    ),
                },
            )


        # ==================================================
        # MEMBER MARITAL STATUS
        # ==================================================

        reg_member = request.session.get(
            "reg_member",
            {},
        )

        marital_status = (
            reg_member.get(
                "marital_status",
                "",
            )
            or ""
        ).upper()


        # ==================================================
        # RELATIONSHIP LIMIT VALIDATION
        # ==================================================
        #
        # These counts apply to the dependants being registered.
        #
        # CHILD and SIBLING have no numerical limit here.
        #
        # SPOUSE:
        #     Maximum 1
        #
        # PARENT:
        #     Maximum 2 total
        #     Maximum 1 Mother
        #     Maximum 1 Father
        # ==================================================

        spouse_count = sum(
            1
            for dependant in dependants
            if dependant.get("relationship") == "SPOUSE"
        )


        parent_count = sum(
            1
            for dependant in dependants
            if dependant.get("relationship") == "PARENT"
        )


        mother_count = sum(
            1
            for dependant in dependants
            if (
                dependant.get("relationship") == "PARENT"
                and dependant.get("parent_type") == "MOTHER"
            )
        )


        father_count = sum(
            1
            for dependant in dependants
            if (
                dependant.get("relationship") == "PARENT"
                and dependant.get("parent_type") == "FATHER"
            )
        )


        # ==================================================
        # SPOUSE LIMIT
        # ==================================================

        if spouse_count > 1:

            validation_errors.append(
                "Only one spouse can be registered."
            )


        # ==================================================
        # PARENT TOTAL LIMIT
        # ==================================================

        if parent_count > 2:

            validation_errors.append(
                "A maximum of two parents can be registered."
            )


        # ==================================================
        # MOTHER LIMIT
        # ==================================================

        if mother_count > 1:

            validation_errors.append(
                "Only one mother can be registered."
            )


        # ==================================================
        # FATHER LIMIT
        # ==================================================

        if father_count > 1:

            validation_errors.append(
                "Only one father can be registered."
            )


        # ==================================================
        # SPOUSE / MARITAL STATUS
        # ==================================================

        if (
            spouse_count > 0
            and marital_status != "MARRIED"
        ):

            validation_errors.append(
                "A spouse can only be registered when "
                "the member's marital status is Married."
            )


        # ==================================================
        # PARENT FIELD VALIDATION
        # ==================================================

        for number, dependant in enumerate(
            dependants,
            start=1,
        ):

            if dependant.get("relationship") != "PARENT":
                continue


            parent_type = (
                dependant.get("parent_type")
                or ""
            ).upper()


            parent_status = (
                dependant.get("parent_status")
                or ""
            ).upper()


            if parent_type not in {
                "MOTHER",
                "FATHER",
            }:

                validation_errors.append(
                    f"Please select Mother or Father "
                    f"for Parent {number}."
                )


            if parent_status not in {
                "ALIVE",
                "DECEASED",
            }:

                validation_errors.append(
                    f"Please select the status for "
                    f"Parent {number}."
                )


            # --------------------------------------------------
            # Alive parent requires location.
            # --------------------------------------------------

            if parent_status == "ALIVE":

                if not dependant.get("country"):

                    validation_errors.append(
                        f"Please enter the country for "
                        f"Parent {number}."
                    )

                if not dependant.get("county"):

                    validation_errors.append(
                        f"Please enter the county for "
                        f"Parent {number}."
                    )

                if not dependant.get(
                    "sub_county_town"
                ):

                    validation_errors.append(
                        f"Please enter the sub-county / town "
                        f"for Parent {number}."
                    )

            else:

                # Location is not applicable to a
                # deceased parent.

                dependant["country"] = ""
                dependant["county"] = ""
                dependant["sub_county_town"] = ""


        # ==================================================
        # SPOUSE / SIBLING LOCATION
        # ==================================================

        for number, dependant in enumerate(
            dependants,
            start=1,
        ):

            relationship = (
                dependant.get("relationship")
                or ""
            ).upper()


            if relationship not in {
                "SPOUSE",
                "SIBLING",
            }:

                continue


            if not dependant.get("country"):

                validation_errors.append(
                    f"Please enter the country for "
                    f"{relationship.title()} {number}."
                )


            if not dependant.get("county"):

                validation_errors.append(
                    f"Please enter the county for "
                    f"{relationship.title()} {number}."
                )


            if not dependant.get(
                "sub_county_town"
            ):

                validation_errors.append(
                    f"Please enter the sub-county / town for "
                    f"{relationship.title()} {number}."
                )


        # ==================================================
        # FINAL VALIDATION RESULT
        # ==================================================

        if validation_errors:

            for error in validation_errors:

                messages.error(
                    request,
                    error,
                )


            request.session["reg_dependants"] = (
                dependants
            )

            request.session.modified = True


            return render(
                request,
                "members/register/"
                "register_step_4_dependants.html",
                {
                    "step_num": 4,
                    "dependants": dependants,
                    "marital_status": marital_status,
                },
            )


        # ==================================================
        # VALID → STEP 5
        # ==================================================

        return redirect(
            "members:register_step_5"
        )


    # ======================================================
    # GET – RESTORE CACHED DEPENDANTS
    # ======================================================

    dependants = request.session.get(
        "reg_dependants",
        [],
    )


    reg_member = request.session.get(
        "reg_member",
        {},
    )


    marital_status = (
        reg_member.get(
            "marital_status",
            "",
        )
        or ""
    ).upper()


    return render(
        request,
        "members/register/"
        "register_step_4_dependants.html",
        {
            "step_num": 4,
            "dependants": dependants,
            "marital_status": marital_status,
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
    
    # ======================================================
    # FINAL SERVER-SIDE REGISTRATION VALIDATION
    # ======================================================

    marital_status = (
        reg_member or {}
    ).get("marital_status")

    final_errors = validate_registration_dependants(
        dependants=reg_dependants,
        marital_status=marital_status,
    )

    if final_errors:

        for error in final_errors:
            messages.error(
                request,
                error,
            )

        request.session["reg_dependants"] = (
            reg_dependants
        )

        request.session.modified = True

        return redirect(
            "members:register_step_4"
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
            # A deceased parent must always be retired.
            # All other dependants begin as pending.
            dependants = []

            for dependant_data in reg_dependants:

                dependant_data = dict(dependant_data)

                if (
                    dependant_data.get("relationship") == "PARENT"
                    and dependant_data.get("parent_status") == "DECEASED"
                ):
                    dependant_data["status"] = "retired"
                else:
                    dependant_data["status"] = "pending"

                dependants.append(
                    Dependant(
                        member=member,
                        **dependant_data,
                    )
                )

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
