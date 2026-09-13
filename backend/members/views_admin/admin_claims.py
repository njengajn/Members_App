from django.shortcuts import render, get_object_or_404, redirect
from pathlib import Path

from backend.members.services.document_files import (
    prepare_document_file,
    generate_document_thumbnail,
    DocumentUploadValidationError,
)
from backend.members.forms import ClaimApprovalVerificationForm
from backend.members.services.claim_lifecycle import can_transition
from django.contrib.auth.decorators import login_required
from .admin_auth import admin_required
from django.contrib.admin.views.decorators import staff_member_required
from backend.members.services.business_rules import approve_claim
from backend.members.services.event_engine import trigger_event
from django.utils import timezone
from backend.members.services.payment_service import create_payment_request
from backend.members.utils.payments import validate_due_date
from django.db import transaction
from django.contrib import messages
from django.http import HttpResponseNotAllowed
from backend.members.forms import (ClaimForm, ClaimBankDetailsForm, ClaimSubmissionDeclarationForm,
    ClaimApprovalVerificationForm,)
from backend.members.models import (
    Claim,
    ClaimDecisionHistory,
    Member,
    MemberDocument,
    PaymentRequest,
    Payment,
    ClaimBankDetails,
    ClaimSubmissionDeclaration,
    ClaimApprovalVerification,
)

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
@login_required
def approve_claim(request, claim_uid):
    """
    Approve a claim.

    Before approval, the administrator must:

    1. Complete the verification form.
    2. Explicitly answer all verification questions.
    3. Select at least one confirmation method.
    4. Confirm that all three verification answers
       are "Yes".
    5. Confirm the approval action.

    A claim cannot be approved when any required
    verification answer is "No".
    """

    # ==================================================
    # GET CLAIM
    # ==================================================

    claim = get_object_or_404(

        Claim,

        uid=claim_uid,
    )


    # ==================================================
    # ONLY REVIEWABLE CLAIMS MAY BE APPROVED
    # ==================================================

    if claim.status not in [

        Claim.STATUS_RECEIVED,

        Claim.STATUS_OPEN,

    ]:

        messages.error(

            request,

            (
                "This claim cannot be approved in its "
                "current status."
            ),
        )

        return redirect(

            "claim_detail_admin",

            claim_uid=claim.uid,
        )


    # ==================================================
    # POST ONLY
    # ==================================================

    if request.method != "POST":

        return redirect(

            "claim_detail_admin",

            claim_uid=claim.uid,
        )


    # ==================================================
    # CONFIRMATION PROTECTION
    # ==================================================

    approval_confirmed = request.POST.get(
        "approval_confirmed"
    )


    if approval_confirmed != "yes":

        messages.error(

            request,

            (
                "Please confirm that you want to approve "
                "this claim."
            ),
        )

        return redirect(

            "claim_detail_admin",

            claim_uid=claim.uid,
        )


    # ==================================================
    # VALIDATE VERIFICATION FORM
    # ==================================================

    verification_form = (
        ClaimApprovalVerificationForm(
            request.POST
        )
    )


    if not verification_form.is_valid():

        messages.error(

            request,

            (
                "The claim could not be approved. "
                "Please correct the verification errors."
            ),
        )


        return render(

            request,

            "members/admin/claims/admin_claims_detail.html",

            {
                "claim": claim,

                "verification_form":
                    verification_form,
            },
        )


    # ==================================================
    # GET VERIFICATION ANSWERS
    # ==================================================

    details_match = (

        verification_form.cleaned_data.get(
            "details_match_welfare_record"
        )

    )


    telephone_matches = (

        verification_form.cleaned_data.get(
            "telephone_matches_record"
        )

    )


    information_correct = (

        verification_form.cleaned_data.get(
            "information_correct_declaration"
        )

    )


    # ==================================================
    # ALL THREE ANSWERS MUST BE YES
    #
    # The exact value assumes:
    #
    # ClaimApprovalVerification.VERIFICATION_YES
    #
    # If your implemented constant has a different
    # name, use that existing constant.
    # ==================================================

    verification_yes = (
        ClaimApprovalVerification.VERIFICATION_YES
    )


    if (

        details_match != verification_yes

        or telephone_matches != verification_yes

        or information_correct != verification_yes

    ):

        messages.error(

            request,

            (
                "The claim cannot be approved because "
                "all required verification statements "
                "must be answered Yes."
            ),
        )


        return render(

            request,

            "members/admin/claims/admin_claims_detail.html",

            {
                "claim": claim,

                "verification_form":
                    verification_form,
            },
        )


    # ==================================================
    # SAVE VERIFICATION
    # ==================================================

    verification = (
        verification_form.save(
            commit=False
        )
    )


    verification.claim = claim

    verification.verified_by = request.user

    verification.save()


    # ==================================================
    # TRANSITION TO OPEN FIRST
    #
    # A received claim may need to move through OPEN
    # depending on the existing lifecycle.
    # ==================================================

    if claim.status == Claim.STATUS_RECEIVED:

        claim.transition_to(

            Claim.STATUS_OPEN,

            by_user=request.user,
        )


    # ==================================================
    # APPROVE CLAIM
    # ==================================================

    claim.transition_to(

        Claim.STATUS_APPROVED,

        by_user=request.user,
    )


    # ==================================================
    # CLEAR CURRENT REJECTION REASON
    #
    # A reopened claim may previously have been rejected.
    # The historical rejection remains in decision history.
    # ==================================================

    claim.rejection_reason = ""

    claim.save(
        update_fields=[
            "rejection_reason",
        ]
    )


    # ==================================================
    # CREATE DECISION HISTORY
    # ==================================================

    ClaimDecisionHistory.objects.create(

        claim=claim,

        action=(
            ClaimDecisionHistory.ACTION_APPROVED
        ),

        reason=(

            "Claim approved after verification."
        ),

        performed_by=request.user,
    )


    # ==================================================
    # SUCCESS
    # ==================================================

    messages.success(

        request,

        "The claim has been approved successfully.",
    )


    return redirect(

        "claim_detail_admin",

        claim_uid=claim.uid,
    )

@admin_required
def approve_claimReplaced(request, claim_id):
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
def approve_claim_view(request, claim_id):

    claim = Claim.objects.get(id=claim_id)

    approve_claim(claim)

    return redirect("members_admin:claims")

@login_required
@admin_required
def reject_claim(request, claim_id):
    """
    Reject a received claim.

    IMPORTANT
    ==========================================================
    The existing URL uses:

        claims/<int:claim_id>/reject/

    Therefore this function MUST accept `claim_id`.

    Do not change this function to `claim_uid` unless the URL
    configuration is deliberately changed as well.

    Rejection is not a dead end. The rejected claim can later
    be reopened through the review-rejection workflow.
    """

    # ==========================================================
    # POST ONLY
    # ==========================================================

    if request.method != "POST":

        messages.error(
            request,
            "Claim rejection must use POST.",
        )

        return redirect(
            "members_admin:claim_detail",
            claim_id=claim_id,
        )

    # ==========================================================
    # CLAIM
    # ==========================================================

    claim = get_object_or_404(
        Claim,
        id=claim_id,
    )

    # ==========================================================
    # STATUS CHECK
    # ==========================================================

    if claim.status != Claim.STATUS_RECEIVED:

        messages.warning(
            request,
            "Only received claims can be rejected.",
        )

        return redirect(
            "members_admin:claim_detail",
            claim_id=claim.id,
        )

    # ==========================================================
    # REJECTION REASON
    # ==========================================================

    rejection_reason = (
        request.POST.get(
            "rejection_reason",
            "",
        ).strip()
    )

    if not rejection_reason:

        messages.error(
            request,
            "Please provide a reason for rejecting the claim.",
        )

        return redirect(
            "members_admin:claim_detail",
            claim_id=claim.id,
        )

    # ==========================================================
    # CONFIRMATION
    # ==========================================================

    rejection_confirmed = (
        request.POST.get(
            "rejection_confirmed"
        )
        == "yes"
    )

    if not rejection_confirmed:

        messages.error(
            request,
            (
                "Please confirm the rejection before "
                "continuing."
            ),
        )

        return redirect(
            "members_admin:claim_detail",
            claim_id=claim.id,
        )

    # ==========================================================
    # SAVE CLAIM
    # ==========================================================

    claim.status = Claim.STATUS_REJECTED

    claim.rejection_reason = (
        rejection_reason
    )

    claim.save(
        update_fields=[
            "status",
            "rejection_reason",
            "updated_at",
        ]
    )

    # ==========================================================
    # SUCCESS
    # ==========================================================

    messages.success(
        request,
        (
            "Claim rejected successfully. "
            "The rejection reason has been recorded."
        ),
    )

    return redirect(
        "members_admin:claim_detail",
        claim_id=claim.id,
    )

@login_required
@admin_required
def review_rejection(request, claim_id):
    """
    Reopen a rejected claim for further review.

    This does not delete:

    - the rejection;
    - the rejection reason;
    - previous verification records;
    - decision history.

    The claim returns to OPEN and may subsequently
    be approved or rejected again.
    """

    # ==================================================
    # GET CLAIM
    # ==================================================

    claim = get_object_or_404(

        Claim,

        uid=claim_id,
    )


    # ==================================================
    # ONLY REJECTED CLAIMS MAY BE REOPENED
    # ==================================================

    if claim.status != Claim.STATUS_REJECTED:

        messages.error(

            request,

            (
                "Only a rejected claim can be reopened "
                "for review."
            ),
        )

        return redirect(

            "claim_detail_admin",

            claim_uid=claim.id,
        )


    # ==================================================
    # POST ONLY
    # ==================================================

    if request.method != "POST":

        return redirect(

            "claim_detail_admin",

            claim_uid=claim.uid,
        )


    # ==================================================
    # CONFIRM REVIEW ACTION
    # ==================================================

    review_confirmed = request.POST.get(
        "review_confirmed"
    )


    if review_confirmed != "yes":

        messages.error(

            request,

            (
                "Please confirm that you want to reopen "
                "this claim for review."
            ),
        )

        return redirect(

            "claim_detail_admin",

            claim_uid=claim.uid,
        )


    # ==================================================
    # OPTIONAL REVIEW NOTE
    #
    # This can explain why the rejection is being
    # reviewed, for example:
    #
    # "Applicant provided additional documents."
    # ==================================================

    review_reason = (

        request.POST.get(
            "review_reason",
            ""
        ).strip()

    )


    # ==================================================
    # REQUIRE A REASON FOR REOPENING
    #
    # Recommended for audit purposes.
    # ==================================================

    if not review_reason:

        messages.error(

            request,

            (
                "Please provide a reason for reopening "
                "the rejected claim."
            ),
        )

        return redirect(

            "claim_detail_admin",

            claim_uid=claim.uid,
        )


    # ==================================================
    # REOPEN CLAIM
    # ==================================================

    claim.transition_to(

        Claim.STATUS_OPEN,

        by_user=request.user,
    )


    # ==================================================
    # CREATE DECISION HISTORY
    #
    # Do NOT erase the previous rejection.
    # ==================================================

    ClaimDecisionHistory.objects.create(

        claim=claim,

        action=(
            ClaimDecisionHistory.ACTION_REOPENED
        ),

        reason=review_reason,

        performed_by=request.user,
    )


    # ==================================================
    # SUCCESS
    # ==================================================

    messages.success(

        request,

        (
            "The rejected claim has been reopened for "
            "review."
        ),
    )


    return redirect(

        "claim_detail_admin",

        claim_uid=claim.uid,
    )
 
 # CLAIM DETAIL VIEW

def _get_claim_detail_context(
    claim,
    verification_form=None,
):
    """
    Build the context required by the admin claim detail page.

    Keeping this in one place prevents GET and invalid POST
    requests from drifting apart.
    """

    # ==========================================================
    # BANK DETAILS
    # ==========================================================

    bank_details = (
        ClaimBankDetails.objects
        .filter(claim=claim)
        .first()
    )

    # ==========================================================
    # CLAIM SUBMISSION DECLARATION
    # ==========================================================

    submission_declaration = (
        ClaimSubmissionDeclaration.objects
        .filter(claim=claim)
        .first()
    )

    # ==========================================================
    # APPROVAL VERIFICATION
    # ==========================================================

    approval_verification = (
        ClaimApprovalVerification.objects
        .filter(claim=claim)
        .first()
    )

    # ==========================================================
    # SUPPORTING DOCUMENTS
    # ==========================================================

    documents = (
        MemberDocument.objects
        .filter(
            claim=claim,
            is_archived=False,
        )
        .order_by(
            "-uploaded_at"
        )
    )

    # ==========================================================
    # PAYMENT REQUEST
    # ==========================================================

    payment_request = (
        PaymentRequest.objects
        .filter(claim=claim)
        .first()
    )

    paid_members = []
    unpaid_members = []
    total = 0
    paid_count = 0
    total_paid_amount = 0

    # ==========================================================
    # PAYMENT INFORMATION
    # ==========================================================

    if payment_request:

        if payment_request.viewable_by_all:

            members = (
                Member.objects
                .filter(
                    status="active"
                )
            )

        else:

            members = (
                payment_request
                .selected_members
                .all()
            )

        paid_members = (
            payment_request
            .paid_members
            .all()
        )

        unpaid_members = (
            members.exclude(
                id__in=paid_members.values_list(
                    "id",
                    flat=True,
                )
            )
        )

        total = members.count()

        paid_count = (
            paid_members.count()
        )

        total_paid_amount = (
            payment_request.total_paid
        )

    # ==========================================================
    # DEFAULT VERIFICATION FORM
    # ==========================================================

    if (
        verification_form is None
        and claim.status == Claim.STATUS_RECEIVED
        and not approval_verification
    ):

        verification_form = (
            ClaimApprovalVerificationForm()
        )

    return {

        "claim": claim,

        "bank_details": bank_details,

        "submission_declaration": (
            submission_declaration
        ),

        "approval_verification": (
            approval_verification
        ),

        "documents": documents,

        "verification_form": (
            verification_form
        ),

        "payment_request": (
            payment_request
        ),

        "paid_members": (
            paid_members
        ),

        "unpaid_members": (
            unpaid_members
        ),

        "total": total,

        "paid_count": paid_count,

        "total_paid_amount": (
            total_paid_amount
        ),
    }

def claim_detail_admin(request, claim_id):
    """
    Display complete claim details.

    Includes:

    - Claim information
    - Claim bank details
    - Claimant declaration
    - Supporting documents
    - Approval verification
    - Payment request information
    - Paid and unpaid member information

    This view does not approve or reject the claim.
    """

    # ==========================================================
    # CLAIM
    # ==========================================================

    claim = get_object_or_404(
        Claim,
        id=claim_id,
    )

    # ==========================================================
    # BANK DETAILS
    # ==========================================================

    bank_details = (
        ClaimBankDetails.objects
        .filter(
            claim=claim
        )
        .first()
    )

    # ==========================================================
    # CLAIM SUBMISSION DECLARATION
    # ==========================================================

    submission_declaration = (
        ClaimSubmissionDeclaration.objects
        .filter(
            claim=claim
        )
        .first()
    )

    # ==========================================================
    # APPROVAL VERIFICATION
    # ==========================================================

    approval_verification = (
        ClaimApprovalVerification.objects
        .filter(
            claim=claim
        )
        .first()
    )

    # ==========================================================
    # SUPPORTING DOCUMENTS
    # ==========================================================
    #
    # IMPORTANT:
    # This is a queryset, not a single document. Every
    # MemberDocument linked to this claim is returned.
    #
    # Do not use .first() or [:1] here: claims can have
    # multiple supporting documents.
    #

    documents = (
        MemberDocument.objects
        .filter(
            claim=claim
        )
        .order_by(
            "uploaded_at"
        )
    )

    # ==========================================================
    # PAYMENT REQUEST
    # ==========================================================

    payment_request = (
        PaymentRequest.objects
        .filter(
            claim=claim
        )
        .first()
    )

    # ==========================================================
    # DEFAULT PAYMENT VALUES
    # ==========================================================

    paid_members = []

    unpaid_members = []

    total = 0

    paid_count = 0

    total_paid_amount = 0

    # ==========================================================
    # PAYMENT INFORMATION
    # ==========================================================

    if payment_request:

        # ------------------------------------------------------
        # MEMBERS INCLUDED IN PAYMENT REQUEST
        # ------------------------------------------------------

        if payment_request.viewable_by_all:

            members = (
                Member.objects
                .filter(
                    status="active"
                )
            )

        else:

            members = (
                payment_request
                .selected_members
                .all()
            )

        # ------------------------------------------------------
        # PAID MEMBERS
        # ------------------------------------------------------

        paid_members = (
            payment_request
            .paid_members
            .all()
        )

        # ------------------------------------------------------
        # UNPAID MEMBERS
        # ------------------------------------------------------

        unpaid_members = (
            members.exclude(
                id__in=paid_members.values_list(
                    "id",
                    flat=True,
                )
            )
        )

        # ------------------------------------------------------
        # PAYMENT TOTALS
        # ------------------------------------------------------

        total = members.count()

        paid_count = (
            paid_members.count()
        )

        total_paid_amount = (
            payment_request.total_paid
        )

    # ==========================================================
    # APPROVAL VERIFICATION FORM
    # ==========================================================

    verification_form = None

    if (
        claim.status
        == Claim.STATUS_RECEIVED
        and not approval_verification
    ):

        verification_form = (
            ClaimApprovalVerificationForm()
        )

    # ==========================================================
    # RENDER
    # ==========================================================

    return render(
        request,
        (
            "members/admin/claims/"
            "admin_claims_detail.html"
        ),
        {
            "claim": claim,

            "bank_details": (
                bank_details
            ),

            "submission_declaration": (
                submission_declaration
            ),

            "documents": documents,

            "approval_verification": (
                approval_verification
            ),

            "verification_form": (
                verification_form
            ),

            "payment_request": (
                payment_request
            ),

            "paid_members": (
                paid_members
            ),

            "unpaid_members": (
                unpaid_members
            ),

            "total": total,

            "paid_count": (
                paid_count
            ),

            "total_paid_amount": (
                total_paid_amount
            ),
        },
    )
