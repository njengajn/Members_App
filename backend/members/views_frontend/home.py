from django.shortcuts import redirect, render

def home(request):
    #if request.user.is_authenticated:
       # return redirect("members:dashboard")
    return render(request, "frontend/frontend_home.html")


def register_start(request):
    """
    Entry point for registration.
    """
    return render(request, "members/register/register_step_1_user.html")


def register_submit(request):
    """
    Handles registration submission.
    """
    if request.method == "POST":
        # handle form saving logic here
        return redirect("members:login")

    return redirect("members:register")


