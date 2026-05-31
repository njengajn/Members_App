from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test, login_required
from functools import wraps

User = get_user_model()


# ======================================================
# HELPERS
# ======================================================
def is_admin(user):
    return user.is_staff or user.is_superuser


# ======================================================
# ADMIN LOGIN
# ======================================================
def login_view(request):
    """
    Admin login with:
    - inactive account detection
    - proper error messaging
    """

    if request.user.is_authenticated and is_admin(request.user):
        return redirect("members_admin:dashboard")

    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        # -----------------------------------------
        # CHECK USER EXISTS FIRST
        # -----------------------------------------
        try:
            user_obj = User.objects.get(username=email)
        except User.DoesNotExist:
            user_obj = None

        # -----------------------------------------
        # INACTIVE ACCOUNT CHECK
        # -----------------------------------------
        if user_obj and not user_obj.is_active:
            messages.error(request, "Your account is not active. Contact the administrator.")
            return render(request, "members/admin/admin_login.html")

        # -----------------------------------------
        # AUTHENTICATE
        # -----------------------------------------
        user = authenticate(request, username=email, password=password)

        if user and is_admin(user):
            login(request, user)
            return redirect("members_admin:dashboard")

        messages.error(request, "Invalid admin credentials.")

    return render(request, "members/admin/admin_login.html")


# ======================================================
# ADMIN LOGOUT
# ======================================================
@user_passes_test(is_admin, login_url="/admin/login/")
def logout_view(request):
    logout(request)
    return redirect("members_admin:login")


# ======================================================
# ADMIN REQUIRED DECORATOR
# ======================================================
def admin_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            messages.error(request, "Admin access required.")
            return redirect("members:home")
        return view_func(request, *args, **kwargs)
    return wrapper


# ======================================================
# REMOVE DUPLICATE / UNUSED VIEWS
# (kept for compatibility but aligned)
# ======================================================
def admin_login(request):
    return login_view(request)


def admin_logout(request):
    return logout_view(request)