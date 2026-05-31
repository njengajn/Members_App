from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, render
from django.contrib.admin.views.decorators import staff_member_required
from backend.members.utils.payments import ( get_paid_member_ids, get_eligible_members,)  
from django.utils import timezone
from backend.members.models import ( PaymentRequest, Payment,Member,)
from backend.members.views_admin.admin_auth import admin_required
from django.http import HttpResponse
from django.db.models import Q
import csv
from backend.members.models import (
    PaymentRequest,
    Payment,
    Member
)


@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_payment_request_detail(request, pk):
    payment_request = get_object_or_404(PaymentRequest, pk=pk)

    paid_ids = get_paid_member_ids(payment_request)

    eligible_members = get_eligible_members(payment_request)
    paid_members = eligible_members.filter(id__in=paid_ids)
    unpaid_members = eligible_members.exclude(id__in=paid_ids)

    return render(
        request,
        "members/admin/admin_payment_request_detail.html",
        {
            "payment_request": payment_request,
            "paid_members": paid_members,
            "unpaid_members": unpaid_members,
            "pk": payment_request.id
        }
    )

# ==========================================================
# ADMIN – VIEW SINGLE PAYMENT REQUEST
# ==========================================================

def is_admin(user):
    return user.is_authenticated and user.is_staff


@user_passes_test(is_admin)
def admin_view_payment_request(request, pk):
    """
    Admin payment request detail page.

    Displays:
    - Paid members
    - Outstanding members
    - Compliance %
    - Progress bar
    """

    payment_request = get_object_or_404(PaymentRequest, pk=pk)

    # Determine required members
    if payment_request.member:
        required_members = Member.objects.filter(id=payment_request.member.id)
    else:
        required_members = Member.objects.filter(status="active")

    # Payments recorded for this request
    payments = Payment.objects.filter(payment_request=payment_request)

    paid_members = Member.objects.filter(
        payments__payment_request=payment_request,
        payments__status="completed"
    ).distinct()

    unpaid_members = required_members.exclude(id__in=paid_members)

    total_required = required_members.count()
    total_paid = paid_members.count()

    compliance = 0
    if total_required > 0:
        compliance = round((total_paid / total_required) * 100)

    context = {
        "payment_request": payment_request,
        "paid_members": paid_members,
        "unpaid_members": unpaid_members,
        "total_required": total_required,
        "total_paid": total_paid,
        "compliance": compliance,
    }

    return render(
        request,
        "members/admin/payments/admin_payment_request_detail.html",
        context,
    )


@user_passes_test(is_admin)
def export_payment_compliance_csv(request, pk):
    """
    Export payment compliance report for treasurer.
    """

    payment_request = get_object_or_404(PaymentRequest, pk=pk)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="payment_request_{pk}_compliance.csv"'
    )

    writer = csv.writer(response)

    writer.writerow([
        "Member UID",
        "First Name",
        "Surname",
        "Email",
        "Payment Status",
    ])

    members = Member.objects.filter(status="active")

    for m in members:

        paid = Payment.objects.filter(
            member=m,
            payment_request=payment_request,
            status="completed"
        ).exists()

        status = "PAID" if paid else "OUTSTANDING"

        writer.writerow([
            m.member_uid,
            m.first_name,
            m.surname,
            m.email,
            status
        ])
        
    return response

