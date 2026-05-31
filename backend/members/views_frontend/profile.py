from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
import base64
from django.core.files.base import ContentFile
from PIL import Image
from io import BytesIO


@login_required
def profile_view(request):

    member = request.user.member

    if request.method == "POST":

        # =========================
        # BASIC FIELDS
        # =========================
        member.first_name = request.POST.get("first_name")
        member.surname = request.POST.get("surname")
        member.phone = request.POST.get("phone")

        # =========================
        # CROPPED IMAGE HANDLING
        # =========================
        cropped = request.POST.get("cropped_avatar")

        if cropped:
            try:
                format, imgstr = cropped.split(';base64,')
                image = Image.open(BytesIO(base64.b64decode(imgstr)))

                # 🔥 ENSURE RGB
                image = image.convert("RGB")

                # 🔥 COMPRESS
                buffer = BytesIO()
                image.save(buffer, format="JPEG", quality=75)

                # 🔥 SAVE
                member.avatar.save(
                    f"avatar_{member.id}.jpg",
                    ContentFile(buffer.getvalue()),
                    save=False
                )

            except Exception as e:
                messages.error(request, f"Image processing failed: {str(e)}")

        # =========================
        # SAVE MEMBER
        # =========================
        member.save()

        messages.success(request, "Profile updated.")
        return redirect("members:profile")

    return render(request, "members/profile/profile.html", {
        "member": member
    })