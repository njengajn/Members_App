#backend/members/views_ajax/register_ajax.py
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth import get_user_model
from backend.members.models import Member

User = get_user_model()


@require_POST
def check_email(request):
    """
    AJAX endpoint → Check if email already exists.
    """
    email = request.POST.get("email", "").strip().lower()

    if not email:
        return JsonResponse({"status": "error", "message": "Email is required."}, status=400)

    exists = User.objects.filter(email=email).exists()

    return JsonResponse({
        "status": "ok",
        "exists": exists,
        "message": "Email already registered." if exists else "Email available."
    })


@require_POST
def check_id_number(request):
    """
    AJAX endpoint → Check if a member ID number already exists.
    """
    id_number = request.POST.get("id_number", "").strip()

    if not id_number:
        return JsonResponse({"status": "error", "message": "ID number is required."}, status=400)

    exists = Member.objects.filter(id_number=id_number).exists()

    return JsonResponse({
        "status": "ok",
        "exists": exists,
        "message": "ID number already exists." if exists else "ID number available."
    })


@require_POST
def register_submit(request):
    """
    Step 1 AJAX submission → Save user info in session → Return next step URL.
    """
    username = request.POST.get("username", "").strip()
    email = request.POST.get("email", "").strip().lower()
    password = request.POST.get("password", "")
    confirm = request.POST.get("confirm_password", "")

    if not all([username, email, password, confirm]):
        return JsonResponse({"success": False, "message": "All fields are required."}, status=400)

    if password != confirm:
        return JsonResponse({"success": False, "message": "Passwords do not match."}, status=400)

    if User.objects.filter(username=username).exists():
        return JsonResponse({"success": False, "message": "Username already exists."}, status=400)

    if User.objects.filter(email=email).exists():
        return JsonResponse({"success": False, "message": "Email already registered."}, status=400)

    # Save to session
    request.session["reg_user"] = {
        "username": username,
        "email": email,
        "password": password,
    }

    return JsonResponse({
        "success": True,
        "next_url": "/register/step-2/"
    })
    
@require_POST
def register_step_2_submit(request):
    """
    AJAX submission → Save member info in session → Return next step URL (Step 3: NOK)
    """
    if "reg_user" not in request.session:
        return JsonResponse({"success": False, "message": "Start registration first."}, status=400)

    id_number = request.POST.get("id_number", "").strip()
    gender = request.POST.get("gender", "").strip()
    dob = request.POST.get("dob", "").strip()

    if not id_number:
        return JsonResponse({"success": False, "message": "ID number is required."}, status=400)

    if Member.objects.filter(id_number=id_number).exists():
        return JsonResponse({"success": False, "message": "ID number already exists."}, status=400)

    request.session["reg_member"] = {
        "id_number": id_number,
        "gender": gender,
        "dob": dob,
    }

    return JsonResponse({"success": True, "next_url": "/register/step-3/"})


@require_POST
def register_step_3_submit(request):
    """
    AJAX submission → Save NOK info in session → Return next step URL (Step 4: Dependants)
    """
    if "reg_member" not in request.session:
        return JsonResponse({"success": False, "message": "Complete previous step first."}, status=400)

    nok_data = {
        "first_name": request.POST.get("first_name", "").strip(),
        "middle_name": request.POST.get("middle_name", "").strip(),
        "surname": request.POST.get("surname", "").strip(),
        "relationship": request.POST.get("relationship", "").strip(),
        "phone": request.POST.get("phone", "").strip(),
        "email": request.POST.get("email", "").strip(),
    }

    if not nok_data["first_name"] or not nok_data["surname"]:
        return JsonResponse({"success": False, "message": "NOK first and last name are required."}, status=400)

    request.session["reg_nok"] = nok_data

    return JsonResponse({"success": True, "next_url": "/register/step-4/"})


@require_POST
def register_step_4_submit(request):
    """
    AJAX submission → Save dependants in session → Return next step URL (Step 5: Confirm)
    """
    if "reg_member" not in request.session:
        return JsonResponse({"success": False, "message": "Complete previous step first."}, status=400)

    dependants = []
    i = 1
    while True:
        first = request.POST.get(f"dep_{i}_first", "").strip()
        if not first:
            break

        dependants.append({
            "first_name": first,
            "middle_name": request.POST.get(f"dep_{i}_middle", "").strip(),
            "surname": request.POST.get(f"dep_{i}_surname", "").strip(),
            "dob": request.POST.get(f"dep_{i}_dob", "").strip(),
            "relationship": request.POST.get(f"dep_{i}_relation", "").strip(),
        })
        i += 1

    request.session["reg_dependants"] = dependants

    return JsonResponse({"success": True, "next_url": "/register/step-5/"})



