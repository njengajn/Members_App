from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse


# ==========================================================
# ADMIN REQUIRED
# ==========================================================
def admin_required(view_func):
    return user_passes_test(
        lambda u: u.is_authenticated and u.is_staff
    )(view_func)


# ==========================================================
# SAFE REDIRECT
# ==========================================================
def safe_redirect(view_name, fallback="/"):
    """
    Prevents NoReverseMatch crashes.
    """

    try:
        return redirect(reverse(view_name))
    except NoReverseMatch:
        return redirect(fallback)


# ==========================================================
# MEMBER REQUIRED
# ==========================================================
def member_required(view_func):
    """
    Ensures user has a Member profile.

    Behaviour:
    ----------
    - Members:
        Allowed normally.

    - Superusers/staff without member profile:
        Redirect to custom admin dashboard.

    - Non-member normal users:
        Redirect safely with warning.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):

        user = request.user

        # ==================================================
        # NOT AUTHENTICATED
        # ==================================================
        if not user.is_authenticated:
            return safe_redirect("login", "/login/")

        # ==================================================
        # ADMIN / SUPERUSER WITHOUT MEMBER PROFILE
        # ==================================================
        if user.is_superuser or user.is_staff:

            if not hasattr(user, "member"):

                messages.info(
                    request,
                    "Admin dashboard."
                )

                # IMPORTANT:
                # Replace "admin_dashboard"
                # with your REAL admin dashboard URL name
                return safe_redirect(
                    "admin_dashboard",
                    "/admin-panel/"
                )

        # ==================================================
        # NORMAL NON-MEMBER USERS
        # ==================================================
        if not hasattr(user, "member"):

            messages.warning(
                request,
                "You do not have a member account."
            )

            # Prevent crash if front_home missing
            try:
                return redirect(reverse("members:front_home"))
            except NoReverseMatch:

                try:
                    return redirect(reverse("home"))
                except NoReverseMatch:
                    return redirect("/")

        # ==================================================
        # ALLOW ACCESS
        # ==================================================
        return view_func(request, *args, **kwargs)

    return wrapper