# backend/members/views_admin/admin_dashboard.py
from django.shortcuts import render
from django.contrib.auth.decorators import user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from backend.members.models import Member, Claim, Payment,  PaymentRequest, Claim


def is_admin(user):
    return user.is_authenticated and user.is_staff

@user_passes_test(is_admin, login_url="/admin/login/")
@staff_member_required

def dashboard_home(request):

    # ==========================
    # MEMBERS TOTALS
    # ==========================
    
    members_count = Member.objects.filter(status="active").count()
    

    # ==========================
    # CLAIM TOTALS
    # ==========================

    open_claims = Claim.objects.filter(status="open").count()
    approved_claims = Claim.objects.filter(status="approved").count()
    rejected_claims = Claim.objects.filter(status="rejected").count()
    settled_claims = Claim.objects.filter(status="settled").count()

    total_claims = Claim.objects.count()

    # ==========================
    # PAYMENT REQUEST TOTALS
    # ==========================

    payment_requests_count = PaymentRequest.objects.count()

    # ==========================
    # COMPLETED PAYMENTS
    # ==========================

    completed_payments_count = (
        Payment.objects.filter(status="completed").count()
    )

    # ==========================
    # ALL PAYMENTS
    # ==========================

    total_payments = Payment.objects.count()

    context = {
        "open_claims": open_claims,
        "approved_claims": approved_claims,
        "rejected_claims": rejected_claims,
        "settled_claims": settled_claims,
        "total_claims": total_claims,
        "payment_requests_count": payment_requests_count,
        "completed_payments_count": completed_payments_count,
        "total_payments": total_payments,
    }

    return render(
        request,
        "members/admin/dashboard.html",
        context,
    )

    



