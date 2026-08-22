from django.http import HttpResponse
from django.urls import path
# HOME
from backend.members.views_frontend import payments as payment_views
from backend.members.views_frontend.dashboard import member_dashboard
from backend.members.views_frontend.documents import document_requests
from backend.members.views_frontend.home import home
from backend.members.views_frontend.privacy_policy import privacy_policy
# AUTH
from backend.members.views_frontend.auth import login_view, logout_view, password_reset_request, password_reset_verify

# DASHBOARD
#from backend.members.views_frontend.dashboard import dependants_view, member_dashboard

# CLAIMS
from backend.members.views_frontend.claims import (
    member_claims_list,
    member_create_claim,
    members_claim_detail,
    create_claim_entry,
    )

# DEPENDANTS 
from backend.members.views_frontend.dependants import (
    members_dependants_list,
    members_add_dependant,
    members_edit_dependant,
    members_delete_dependant,
    members_dependant_detail,
)

# PAYMENTS
from backend.members.views_frontend.payments import (
    confirm_manual_payment,
    create_stripe_checkout,
    manual_payment_page,
    member_payment_requests,
    #members_payments_list,
    #members_payment_detail,
    pay_payment_request,
    payment_receipt,
    stripe_payment_success,
)

# USER AND REGISTER
from backend.members.views_frontend.profile import profile_view
from backend.members.views_frontend.register_flow import (
    register_step_1_user,
    register_step_2_member_profile,
    register_step_3_next_of_kin,
    register_step_4_dependants,
    register_step_5_confirmation,
    register_verify_email
)
from backend.members.views_admin.payments import payment_webhook
from backend.members.views_frontend.api import postcode_lookup
from backend.members.views_frontend.address_api import address_autocomplete
from backend.members.views_frontend.ajax import register_ajax
from backend.members.views_frontend.documents import(
    member_requests,
    upload_document,
    resubmit_document,
    view_document_file,
    view_document_thumbnail,
    view_document_preview,
)


app_name = "members"

urlpatterns = [

    # HOME
    path("", home, name="home"),

    # AUTH
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),

    # DASHBOARD
    path("dashboard/", member_dashboard, name="dashboard"),

    # DEPENDANTS 
    path("dependants/", members_dependants_list, name="dependants"),
    path("dependants/add/", members_add_dependant, name="add_dependant"),

    # CLAIMS    
    path("claims/create/", create_claim_entry, name="create_claim_entry"),

    # 🔥 MEMBER ONLY (FINAL DESTINATION)
    path("claims/create/member/", member_create_claim, name="member_create_claim"),

    path("claims/create/", member_create_claim, name="create_claim"),
    path("claims/<int:pk>/", members_claim_detail, name="member_claims"),
    
    path("claims/", member_claims_list, name="member_claims_list"),
    path("claims/create/", member_create_claim, name="member_create_claim"),
    path("claims/create/", member_create_claim, name="members_create_claim"),
    path("claims/", member_claims_list, name="member_claims"),
    path("profile/", profile_view, name="profile"),


    # PAYMENTS
    path("payments/", payment_views.member_payment_requests, name="member_payments",),
    path("payments/<int:pk>/pay/", pay_payment_request, name="pay"),
    path("payments/receipt/<uuid:uid>/", payment_receipt, name="receipt"),
    path("payments/requests/", member_payment_requests, name="member_payment_requests"),
    path("payments/<int:pk>/pay/", pay_payment_request, name="pay_payment_request"), 
    path("payments/<int:pk>/confirm/", confirm_manual_payment, name="confirm_manual_payment"),
    path("payments/<int:pk>/manual/", manual_payment_page, name="manual_payment_page"),
    path("payments/<int:pk>/manual/", manual_payment_page, name="manual_payment",),
    path("payments/<int:pk>/stripe/", create_stripe_checkout, name="create_stripe_checkout",),
    path("payments/stripe-success/<int:pk>/",stripe_payment_success,name="stripe_success",),
    path("webhook/", payment_webhook, name="payment_webhook"),
    path("payments/<int:pk>/success/", stripe_payment_success, name="stripe_payment_success"),
    path("payments/<int:pk>/pay/", pay_payment_request, name="pay_payment"),


    # REGISTER
    path("register/step-1/", register_step_1_user, name="register_step_1"),
    path("register/step-2/", register_step_2_member_profile, name="register_step_2"),
    path("register/step-3/", register_step_3_next_of_kin, name="register_step_3"),
    path("register/step-4/", register_step_4_dependants, name="register_step_4"),
    path("register/step-5/", register_step_5_confirmation, name="register_step_5"),
    #path("register/verify-email/", register_verify_email, name="register_verify_email"),
    path("members/register/verify-email/", register_verify_email, name="register_verify_email"),
    
    #path("members/ajax/register/", views.register_step_1_user, name="ajax_register"),
    
    path("members/ajax/register/", register_ajax, name="ajax_register"),
    path("dependants/", members_dependants_list, name="dependants"),
    path("dependants/add/", members_add_dependant, name="add_dependant"),
    path("dependants/<int:pk>/edit/", members_edit_dependant, name="edit_dependant"),
    path("dependants/<int:pk>/delete/", members_delete_dependant, name="delete_dependant"),
    path("dependants/<int:pk>/", members_dependant_detail, name="dependant_detail"),
    
    path("password-reset/", password_reset_request, name="password_reset"),
    path("password-reset/verify/", password_reset_verify, name="password_reset_verify"),
    
    #api

    path("api/postcode-lookup/", postcode_lookup, name="postcode_lookup"),
    path("api/address-autocomplete/", address_autocomplete, name="address_autocomplete"),
    
    path(".well-known/appspecific/com.chrome.devtools.json", lambda request: HttpResponse("{}", content_type="application/json")),
    
    
    #path("documents/requests/", document_requests, name="document_requests"),
    
    path("documents/requests/", member_requests, name="member_requests"),
    #path("documents/requests/", upload_document, name="upload_document"),
    path("documents/upload/", upload_document, name="upload_document"),
    path("documents/<int:document_id>/resubmit/", resubmit_document, name="resubmit_document",),
    path("privacy-policy/",  privacy_policy, name="privacy_policy",),
    path(
        "documents/<int:file_id>/thumbnail/",
        view_document_thumbnail,
        name="view_document_thumbnail",
    ),
    # =========================================================
    # SECURE MEMBER DOCUMENT VIEW
    # =========================================================

    path("documents/<int:file_id>/view/", view_document_file, name="view_document_file",),
    path(
        "documents/<int:file_id>/preview/",
        view_document_preview,
        name="view_document_preview",
    ),
    
]