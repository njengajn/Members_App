from django.urls import path

from backend.members.views_ajax.register_ajax import (
    check_email,
    check_id_number,
    register_submit,
)

from backend.members.views_ajax.admin_ajax import (
    admin_search_members,
    admin_update_payment_status,
)

from backend.members.views_ajax.downloads_ajax import download_zip

app_name = "ajax"

urlpatterns = [

    # ========================
    # REGISTRATION
    # ========================
    path("register/check-email/", check_email, name="check_email"),
    path("register/check-id/", check_id_number, name="check_id_number"),
    path("register/submit/", register_submit, name="register_submit"),

    # ========================
    # ADMIN
    # ========================
    path("admin/members/search/", admin_search_members, name="admin_search_members"),
    path(
        "admin/payments/update-status/",
        admin_update_payment_status,
        name="admin_update_payment_status",
    ),

    # ========================
    # DOWNLOADS
    # ========================
    path("download/zip/", download_zip, name="download_zip"),
]
