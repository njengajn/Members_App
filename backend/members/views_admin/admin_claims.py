from pyexpat.errors import messages

from django.shortcuts import render, get_object_or_404, redirect

from backend.members.services.claim_lifecycle import can_transition
from .admin_auth import admin_required
from backend.members.models import Claim, Member, PaymentRequest, Payment
from django.contrib.admin.views.decorators import staff_member_required
from backend.members.services.business_rules import approve_claim
from backend.members.services.event_engine import trigger_event
from django.utils import timezone
from backend.members.services.payment_service import create_payment_request
from backend.members.utils.payments import validate_due_date


@admin_required
def claim_list(request):
    claims = Claim.objects.all()
    return render(request, "members/admin/claims.html", {"claims": claims})


@admin_required
def settle_claim_view(request, pk):
    claim = get_object_or_404(Claim, pk=pk)
    claim.status = "settled"
    claim.save()
    return redirect("members:claim_list")


@admin_required
def claims_list_admin(request):
    """
    Admin claims list
    """

    status_filter = request.GET.get("status")

    claims = Claim.objects.select_related(
        "member",
        "causer_dependant"
    ).order_by("-created_at")

    if status_filter:
        claims = claims.filter(status=status_filter)

    return render(
        request,
        "members/admin/claims/admin_claims_list.html",
        {
            "claims": claims
        },
    )


@admin_required
def approve_claim(request, claim_id):
    """
    Approve claim and trigger lifecycle event.

    Business rules preserved:
    - Only 'received' claims can be approved
    """

    claim = get_object_or_404(Claim, id=claim_id)

    # FIX STATUS (pending → received)
    if claim.status != "received":
        messages.warning(request, "Only received claims can be approved.")
        return redirect("members_admin:admin_claims_list")

    try:
        # Step 1: update status
        claim.status = "approved"
        claim.save()

        # Step 2: trigger event (NEW — replaces manual logic)
        trigger_event("claim_approved", claim=claim)

        messages.success(request, "Claim approved successfully.")

    except Exception as e:
        messages.error(request, str(e))

    return redirect("members_admin:admin_claims_list")


@staff_member_required
def create_payment_request_from_claim(request):
    """
    CREATE PAYMENT REQUEST FROM CLAIM

    ✅ FIXED:
    - Uses central service (no direct DB writes)
    - Enforces payment_method
    - Enforces due_date validation
    """

    claim_id = request.GET.get("claim")
    claim = None

    if claim_id:
        claim = get_object_or_404(
            Claim,
            id=claim_id,
            status=Claim.STATUS_APPROVED,
        )

    if request.method == "POST":

        try:
            # =========================
            # INPUTS
            # =========================
            request_type = request.POST.get("request_type")
            amount = request.POST.get("amount")
            due_date_input = request.POST.get("due_date")

            # 🔴 CRITICAL FIX
            payment_method = request.POST.get("payment_method")

            if not payment_method:
                raise ValueError("Payment method is required.")

            if payment_method not in ["manual", "card", "both"]:
                raise ValueError("Invalid payment method.")

            # =========================
            # VALIDATE DUE DATE
            # =========================
            due_date = validate_due_date(due_date_input)

            member = None
            claim_obj = None

            # =========================
            # CLAIM FLOW
            # =========================
            if request_type == "Claim":

                claim_id = request.POST.get("claim_id")
                claim_obj = get_object_or_404(Claim, id=claim_id)

                member = claim_obj.member

                claim_obj.status = Claim.STATUS_OPEN
                claim_obj.save()

            # =========================
            # ✅ USE SERVICE (CRITICAL FIX)
            # =========================
            create_payment_request(
                member=member,
                claim=claim_obj,
                amount=amount,
                description=request_type,
                due_date=due_date,
                request_type=request_type,
                payment_method=payment_method,
            )

            messages.success(request, "Payment request created successfully.")
            return redirect("members_admin:admin_payments_list")

        except Exception as e:
            messages.error(request, str(e))

    return render(
        request,
        "members/admin/payments/admin_create_payments_request.html",
        {
            "claim": claim,
            "today": timezone.now(),  # for date restriction
        },
    )
    
def payment_completed(payment):
    payment.status = "completed"
    payment.save()

    if payment.payment_request.claim:
        claim = payment.payment_request.claim
        claim.status = Claim.STATUS_SETTLED
        claim.save()
        
@admin_required
def claim_lifecycle_view(request, claim_id):
    """
    Displays lifecycle tracker for a claim.
    """

    claim = get_object_or_404(Claim, id=claim_id)

    payment_request = PaymentRequest.objects.filter(claim=claim).first()

    payment = None
    if payment_request:
        payment = Payment.objects.filter(
            payment_request=payment_request
        ).first()

    lifecycle = {
        "submitted": True,
        "approved": claim.status in ["approved", "open", "settled"],
        "payment_requested": payment_request is not None,
        "payment_completed": payment is not None,
        "settled": claim.status == "settled",
    }

    context = {
        "claim": claim,
        "payment_request": payment_request,
        "payment": payment,
        "lifecycle": lifecycle,
    }

    return render(
        request,
        "members/admin/claims/admin_claim_lifecycle.html",
        context,
    )
    
@admin_required
def claims_list_admin(request):
    """
    Admin list of claims

    FIXES:
    ✔ Matches template variable name (claims)
    ✔ Supports dashboard filtering
    ✔ Fixes empty table issue
    ✔ Uses correct statuses
    """

    status_filter = request.GET.get("status")

    claims = Claim.objects.select_related(
        "member",
        "causer_dependant"
    ).order_by("-created_at")

    # APPLY FILTER ONLY IF PRESENT
    if status_filter:
        claims = claims.filter(status=status_filter)

    context = {
        "claims": claims,  # call claims
    }

    return render(
        request,
        "members/admin/claims/admin_claims_list.html",
        context,
    )
    

@admin_required
def approve_claim(request, claim_id):

    claim = Claim.objects.get(id=claim_id)

    if not can_transition(claim.status, "approved"):
        messages.error(request, "Invalid claim lifecycle change.")
        return redirect("members_admin:claims")

    claim.status = "approved"
    claim.save()

    messages.success(request, "Claim approved.")

    return redirect("members_admin:claims")


@admin_required
def approve_claim_view(request, claim_id):

    claim = Claim.objects.get(id=claim_id)

    approve_claim(claim)

    return redirect("members_admin:claims")



@admin_required
def reject_claim(request, claim_id):
    """
    Reject claim
    """

    from django.contrib import messages
    from django.shortcuts import redirect, get_object_or_404

    claim = get_object_or_404(Claim, id=claim_id)

    if claim.status != "received":
        messages.warning(request, "Only received claims can be rejected.")
        return redirect("members_admin:admin_claims_list")

    claim.status = "rejected"
    claim.save()

    messages.success(request, "Claim rejected.")

    return redirect("members_admin:admin_claims_list")
 
 
 # CLAIM DETAIL VIEW

@admin_required
def claim_detail_admin(request, claim_id):
    """
    Claim detail with analytics
    """
    claim = get_object_or_404(Claim, id=claim_id)

    payment_request = getattr(claim, "payment_request", None)

    paid_members = []
    unpaid_members = []
    total = 0
    paid_count = 0
    total_paid_amount = 0

    if payment_request:

        if payment_request.viewable_by_all:
            members = Member.objects.filter(status="active")
        else:
            members = payment_request.selected_members.all()

        paid_members = payment_request.paid_members.all()
        unpaid_members = members.exclude(id__in=paid_members.values_list("id", flat=True))

        total = members.count()
        paid_count = paid_members.count()

        total_paid_amount = payment_request.total_paid

    return render(
        request,
        "members/admin/claims/admin_claims_detail.html",
        {
            "claim": claim,
            "payment_request": payment_request,
            "paid_members": paid_members,
            "unpaid_members": unpaid_members,
            "total": total,
            "paid_count": paid_count,
            "total_paid_amount": total_paid_amount,
        },
    )






    



    
