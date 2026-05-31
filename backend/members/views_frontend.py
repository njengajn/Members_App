from django.shortcuts import redirect, render
from django.urls import path
from .views_frontend import (
    home,
    auth,
    dashboard,
    dependants,
    payments,
    documents,
    register_flow,
)
from backend.members import views_frontend

# DEPENDANTS
from backend.members.views_frontend.dependants import (
    members_dependants_list,)

app_name = "members"

urlpatterns = [
    # Public
    path("", home.frontend_home, name="home"),

    # Auth
    path("login/", auth.login_view, name="login"),
    path("logout/", auth.logout_view, name="logout"),

    # Member dashboard
    path("dashboard/", dashboard.member_dashboard, name="member_dashboard"),

    # Dependants
    path("dependants/", dependants.dependants_list, name="dependants"),
    #("dependants/", dependants.list_dependants, name="dependants"),
    #path("dependants/", dependants.dependants_view, name="dependants"),

    path("dependants/add/", dependants.add_dependant, name="add_dependant"),

    # Payments
    path("payments/", payments.payment_requests_list, name="payment_requests"),
    path("payments/<int:request_id>/", payments.payment_request_detail, name="payment_request_detail"),
    path("payments/<uuid:payment_uid>/receipt/", views_frontend.payments.payment_receipt, name="payment_receipt",),

    # Documents
    path("documents/", documents.documents_list, name="documents"),
    path("documents/requests/", documents.member_requests, name="member_requests"),

    # Registration flow
    path("register/", register_flow.register_start, name="register"),
    path("register/submit/", register_flow.register_submit,
         name="register_submit"),
]

def home(request):
    #if request.user.is_authenticated:
        #return redirect("members:dashboard")
    return render(request, "frontend/home.html")







