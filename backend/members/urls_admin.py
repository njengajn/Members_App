from django.urls import path
from django.contrib.auth.views import LogoutView

# AUTH
from backend.members.views_admin import admin_claims_list, admin_member_search
from backend.members.views_admin import admin_payment_request_detail
from backend.members.views_admin import admin_payments
from backend.members.views_admin import admin_members
from backend.members.views_admin.admin_auth import login_view

# DASHBOARD
from backend.members.views_admin.admin_dashboard import admin_dashboard

# MEMBERS
from backend.members.views_admin.admin_documents import admin_documents_list, approve_document, document_dashboard, reject_document, request_document
from backend.members.views_admin.admin_members import (
    admin_update_member_permissions,
    dependant_detail,
    export_members_excel,
    export_members_pdf,
    members_list,
    member_detail,
    membership_history,
    update_member_status,
    bulk_update_dependants,
)

from backend.members.views_admin.admin_members import (
    update_dependant_inline,
    edit_next_of_kin,
    approve_member,
)

from backend.members.views_admin.admin_members import (
    admin_members_list,
    admin_member_detail,
    update_member_status,
    update_dependant_status,
)

# CLAIMS
from backend.members.views_admin.admin_claims import approve_claim, claim_detail_admin, claim_lifecycle_view, claims_list_admin, reject_claim
from backend.members.views_admin.admin_claims import (
    approve_claim_view,
)

# PAYMENTS
from backend.members.views_admin.admin_payments import (
    admin_mark_payment_paid,
    admin_payments_list,
    admin_pending_payments,
    approve_payment,
    confirm_claim_payment,
    confirm_manual_payment,
    create_payment_request,
    export_payment_members,
    payment_compliance_tracker,
    payment_request_paid_members,
    payments_awaiting_confirmation,
    reject_payment,
    settle_claim_payment,
    update_payment_request,
    update_payment_request_status,
)
from backend.members.views_admin.admin_analytics import admin_analytics_dashboard
from backend.members.views_admin.admin_tools import bulk_member_activation
from backend.members.views_admin.admin_finance import finance_summary, finance_summary_pdf, finance_summary_excel
from backend.members.views_admin.admin_payment_request_detail import admin_view_payment_request
from backend.members.views_admin.admin_finance import treasurer_control_panel
from backend.members.views_admin.admin_finance import treasurer_analytics_dashboard

from backend.members.views_admin.admin_payment_request_detail import (
    admin_view_payment_request,
    export_payment_compliance_csv,
    admin_payment_request_detail
)
from backend.members.views_admin.admin_treasurer_dashboard import treasurer_dashboard
from backend.members.views_admin.admin_financial_risk import financial_risk_monitor
from backend.members.views_admin.claims import admin_create_claim, search_members
from backend.members.views_admin.payments import payment_webhook, archive_payment_request

from backend.members.views_admin.admin_members import (
    admin_members_dashboard,
    approve_member,
    reject_member,
    toggle_member_edit,
    member_card_view,
)
from backend.members.views_admin.admin_documents import (
    document_dashboard,
    approve_document,
    reject_document,
    archive_document,
    delete_document,
    upload_requested_document_admin,
    reject_document_form,
    admin_document_preview,
)
from backend.members.views_admin import admin_dashboard, payment_filters
from backend.members.views_admin.admin_member_search import admin_member_search
from backend.members.views_admin.admin_claims import create_payment_request_from_claim
from backend.members.views_frontend.claims import member_create_claim
from backend.members.views_admin.admin_audit import admin_audit_logs, export_audit_logs
from backend.members.views_admin.admin_security import admin_security_dashboard
from backend.members.views_admin.member_actions import restore_member, restore_member_view, retire_member_view
from backend.members.views_admin import claim_settlement
from django.urls import path


from backend.members.views_admin.admin_treasurer_dashboard import (
    treasurer_dashboard,
    treasurer_dashboard_pdf,
    treasurer_dashboard_excel,
)

# =========================================================
# ADMIN DOCUMENT VIEWS
# =========================================================

from backend.members.views_admin.admin_documents import(
    document_dashboard,
    admin_document_review,
    request_document,
    )
app_name = "members_admin"

urlpatterns = [

    # ======================
    # AUTH
    # ======================
    path("login/", login_view, name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),

    # ======================
    # DASHBOARD
    # ======================
    path("", admin_dashboard, name="dashboard"),
    
    
    path("dashboard/", admin_dashboard, name="admin_dashboard"),

    path(
        "payments/filter/<str:status>/",
        payment_filters.filtered_payment_requests,
        name="filtered_payment_requests"
    ),

    # ======================
    # MEMBERS
    # ======================

    path("members/", admin_members_list, name="admin_members_list"),
    path("members/<int:member_id>/", admin_member_detail, name="admin_member_detail",),
    path("members/<int:member_id>/update-status/", update_member_status, name="update_member_status",),
    path("members/<int:member_id>/approve/", approve_member, name="approve_member",),
    path("members/<int:member_id>/edit-nok/", edit_next_of_kin, name="edit_next_of_kin",),
    path("dependants/<int:dependant_id>/update/", update_dependant_inline, name="update_dependant_inline",),
    #path("dependants/<int:dependant_id>/update/", admin_members.update_dependant_inline, name="update_dependant_inline",),
    path("members/<int:member_id>/dependants/bulk-update/", bulk_update_dependants, name="bulk_update_dependants",),

    path(
        "members/<int:member_id>/update-permissions/",
        admin_update_member_permissions,
        name="update_member_permissions",
    ),
    path(
    "dependants/<int:pk>/",
    dependant_detail,
    name="dependant_detail",
    ),
    path("members/<int:member_id>/restore/", restore_member_view, name="restore_member"),
    path("members/<int:member_id>/retire/", retire_member_view, name="retire_member"),
    

    # ======================
    # CLAIMS
    # ======================
    path("claims/", claims_list_admin, name="claims"),
    #path("claims/<uuid:claim_uid>/approve/", approve_claim_view, name="approve_claim", ),
    path("claims/", claims_list_admin, name="admin_claims_list"),
    path("claims/<int:claim_id>/approve/", approve_claim, name="approve_claim"),
    
    
    path("claims/", claims_list_admin, name="admin_claims_list"),
    path("claims/<int:claim_id>/", claim_detail_admin, name="claim_detail"),
    path("claims/<int:claim_id>/approve/", approve_claim, name="approve_claim"),
    path("claims/<int:claim_id>/reject/", reject_claim, name="reject_claim"),
    #path("claims/create-admin/", create_payment_request_from_claim, name="admin_create_claim"),
    path("claims/create/", member_create_claim, name="member_create_claim"),
    path("claims/settle/<int:request_id>/", claim_settlement.start_claim_settlement, name="start_claim_settlement",),
    
    # ======================
    # CLAIM SETTLEMENT
    # ======================

    path("claims/settlement/<int:settlement_id>/", claim_settlement.claim_settlement_detail, name="claim_settlement_detail",),

    path("claims/settlement/<int:settlement_id>/export/", claim_settlement.export_claim_ledger, name="export_claim_ledger",),
    
    path("claims/reconcile/<int:request_id>/", claim_settlement.reconcile_claim, name="reconcile_claim",),
    path("claims/confirm/<int:settlement_id>/", claim_settlement.confirm_claim_settlement, name="confirm_claim_settlement",),
    path("claims/approve/<int:settlement_id>/", claim_settlement.approve_claim_settlement, name="approve_claim_settlement",),
    path("claims/settlement/<int:settlement_id>/pdf/", claim_settlement.export_claim_pdf, name="export_claim_pdf"),
    path("claims/settled/", claim_settlement.settled_claims, name="settled_claims"),
    
    # ======================
    # PAYMENTS
    # ======================
    path("payments/", admin_payments_list, name="payments"),
    path("payments/create/", create_payment_request, name="create_payment_request", ),
    path("payments/<int:pk>/", admin_view_payment_request, name="payment_detail", ),
    path("payments/create/", create_payment_request, name="create_payment_request"),
    path("payments/", admin_payments_list, name="admin_payments_list"),
    
    path("analytics/", admin_analytics_dashboard, name="admin_analytics_dashboard",),
    path("tools/bulk-activation/", bulk_member_activation, name="bulk_member_activation",),
    path("finance/", finance_summary, name="finance_summary",),
    
    path("claims/<int:claim_id>/lifecycle/", claim_lifecycle_view, name="claim_lifecycle",),
    
    path("payments/<int:request_id>/paid-members/", payment_request_paid_members, name="payment_request_paid_members",),

    path("payments/<int:request_id>/update-status/", update_payment_request_status, name="update_payment_request_status",),
    path("payments/<int:pk>/compliance/", payment_compliance_tracker, name="payment_compliance_tracker",),
    path("payments/<int:pk>/", admin_view_payment_request, name="payment_detail",),
    
    path("payments/pending/", payments_awaiting_confirmation, name="payments_awaiting_confirmation"),

    path("admin/payments/pending/", admin_pending_payments, name="pending_payments"),
    

    path("payments/<int:pk>/confirm/", confirm_manual_payment, name="confirm_manual_payment"),
    path("admin-panel/payments/<int:pk>/approve/", approve_payment, name="approve_payment"),
    path("admin-panel/payments/<int:pk>/reject/", reject_payment, name="reject_payment"),    
    path("payments/", admin_payments_list, name="admin_payments_list"),
    path("payments/<int:pk>/", admin_payment_request_detail, name="payment_request_detail"),
    path("payments/<int:pk>/edit/", update_payment_request, name="update_payment_request",),
    path("payments/<int:pk>/mark-paid/<int:member_id>/", admin_mark_payment_paid, name="admin_mark_payment_paid",),     
    path("payments/<int:pk>/approve/", admin_payments.approve_payment, name="admin_approve_payment", ),
    path("payments/<int:pk>/", admin_payment_request_detail, name="admin_payment_detail"),
     
     
     # Existing admin routes...

    # Stripe webhook (ADMIN SIDE)
    path("payments/webhook/", payment_webhook, name="payment_webhook"),
    
    # ======================
    # treasurer_control_panel
    # ======================
    
    path("finance/treasurer/", treasurer_control_panel, name="treasurer_control_panel",),
    path("finance/analytics/", treasurer_analytics_dashboard, name="treasurer_analytics_dashboard", ),
    path("claims/<int:claim_id>/settle/", settle_claim_payment, name="settle_claim_payment",),
    path("payments/<int:request_id>/confirm/", confirm_claim_payment, name="confirm_claim_payment",),
    path("payments/<int:pk>/export/", export_payment_members, name="export_payment_members"),



    path("payments/<int:pk>/", admin_view_payment_request, name="payment_detail",),
    path("payments/<int:pk>/export/", export_payment_compliance_csv, name="export_payment_compliance_csv",),
    path("treasurer/", treasurer_dashboard, name="treasurer_dashboard"),
    path("treasurer/risk-monitor/", financial_risk_monitor,name="financial_risk_monitor"),
    
    path("admin-panel/finance-summary/pdf/", finance_summary_pdf, name="finance_summary_pdf",),
    path("admin-panel/finance-summary/excel/", finance_summary_excel, name="finance_summary_excel",),

    
    # ===============================
    #DOCUMENTS
    # ===========================
    path("admin/documents/", document_dashboard, name="admin_documents"),
    path("admin/documents/<int:pk>/approve/", approve_document, name="approve_document"),
    path("admin/documents/<int:document_id>/reject/", reject_document_form, name="reject_document_form",),
    
    #======================
    # MEMBER EDIT AND UPDATE
    #
    path("admin/members/", admin_members_dashboard, name="admin_members"),
    path("admin/members/<int:pk>/approve/", approve_member, name="approve_member"),
    path("admin/members/<int:pk>/reject/", reject_member, name="reject_member"),
    path("admin/members/<int:pk>/toggle-edit/", toggle_member_edit, name="toggle_member_edit"),
    path("admin/members/<int:pk>/card/", member_card_view, name="member_card"),
    

    # MEMBERS DASHBOARD
    path("members/", admin_members_dashboard, name="admin_members"),

    path("members/<int:pk>/approve/", approve_member, name="approve_member"),
    path("members/<int:pk>/reject/", reject_member, name="reject_member"),
    path("members/<int:pk>/toggle-edit/", toggle_member_edit, name="toggle_member_edit"),
    path("members/<int:pk>/card/", member_card_view, name="member_card"),

    # DOCUMENTS DASHBOARD
    path("documents/", document_dashboard, name="admin_documents"),
    path("documents/<int:pk>/approve/", approve_document, name="approve_document"),
    path("documents/<int:pk>/reject/", reject_document, name="reject_document"),
    
    path("admin/documents/", document_dashboard, name="admin_documents"),

    path("admin/documents/member/<int:member_id>/", admin_documents_list, name="admin_documents_list"),

    path("admin/documents/request/<int:member_id>/", request_document, name="request_document"),
    
    #search
    path("claims/search-members/", search_members, name="search_members"),
    path("ajax/member-search/", admin_member_search, name="admin_member_search"),


    # ADMIN CLAIM CREATE
    path("claims/create-admin/", admin_create_claim, name="admin_create_claim"),
    
    #-------------------------
    # AUDIT LOGS
    #------------------
    path("audit/", admin_audit_logs, name="admin_audit_logs"),
    path("audit/export/", export_audit_logs, name="export_audit_logs"),
    
       #SECURITY DASHBOARD

    path("security/", admin_security_dashboard, name="security_dashboard"),
    
    path("payments/<int:pk>/close/", admin_payments.close_payment_request, name="close_payment_request"),
    
    path("payments/<int:pk>/report/pdf/", admin_payments.export_payment_request_pdf, name="export_payment_request_pdf"),
    
    # =====================================================
    # DOCUMENT DASHBOARD
    # =====================================================

    path("admin/documents/", document_dashboard, name="admin_documents",),

    # =====================================================
    # MEMBER DOCUMENTS PAGE
    # =====================================================

    path("admin/documents/member/<int:member_id>/", admin_documents_list, name="admin_documents_list",),

    # =====================================================
    # DOCUMENT REVIEW
    # =====================================================
    #
    # Handles:
    # - approve
    # - reject
    #
    # Used by:
    #
    # admin_documents_list.html
    #
    # =====================================================

    path("admin/documents/review/<int:document_id>/<str:action>/", admin_document_review, name="admin_document_review",
    ),

    # =====================================================
    # REQUEST DOCUMENT
    # =====================================================

    path("admin/documents/request/<int:member_id>/",request_document,name="request_document",),
    
    
    #=============================
    # ADMIN DOCUMENTS
    #=============================
    # =====================================================
    # DOCUMENT DASHBOARD
    # =====================================================

    path("admin/documents/", document_dashboard, name="admin_documents",),

    # =====================================================
    # MEMBER DOCUMENTS PAGE
    # =====================================================

    path("admin/documents/member/<int:member_id>/", admin_documents_list, name="admin_documents_list",),

    # =====================================================
    # DOCUMENT REVIEW
    # =====================================================
    #
    # Handles:
    # - approve
    # - reject
    #
    # Used by:
    #
    # admin_documents_list.html
    #
    # =====================================================

    path("admin/documents/review/<int:document_id>/<str:action>/", admin_document_review, name="admin_document_review",),

    # =====================================================
    # REQUEST DOCUMENT
    # =====================================================

    path("admin/documents/request/<int:member_id>/", request_document, name="request_document",),
    
    path("documents/<int:document_id>/archive/", archive_document,name="archive_document",),
    path("documents/<int:document_id>/delete/", delete_document, name="delete_document",),
    
    path("documents/request/<int:request_id>/upload/", upload_requested_document_admin, name="upload_requested_document_admin",),
    

    path("treasurer-dashboard/pdf/", treasurer_dashboard_pdf, name="treasurer_dashboard_pdf",),

    path("treasurer-dashboard/excel/", treasurer_dashboard_excel,name="treasurer_dashboard_excel",),
    
    # =========================================================
    # SECURE DOCUMENT PREVIEW
    # =========================================================

    path("documents/<int:document_id>/preview/", admin_document_preview,
        name="admin_document_preview",),

    # =====================================================
    # PAYMENT REQUEST ARCHIVE
    # =====================================================

    path("payments/request/<int:pk>/archive/", archive_payment_request,name="archive_payment_request",),

    path("members/export/pdf/", export_members_pdf, name="export_members_pdf"),

    path("members/export/excel/", export_members_excel, name="export_members_excel"),
    
    
    #=====================
    # MEMBER RETIREMENT HISTORY
    #=============================
    path("admin/members/history/", membership_history, name="membership_history",),
    
]