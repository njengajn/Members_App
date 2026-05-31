from django.utils import timezone
import random

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from backend.core import settings
from backend.members.models import Dependant
from django.contrib.auth.decorators import login_required
import zipfile, os
from django.http import HttpResponse
from django.contrib.auth import get_user_model
from django.conf import settings
import random

from backend.members.models import EmailOTP

User = get_user_model()


@require_POST
def register_ajax(request):

    """
    AJAX registration step.

    - validates user
    - generates OTP
    - sends branded verification email
    - stores registration data in session
    """

    username = request.POST.get("username")

    email = request.POST.get("email")

    password = request.POST.get("password")

    confirm = request.POST.get(
        "confirm_password"
    )

    # =====================================================
    # VALIDATION
    # =====================================================

    if (
        not username or
        not email or
        not password
    ):

        return JsonResponse({

            "status": "error",

            "message": (
                "All fields required"
            )

        })

    if password != confirm:

        return JsonResponse({

            "status": "error",

            "message": (
                "Passwords do not match"
            )

        })

    if User.objects.filter(
        username=username
    ).exists():

        return JsonResponse({

            "status": "error",

            "message": (
                "Username already exists"
            )

        })

    if User.objects.filter(
        email=email
    ).exists():

        return JsonResponse({

            "status": "error",

            "message": (
                "Email already exists"
            )

        })

    # =====================================================
    # RATE LIMIT OTP REQUESTS
    # =====================================================

    window = (
        timezone.now() -
        timezone.timedelta(minutes=5)
    )

    recent_otps = EmailOTP.objects.filter(
        email=email,
        created_at__gte=window
    ).count()

    if recent_otps >= 3:

        return JsonResponse({

            "status": "error",

            "message": (
                "Too many verification attempts. "
                "Try again later."
            )

        })

    # =====================================================
    # OTP GENERATION
    # =====================================================

    otp = str(
        random.randint(100000, 999999)
    )

    otp_obj = EmailOTP(

        email=email,

        purpose=EmailOTP.PURPOSE_REGISTRATION,

    )

    # HASH OTP

    otp_obj.set_otp(otp)

    otp_obj.save()

    # =====================================================
    # SEND BRANDED EMAIL
    # =====================================================

    from backend.members.services.notifications import (
        send_html_email
    )

    send_html_email(

        recipient=email,

        subject="Verify Your Email",

        template=(
            "members/emails/"
            "registration_otp.html"
        ),

        context={

            "email_title": (
                "Email Verification"
            ),

            "first_name": username,

            "otp": otp,

            "current_year": (
                timezone.now().year
            ),

            "plain_message": (
                f"Your verification "
                f"code is: {otp}"
            ),
        },
    )

    # =====================================================
    # OPTIONAL WHATSAPP OTP
    # FUTURE:
    # phone number can be added to form
    # =====================================================

    # Example:
    #
    # send_whatsapp_otp(phone, otp)

    # =====================================================
    # STORE SESSION
    # =====================================================

    request.session["reg_user"] = {

        "username": username,

        "email": email,

        "password": password,
    }

    # =====================================================
    # RESPONSE
    # =====================================================

    return JsonResponse({

        "status": "ok"

    })


@login_required
@require_POST
def ajax_add_dependant(request):
    name = request.POST.get("name")
    relationship = request.POST.get("relationship")

    d = Dependant.objects.create(
        user=request.user,
        name=name,
        relationship=relationship
    )

    return JsonResponse({
        "status": "ok",
        "id": d.id,
        "name": d.name,
        "relationship": d.relationship
    })


@login_required
@require_POST
def ajax_remove_dependant(request):
    dep_id = request.POST.get("id")
    Dependant.objects.filter(id=dep_id, user=request.user).delete()
    return JsonResponse({"status": "ok"})


@login_required
def download_zip(request):
    zip_path = "/tmp/user_bundle.zip"

    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("info.txt", f"User Export: {request.user.email}")

    with open(zip_path, "rb") as f:
        data = f.read()

    response = HttpResponse(data, content_type="application/zip")
    response["Content-Disposition"] = "attachment; filename=user_bundle.zip"

    return response
