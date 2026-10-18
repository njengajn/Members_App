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

    # Use the saved historical target population.
    eligible_members = payment_request.targeted_members.all().order_by(
        "first_name", "surname", "id"
    )

    # Completed payments for this request.
    paid_ids = get_paid_member_ids(payment_request)

    # Only members in the historical target population count.
    paid_members = eligible_members.filter(id__in=paid_ids)
    unpaid_members = eligible_members.exclude(id__in=paid_ids)

    total_required = eligible_members.count()
    total_paid = paid_members.count()
    total_unpaid = unpaid_members.count()

    compliance = (
        round((total_paid / total_required) * 100)
        if total_required
        else 0
    )

    # Preserve the existing pending-payment section.
    pending_payments = Payment.objects.filter(
        payment_request=payment_request,
        status=Payment.STATUS_PENDING,
    ).select_related("member").order_by("-created_at")

    return render(
        request,
        "members/admin/admin_payment_request_detail.html",
        {
            "payment_request": payment_request,
            "paid_members": paid_members,
            "unpaid_members": unpaid_members,
            "total_required": total_required,
            "total_paid": total_paid,
            "total_unpaid": total_unpaid,
            "compliance": compliance,
            "pending_payments": pending_payments,
            "pk": payment_request.id,
        },
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


@admin_required
def export_payment_compliance_csv(request, pk):
    """
    Export payment compliance for one payment request.

    HISTORICAL POPULATION RULES
    ---------------------------------------------------------
    - The saved targeted_members snapshot is authoritative.
    - Count only completed payments made by target members.
    - Retain target members who have since retired.
    - If the snapshot is missing, recover only request-specific
      evidence and clearly mark the population unverified.
    - Never substitute today's active members for historical
      targets.

    This function does not modify payments, reconcile the
    request, or trigger member retirement.
    """

    payment_request = get_object_or_404(
        PaymentRequest,
        pk=pk,
    )

    response = HttpResponse(
        content_type="text/csv; charset=utf-8",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="payment_compliance_{payment_request.id}.csv"'
    )

    writer = csv.writer(response)

    # ---------------------------------------------------------
    # REPORT TITLE AND GENERATION TIME
    # ---------------------------------------------------------
    writer.writerow([
        f"Payment Compliance Report: Request {payment_request.id}"
    ])
    writer.writerow([
        "Report Generated",
        timezone.localtime(timezone.now()).strftime(
            "%d/%m/%Y %H:%M:%S"
        ),
    ])
    writer.writerow([])

    # ---------------------------------------------------------
    # DETERMINE THE HISTORICAL TARGET POPULATION
    # ---------------------------------------------------------
    member_ids = set(
        payment_request.targeted_members.values_list(
            "id",
            flat=True,
        )
    )
    target_snapshot_exists = bool(member_ids)

    # Legacy fallback: these records are evidence associated with
    # this request, but cannot prove the original target population.
    if not target_snapshot_exists:
        member_ids.update(
            payment_request.paid_members.values_list(
                "id",
                flat=True,
            )
        )
        member_ids.update(
            payment_request.unpaid_members.values_list(
                "id",
                flat=True,
            )
        )
        member_ids.update(
            payment_request.selected_members.values_list(
                "id",
                flat=True,
            )
        )
        member_ids.update(
            Payment.objects.filter(
                payment_request=payment_request,
                status=Payment.STATUS_COMPLETED,
                member__isnull=False,
            ).values_list(
                "member_id",
                flat=True,
            )
        )

    members = Member.objects.filter(
        id__in=member_ids,
    ).order_by(
        "member_uid",
        "id",
    )

    # ---------------------------------------------------------
    # SUMMARY COUNTS
    # ---------------------------------------------------------
    if target_snapshot_exists:
        target_count = len(member_ids)

        completed_member_ids = set(
            Payment.objects.filter(
                payment_request=payment_request,
                status=Payment.STATUS_COMPLETED,
                member_id__in=member_ids,
            ).values_list(
                "member_id",
                flat=True,
            ).distinct()
        )

        paid_count = len(completed_member_ids)
        unpaid_count = max(
            0,
            target_count - paid_count,
        )

        writer.writerow(["Paid members", paid_count])
        writer.writerow(["Unpaid members", unpaid_count])
        writer.writerow(["Target members", target_count])
    else:
        completed_member_ids = set(
            Payment.objects.filter(
                payment_request=payment_request,
                status=Payment.STATUS_COMPLETED,
                member_id__in=member_ids,
            ).values_list(
                "member_id",
                flat=True,
            ).distinct()
        )

        writer.writerow([
            "Paid members (identified payment evidence)",
            len(completed_member_ids),
        ])
        writer.writerow(["Unpaid members", "UNVERIFIED"])
        writer.writerow(["Target members", "UNVERIFIED"])
        writer.writerow([
            "Population Status",
            "UNVERIFIED - historical target snapshot missing",
        ])

    writer.writerow([])

    # ---------------------------------------------------------
    # EXISTING COLUMN HEADERS
    # ---------------------------------------------------------
    writer.writerow([
        "Member UID",
        "First Name",
        "Surname",
        "Email",
        "Payment Status",
    ])

    # Include a warning in the CSV itself so it remains visible
    # when the report is downloaded or forwarded.
    if not target_snapshot_exists:
        writer.writerow([
            "",
            "",
            "",
            "",
            "UNVERIFIED: historical target snapshot missing; "
            "listed members are request-specific evidence only",
        ])

    # ---------------------------------------------------------
    # EXPORT EACH IDENTIFIED MEMBER
    # ---------------------------------------------------------
    for member in members:
        if member.pk in completed_member_ids:
            payment_status = "PAID"
        else:
            payment_status = "OUTSTANDING"

        # Do not present member status as verified compliance
        # when the historical target snapshot is absent.
        if not target_snapshot_exists:
            payment_status = (
                f"{payment_status} - UNVERIFIED POPULATION"
            )

        writer.writerow([
            member.member_uid or "",
            member.first_name,
            member.surname,
            member.email or "",
            payment_status,
        ])

    return response

