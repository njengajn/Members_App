# backend/members/views_admin/claim_settlement.py
from django.shortcuts import redirect, render, get_object_or_404
from django.http import HttpResponse
import csv
from backend.members.services.settlement_reporting import (
    get_contribution_breakdown,
    get_reconciliation_summary,
    generate_ledger_rows,
)
from django.contrib import messages
from backend.members.views_admin.admin_auth import admin_required
from django.utils import timezone
from django.forms import modelformset_factory
from backend.members.models import (
    AuditLog,
    Claim,
    ClaimSettlement,
    ClaimSettlementDeduction,
    Member,
    PaymentRequest,
)
from backend.members.forms import ClaimSettlementDeductionForm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
)
from reportlab.lib import colors
from django.forms import inlineformset_factory
from backend.members.services.payment_lifecycle import (process_payment_lifecycle)
from django.contrib.auth import get_user_model
User = get_user_model()


def claim_settlement_detail(request, settlement_id):
    settlement = get_object_or_404(ClaimSettlement, id=settlement_id)

    breakdown = get_contribution_breakdown(settlement.claim)
    reconciliation = get_reconciliation_summary(settlement.claim)

    return render(request, "members/admin/claims/claim_settlement_detail.html", {
        "settlement": settlement,
        "breakdown": breakdown,
        "reconciliation": reconciliation,
    })


def export_claim_ledger(request, settlement_id):
    settlement = get_object_or_404(ClaimSettlement, id=settlement_id)

    rows = generate_ledger_rows(settlement.claim)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="claim_ledger_{settlement.id}.csv"'

    writer = csv.writer(response)

    writer.writerow([
        "Date",
        "Member UID",
        "Member Name",
        "Amount",
        "Payment Method",
        "Reference",
    ])

    for row in rows:
        writer.writerow(row)

    return response


@admin_required
def start_claim_settlement(request, request_id):
    """
    Trigger settlement AFTER payment request is closed
    """

    payment_request = get_object_or_404(PaymentRequest, id=request_id)

    # -----------------------------------
    # RULE: must be claim type
    # -----------------------------------
    if payment_request.request_type != "claim":
        messages.error(request, "Not a claim-based request.")
        return redirect("members_admin:admin_payments_list")

    # -----------------------------------
    # RULE: must be closed
    # -----------------------------------
    if payment_request.status != PaymentRequest.STATUS_CLOSED:
        messages.warning(request, "Cannot settle until request is closed.")
        return redirect("members_admin:admin_payment_detail", payment_request.id)

    claim = payment_request.claim

    if not claim:
        messages.error(request, "No claim linked.")
        return redirect("members_admin:admin_payments_list")

    # -----------------------------------
    # PREVENT DUPLICATE SETTLEMENT
    # -----------------------------------
    if hasattr(claim, "settlement") and claim.settlement:
        return redirect("members_admin:claim_settlement_detail", claim.settlement.id)

    # -----------------------------------
    # CREATE SETTLEMENT
    # -----------------------------------
    settlement = ClaimSettlement.objects.create(
        claim=claim,
        settlement_date=timezone.now()
    )

    # -----------------------------------
    # UPDATE CLAIM (NO DATE STORED HERE)
    # -----------------------------------
    claim.status = "settled"
    claim.settled = True
    claim.save(update_fields=["status", "settled"])

    messages.success(request, "Claim settled successfully.")

    return redirect("members_admin:claim_settlement_detail", settlement.id)


# =========================================================
# RECONCILIATION
# =========================================================

@admin_required
def reconcile_claim(request, request_id):
    """
    UNIVERSAL RECONCILIATION

    CLAIM FLOW
    ------------------------------------------------
    deductions
    -> approval
    -> finalised

    NON-CLAIM FLOW
    ------------------------------------------------
    reconciliation report
    -> confirm
    -> finalised
    """

    payment_request = get_object_or_404(
        PaymentRequest,
        id=request_id
    )

    # =====================================================
    # MUST BE CLOSED FIRST
    # =====================================================

    if payment_request.status != PaymentRequest.STATUS_CLOSED:

        messages.warning(
            request,
            "Close request before reconciliation."
        )

        return redirect(
            "members_admin:admin_payment_detail",
            payment_request.id
        )

    claim = getattr(payment_request, "claim", None)

    # =====================================================
    # CLAIM FLOW
    # =====================================================

    if claim:

        settlement, _ = ClaimSettlement.objects.get_or_create(
            claim=claim,
            defaults={
                "settlement_date": timezone.now()
            }
        )

        # -------------------------------------------------
        # ALREADY APPROVED
        # -------------------------------------------------

        if settlement.is_approved:

            messages.info(
                request,
                "This settlement has already been finalised."
            )

            return redirect(
                "members_admin:claim_settlement_detail",
                settlement.id
            )

        DeductionFormSet = modelformset_factory(
            ClaimSettlementDeduction,
            form=ClaimSettlementDeductionForm,
            extra=1,
            can_delete=True
        )

        # =================================================
        # POST
        # =================================================

        if request.method == "POST":

            formset = DeductionFormSet(
                request.POST,
                queryset=settlement.deduction_items.all()
            )

            notes = request.POST.get(
                "notes",
                ""
            )

            if formset.is_valid():

                instances = formset.save(commit=False)

                for obj in instances:

                    obj.settlement = settlement
                    obj.save()

                for obj in formset.deleted_objects:
                    obj.delete()

                settlement.notes = notes

                settlement.prepared_by = request.user

                settlement.is_approved = False

                settlement.save()

                messages.success(
                    request,
                    "Reconciliation submitted for approval."
                )

                return redirect(
                    "members_admin:claim_settlement_detail",
                    settlement.id
                )

            messages.error(
                request,
                "Please correct errors before submitting."
            )

        else:

            formset = DeductionFormSet(
                queryset=settlement.deduction_items.all()
            )

        return render(
            request,
            "members/admin/claims/reconcile_claim.html",
            {
                "settlement": settlement,
                "payment_request": payment_request,
                "formset": formset,
                "empty_form": formset.empty_form,
            }
        )

    # =====================================================
    # NON-CLAIM FLOW
    # =====================================================

    else:

        # -------------------------------------------------
        # TARGET MEMBERS
        # -------------------------------------------------

        if (
            payment_request.viewable_by_all
            and payment_request.member
            and payment_request.member.organization
        ):

            all_members = Member.objects.filter(
                organization=payment_request.member.organization,
                status=Member.STATUS_ACTIVE
            )

        elif payment_request.selected_members.exists():

            all_members = payment_request.selected_members.all()

        elif payment_request.member:

            all_members = Member.objects.filter(
                id=payment_request.member.id
            )

        else:

            all_members = Member.objects.none()

        # -------------------------------------------------
        # STATS
        # -------------------------------------------------

        total_required = payment_request.amount

        total_collected = payment_request.total_paid or 0

        paid_count = payment_request.paid_members.count()

        unpaid_count = max(
            0,
            all_members.count() - paid_count
        )

        compliance = 0

        if all_members.exists():

            compliance = int(
                (paid_count / all_members.count()) * 100
            )

        # =================================================
        # CONFIRM SIMPLE RECONCILIATION
        # =================================================

        if request.method == "POST":

            # ---------------------------------------------
            # MARK RECONCILED
            # ---------------------------------------------

            payment_request.is_reconciled = True

            payment_request.reconciled_by = request.user

            payment_request.reconciled_at = timezone.now()

            payment_request.save()

            # =============================================
            # IMPORTANT:
            # RUN LIFECYCLE FOR MEMBERSHIP/SUBSCRIPTION
            # =============================================

            process_payment_lifecycle()

            messages.success(
                request,
                "Payment request reconciled successfully."
            )

            return redirect(
                "members_admin:admin_payment_detail",
                payment_request.id
            )

        return render(
            request,
            "members/admin/claims/reconcile_simple.html",
            {
                "payment_request": payment_request,
                "total_required": total_required,
                "total_collected": total_collected,
                "paid_count": paid_count,
                "unpaid_count": unpaid_count,
                "compliance": compliance,
            }
        )


# =========================================================
# APPROVE CLAIM SETTLEMENT
# =========================================================

@admin_required
def approve_claim_settlementOnHold(request, settlement_id):

    settlement = get_object_or_404(
        ClaimSettlement,
        id=settlement_id
    )

    # =====================================================
    # PREVENT SELF APPROVAL
    # =====================================================

    if settlement.prepared_by == request.user:

        messages.error(
            request,
            "You cannot approve your own reconciliation."
        )

        return redirect(
            "members_admin:claim_settlement_detail",
            settlement.id
        )

    # =====================================================
    # APPROVE
    # =====================================================

    settlement.is_approved = True

    settlement.approved_by = request.user

    settlement.settlement_date = timezone.now()

    settlement.save()

    # =====================================================
    # IMPORTANT:
    # RUN PAYMENT LIFECYCLE
    # =====================================================

    process_payment_lifecycle()

    messages.success(
        request,
        "Claim settlement approved successfully."
    )

    return redirect(
        "members_admin:claim_settlement_detail",
        settlement.id
    )

@admin_required
def reconcile_claim_workingPartially(request, request_id):
    """
    UNIVERSAL RECONCILIATION

    CLAIM FLOW
    ------------------------------------------------
    deductions
    -> submit for approval
    -> second admin approval
    -> finalised

    NON-CLAIM FLOW
    ------------------------------------------------
    reconciliation report
    -> confirm reconciliation
    -> finalised
    """

    payment_request = get_object_or_404(
        PaymentRequest,
        id=request_id
    )

    # =====================================================
    # MUST BE CLOSED FIRST
    # =====================================================

    if payment_request.status != PaymentRequest.STATUS_CLOSED:

        messages.warning(
            request,
            "Close request before reconciliation."
        )

        return redirect(
            "members_admin:admin_payment_detail",
            payment_request.id
        )

    # =====================================================
    # CLAIM LINK
    # =====================================================

    claim = getattr(payment_request, "claim", None)

    # =====================================================
    # CLAIM FLOW
    # =====================================================

    if claim:

        settlement, _ = ClaimSettlement.objects.get_or_create(
            claim=claim,
            defaults={
                "settlement_date": timezone.now()
            }
        )

        # -------------------------------------------------
        # ALREADY APPROVED
        # -------------------------------------------------

        if settlement.is_approved:

            messages.info(
                request,
                "This settlement has already been finalised."
            )

            return redirect(
                "members_admin:claim_settlement_detail",
                settlement.id
            )

        # =================================================
        # DEDUCTION FORMSET
        # =================================================

        DeductionFormSet = modelformset_factory(
            ClaimSettlementDeduction,
            form=ClaimSettlementDeductionForm,
            extra=1,
            can_delete=True
        )

        # =================================================
        # POST
        # =================================================

        if request.method == "POST":

            formset = DeductionFormSet(
                request.POST,
                queryset=settlement.deduction_items.all()
            )

            notes = request.POST.get(
                "notes",
                ""
            )

            # -------------------------------------------------
            # VALIDATION
            # -------------------------------------------------

            if formset.is_valid():

                # ---------------------------------------------
                # SAVE DEDUCTIONS
                # ---------------------------------------------

                instances = formset.save(commit=False)

                for obj in instances:

                    obj.settlement = settlement
                    obj.save()

                # ---------------------------------------------
                # DELETE REMOVED ROWS
                # ---------------------------------------------

                for obj in formset.deleted_objects:
                    obj.delete()

                # ---------------------------------------------
                # UPDATE SETTLEMENT
                # ---------------------------------------------

                settlement.notes = notes

                settlement.prepared_by = request.user

                settlement.is_approved = False

                settlement.save()

                messages.success(
                    request,
                    "Reconciliation submitted for approval."
                )

                # ---------------------------------------------
                # IMPORTANT:
                # GO TO REVIEW / APPROVAL PAGE
                # ---------------------------------------------

                return redirect(
                    "members_admin:claim_settlement_detail",
                    settlement.id
                )

            # -------------------------------------------------
            # FORM ERRORS
            # -------------------------------------------------

            messages.error(
                request,
                "Please correct errors before submitting."
            )

        else:

            formset = DeductionFormSet(
                queryset=settlement.deduction_items.all()
            )

        # =================================================
        # RENDER CLAIM PAGE
        # =================================================

        return render(
            request,
            "members/admin/claims/reconcile_claim.html",
            {
                "settlement": settlement,
                "payment_request": payment_request,
                "formset": formset,
                "empty_form": formset.empty_form,
            }
        )

    # =====================================================
    # NON-CLAIM FLOW
    # =====================================================

    else:

        # -------------------------------------------------
        # TARGET MEMBERS
        # -------------------------------------------------

        if (
            payment_request.viewable_by_all
            and payment_request.member
            and payment_request.member.organization
        ):

            all_members = Member.objects.filter(
                organization=payment_request.member.organization,
                status=Member.STATUS_ACTIVE
            )

        elif payment_request.selected_members.exists():

            all_members = payment_request.selected_members.all()

        elif payment_request.member:

            all_members = Member.objects.filter(
                id=payment_request.member.id
            )

        else:

            all_members = Member.objects.none()

        # -------------------------------------------------
        # STATS
        # -------------------------------------------------

        total_required = payment_request.amount

        total_collected = payment_request.total_paid or 0

        paid_count = payment_request.paid_members.count()

        unpaid_count = max(
            0,
            all_members.count() - paid_count
        )

        compliance = 0

        if all_members.exists():

            compliance = int(
                (paid_count / all_members.count()) * 100
            )

        # =================================================
        # POST = CONFIRM RECONCILIATION
        # =================================================

        if request.method == "POST":

            # ---------------------------------------------
            # MARK RECONCILED
            # ---------------------------------------------

            payment_request.is_reconciled = True

            payment_request.reconciled_by = request.user

            payment_request.reconciled_at = timezone.now()

            payment_request.save()

            # ---------------------------------------------
            # IMPORTANT:
            # RUN LIFECYCLE ENGINE
            # ---------------------------------------------

            process_payment_lifecycle()

            messages.success(
                request,
                "Payment request reconciled successfully."
            )

            # ---------------------------------------------
            # RETURN TO DETAIL PAGE
            # ---------------------------------------------

            return redirect(
                "members_admin:admin_payment_detail",
                payment_request.id
            )

        # =================================================
        # RENDER SIMPLE RECONCILIATION PAGE
        # =================================================

        return render(
            request,
            "members/admin/claims/reconcile_simple.html",
            {
                "payment_request": payment_request,
                "total_required": total_required,
                "total_collected": total_collected,
                "paid_count": paid_count,
                "unpaid_count": unpaid_count,
                "compliance": compliance,
            }
        )

@admin_required
def reconcile_claim_03_05_26(request, request_id):
    """
    SAFE RECONCILIATION (NO MODEL CHANGES)

    ✔ Works with existing ClaimSettlement model
    ✔ Supports claim-based flow only (no regression)
    """

    payment_request = get_object_or_404(PaymentRequest, id=request_id)

    # -----------------------------------
    # 🚫 MUST BE CLOSED
    # -----------------------------------
    if payment_request.status != PaymentRequest.STATUS_CLOSED:
        messages.warning(request, "Close request before reconciliation.")
        return redirect("members_admin:admin_payment_detail", payment_request.id)

    # -----------------------------------
    # 🚫 MUST HAVE CLAIM (MODEL LIMITATION)
    # -----------------------------------
    if not payment_request.claim:
        messages.error(
            request,
            "Reconciliation is currently only available for claim-based payment requests."
        )
        return redirect("members_admin:admin_payment_detail", payment_request.id)

    claim = payment_request.claim

    # -----------------------------------
    # SAFE GET OR CREATE
    # -----------------------------------
    settlement, _ = ClaimSettlement.objects.get_or_create(
        claim=claim,
        defaults={"settlement_date": timezone.now()}
    )

    DeductionFormSet = inlineformset_factory(
        ClaimSettlement,
        ClaimSettlementDeduction,
        form=ClaimSettlementDeductionForm,
        extra=1,
        can_delete=True
    )

    if request.method == "POST":

        formset = DeductionFormSet(
            request.POST,
            queryset=settlement.deduction_items.all()
        )

        notes = request.POST.get("notes", "")

        if formset.is_valid():

            instances = formset.save(commit=False)

            for obj in instances:
                obj.settlement = settlement
                obj.save()

            for obj in formset.deleted_objects:
                obj.delete()

            settlement.notes = notes
            settlement.prepared_by = request.user
            settlement.is_approved = False
            settlement.save()

            messages.success(request, "Reconciliation saved.")

            return redirect(
                "members_admin:claim_settlement_detail",
                settlement.id
            )

    else:
        formset = DeductionFormSet(
            queryset=settlement.deduction_items.all()
        )

    return render(
        request,
        "members/admin/claims/reconcile_claim.html",
        {
            "settlement": settlement,
            "payment_request": payment_request,
            "formset": formset,
            "empty_form": formset.empty_form,
        }
    )

@admin_required
def reconcile_claim_WorkingOnHold(request, request_id):
    """
    UNIVERSAL RECONCILIATION

    CLAIM FLOW
    ------------------------------------------------
    deductions
    -> submit for approval
    -> second admin approval
    -> finalised

    NON-CLAIM FLOW
    ------------------------------------------------
    reconciliation report
    -> confirm reconciliation
    -> finalised
    """

    payment_request = get_object_or_404(
        PaymentRequest,
        id=request_id
    )

    # =====================================================
    # MUST BE CLOSED FIRST
    # =====================================================

    if payment_request.status != PaymentRequest.STATUS_CLOSED:

        messages.warning(
            request,
            "Close request before reconciliation."
        )

        return redirect(
            "members_admin:admin_payment_detail",
            payment_request.id
        )

    # =====================================================
    # CLAIM LINK
    # =====================================================

    claim = getattr(payment_request, "claim", None)

    # =====================================================
    # CLAIM FLOW
    # =====================================================

    if claim:

        settlement, _ = ClaimSettlement.objects.get_or_create(
            claim=claim,
            defaults={
                "settlement_date": timezone.now()
            }
        )

        # -------------------------------------------------
        # ALREADY APPROVED
        # -------------------------------------------------

        if settlement.is_approved:

            messages.info(
                request,
                "This settlement has already been finalised."
            )

            return redirect(
                "members_admin:claim_settlement_detail",
                settlement.id
            )

        # =================================================
        # DEDUCTION FORMSET
        # =================================================

        DeductionFormSet = modelformset_factory(
            ClaimSettlementDeduction,
            form=ClaimSettlementDeductionForm,
            extra=1,
            can_delete=True
        )

        # =================================================
        # POST
        # =================================================

        if request.method == "POST":

            formset = DeductionFormSet(
                request.POST,
                queryset=settlement.deduction_items.all()
            )

            notes = request.POST.get(
                "notes",
                ""
            )

            # -------------------------------------------------
            # VALIDATION
            # -------------------------------------------------

            if formset.is_valid():

                # ---------------------------------------------
                # SAVE DEDUCTIONS
                # ---------------------------------------------

                instances = formset.save(commit=False)

                for obj in instances:

                    obj.settlement = settlement
                    obj.save()

                # ---------------------------------------------
                # DELETE REMOVED ROWS
                # ---------------------------------------------

                for obj in formset.deleted_objects:
                    obj.delete()

                # ---------------------------------------------
                # UPDATE SETTLEMENT
                # ---------------------------------------------

                settlement.notes = notes

                settlement.prepared_by = request.user

                settlement.is_approved = False

                settlement.save()

                messages.success(
                    request,
                    "Reconciliation submitted for approval."
                )

                # ---------------------------------------------
                # IMPORTANT:
                # GO TO REVIEW / APPROVAL PAGE
                # ---------------------------------------------

                return redirect(
                    "members_admin:claim_settlement_detail",
                    settlement.id
                )

            # -------------------------------------------------
            # FORM ERRORS
            # -------------------------------------------------

            messages.error(
                request,
                "Please correct errors before submitting."
            )

        else:

            formset = DeductionFormSet(
                queryset=settlement.deduction_items.all()
            )

        # =================================================
        # RENDER CLAIM PAGE
        # =================================================

        return render(
            request,
            "members/admin/claims/reconcile_claim.html",
            {
                "settlement": settlement,
                "payment_request": payment_request,
                "formset": formset,
                "empty_form": formset.empty_form,
            }
        )

    # =====================================================
    # NON-CLAIM FLOW
    # =====================================================

    else:

        # -------------------------------------------------
        # TARGET MEMBERS
        # -------------------------------------------------

        if (
            payment_request.viewable_by_all
            and payment_request.member
            and payment_request.member.organization
        ):

            all_members = Member.objects.filter(
                organization=payment_request.member.organization,
                status=Member.STATUS_ACTIVE
            )

        elif payment_request.selected_members.exists():

            all_members = payment_request.selected_members.all()

        elif payment_request.member:

            all_members = Member.objects.filter(
                id=payment_request.member.id
            )

        else:

            all_members = Member.objects.none()

        # -------------------------------------------------
        # STATS
        # -------------------------------------------------

        total_required = payment_request.amount

        total_collected = payment_request.total_paid or 0

        paid_count = payment_request.paid_members.count()

        unpaid_count = max(
            0,
            all_members.count() - paid_count
        )

        compliance = 0

        if all_members.exists():

            compliance = int(
                (paid_count / all_members.count()) * 100
            )

        # =================================================
        # POST = CONFIRM RECONCILIATION
        # =================================================

        if request.method == "POST":

            # ---------------------------------------------
            # MARK RECONCILED
            # ---------------------------------------------

            payment_request.is_reconciled = True

            payment_request.reconciled_by = request.user

            payment_request.reconciled_at = timezone.now()

            payment_request.save()

            messages.success(
                request,
                "Payment request reconciled successfully."
            )

            # ---------------------------------------------
            # RETURN TO DETAIL PAGE
            # ---------------------------------------------

            return redirect(
                "members_admin:admin_payment_detail",
                payment_request.id
            )

        # =================================================
        # RENDER SIMPLE RECONCILIATION PAGE
        # =================================================

        return render(
            request,
            "members/admin/claims/reconcile_simple.html",
            {
                "payment_request": payment_request,
                "total_required": total_required,
                "total_collected": total_collected,
                "paid_count": paid_count,
                "unpaid_count": unpaid_count,
                "compliance": compliance,
            }
        )

@admin_required
def reconcile_claimWithProblems(request, request_id):
    """
    UNIVERSAL RECONCILIATION

    ✔ CLAIM → full deductions flow
    ✔ OTHERS → simple reconciliation (no deductions)
    """

    payment_request = get_object_or_404(
        PaymentRequest,
        id=request_id
    )

    # -----------------------------------
    # MUST BE CLOSED FIRST
    # -----------------------------------
    if payment_request.status != PaymentRequest.STATUS_CLOSED:
        messages.warning(
            request,
            "Close request before reconciliation."
        )

        return redirect(
            "members_admin:admin_payment_detail",
            payment_request.id
        )

    claim = payment_request.claim

    # =====================================================
    # CLAIM FLOW
    # =====================================================
    if claim:

        settlement, created = ClaimSettlement.objects.get_or_create(
            claim=claim,
            defaults={
                "settlement_date": timezone.now()
            }
        )

        # -----------------------------------
        # LOCK RECONCILIATION AFTER SUBMISSION
        # -----------------------------------
        if settlement.prepared_by:

            messages.info(
                request,
                "Reconciliation already submitted. Proceed to approval."
            )

            return redirect(
                "members_admin:claim_settlement_detail",
                settlement.id
            )

        DeductionFormSet = modelformset_factory(
            ClaimSettlementDeduction,
            form=ClaimSettlementDeductionForm,
            extra=1,
            can_delete=True
        )

        if request.method == "POST":

            formset = DeductionFormSet(
                request.POST,
                queryset=settlement.deduction_items.all()
            )

            notes = request.POST.get("notes", "")

            if formset.is_valid():

                instances = formset.save(commit=False)

                # -----------------------------------
                # SAVE DEDUCTIONS
                # -----------------------------------
                for instance in instances:
                    instance.settlement = settlement
                    instance.save()

                # -----------------------------------
                # DELETE REMOVED ROWS
                # -----------------------------------
                for obj in formset.deleted_objects:
                    obj.delete()

                # -----------------------------------
                # UPDATE SETTLEMENT
                # -----------------------------------
                settlement.notes = notes
                settlement.prepared_by = request.user
                settlement.is_approved = False
                settlement.save()

                messages.success(
                    request,
                    "Reconciliation submitted for approval."
                )

                return redirect(
                    "members_admin:claim_settlement_detail",
                    settlement.id
                )

            else:
                print("FORMSET ERRORS:", formset.errors)
                print("NON FORM ERRORS:", formset.non_form_errors())

                messages.error(
                    request,
                    "Please correct errors before submitting."
                )

        else:

            formset = DeductionFormSet(
                queryset=settlement.deduction_items.all()
            )

        return render(
            request,
            "members/admin/claims/reconcile_claim.html",
            {
                "settlement": settlement,
                "payment_request": payment_request,
                "formset": formset,
                "empty_form": formset.empty_form,
            }
        )

    # =====================================================
    # SIMPLE RECONCILIATION
    # =====================================================
    else:

        total_required = payment_request.amount
        total_collected = payment_request.total_paid

        paid_members = payment_request.paid_members.all()
        paid_count = paid_members.count()

        # -----------------------------------
        # DETERMINE TARGET MEMBERS
        # -----------------------------------

        if (
            payment_request.viewable_by_all
            and payment_request.member
            and payment_request.member.organization
        ):

            all_members = Member.objects.filter(
                organization=payment_request.member.organization,
                status=Member.STATUS_ACTIVE
            )

        elif payment_request.selected_members.exists():

            all_members = payment_request.selected_members.all()

        elif payment_request.member:

            all_members = Member.objects.filter(
                id=payment_request.member.id
            )

        else:

            all_members = Member.objects.none()

        # ---------------------------------------------
        # STATS
        # ---------------------------------------------

        total_required = payment_request.amount

        total_collected = payment_request.total_paid or 0

        paid_count = payment_request.paid_members.count()

        unpaid_count = max(
            0,
            all_members.count() - paid_count
        )

        compliance = 0

        if all_members.exists():

            compliance = int(
                (paid_count / all_members.count()) * 100
            )

        # ---------------------------------------------
        # POST CONFIRMATION
        # ---------------------------------------------

        if request.method == "POST":

            # -----------------------------------------
            # SAVE RECONCILIATION STATUS
            # -----------------------------------------

            payment_request.reconciliation_status = "submitted"

            payment_request.reconciled_by = request.user

            payment_request.save()

            messages.success(
                request,
                "Reconciliation submitted successfully."
            )

            return redirect(
                "members_admin:admin_payment_detail",
                payment_request.id
            )

        # ---------------------------------------------
        # GET PAGE
        # ---------------------------------------------

        messages.info(
            request,
            "This payment request does not require deductions."
        )

        return render(
            request,
            "members/admin/claims/reconcile_simple.html",
            {
                "payment_request": payment_request,
                "total_required": total_required,
                "total_collected": total_collected,
                "paid_count": paid_count,
                "unpaid_count": unpaid_count,
                "compliance": compliance,
            }
        )
@admin_required
def confirm_claim_settlement(request, settlement_id):

    settlement = get_object_or_404(ClaimSettlement, id=settlement_id)
    claim = settlement.claim

    claim.status = "settled"
    claim.save(update_fields=["status"])

    messages.success(request, "Claim settled successfully.")

    return redirect("members_admin:claim_settlement_detail", settlement.id)



@admin_required
def approve_claim_settlement(request, settlement_id):

    settlement = get_object_or_404(
        ClaimSettlement,
        id=settlement_id
    )

    # -----------------------------------
    # PREVENT SELF APPROVAL
    # -----------------------------------
    if settlement.prepared_by == request.user:

        messages.error(
            request,
            "You cannot approve your own reconciliation."
        )

        return redirect(
            "members_admin:claim_settlement_detail",
            settlement.id
        )

    # -----------------------------------
    # APPROVE
    # -----------------------------------
    settlement.is_approved = True
    settlement.approved_by = request.user
    settlement.settlement_date = timezone.now()

    settlement.save()
    
    # =====================================================
    # RUN PAYMENT LIFECYCLE
    # =====================================================

    process_payment_lifecycle()

    # -----------------------------------
    # CLOSE CLAIM
    # -----------------------------------
    claim = settlement.claim

    claim.status = Claim.STATUS_SETTLED
    claim.settlement_date = timezone.now()

    claim.save()

    messages.success(
        request,
        "Claim settlement approved successfully."
    )

    return redirect(
        "members_admin:claim_settlement_detail",
        settlement.id
    )

def export_claim_pdf(request, settlement_id):

    settlement = get_object_or_404(ClaimSettlement, id=settlement_id)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="claim_{settlement.id}.pdf"'

    doc = SimpleDocTemplate(response)
    styles = getSampleStyleSheet()

    elements = []

    # ---------------------------
    # HEADER
    # ---------------------------
    elements.append(Paragraph("CLAIM SETTLEMENT REPORT", styles["Title"]))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph(f"Claim: {settlement.claim}", styles["Normal"]))
    elements.append(Paragraph(f"Payment Request ID: {settlement.claim.payment_request.id}", styles["Normal"]))
    elements.append(Paragraph(f"Settlement Date: {settlement.settlement_date}", styles["Normal"]))
    elements.append(Spacer(1, 12))

    # ---------------------------
    # FINANCIAL SUMMARY TABLE
    # ---------------------------
    summary_data = [
        ["Description", "Amount (£)"],
        ["Total Collected", f"{settlement.total_collected:.2f}"],
        ["Total Deductions", f"{settlement.total_deductions:.2f}"],
        ["Net Paid", f"{settlement.amount_paid:.2f}"],
    ]

    summary_table = Table(summary_data)
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.grey),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("GRID", (0,0), (-1,-1), 1, colors.black),
        ("ALIGN",(1,1),(-1,-1),"RIGHT"),
    ]))

    elements.append(Paragraph("Financial Summary", styles["Heading2"]))
    elements.append(summary_table)
    elements.append(Spacer(1, 12))

    # ---------------------------
    # DEDUCTIONS TABLE
    # ---------------------------
    elements.append(Paragraph("Deductions Breakdown", styles["Heading2"]))

    deductions = settlement.deduction_items.all()

    if deductions.exists():

        data = [["Item", "Amount (£)"]]

        for d in deductions:
            data.append([d.title, f"{d.amount:.2f}"])

        table = Table(data)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
            ("GRID", (0,0), (-1,-1), 1, colors.black),
            ("ALIGN",(1,1),(-1,-1),"RIGHT"),
        ]))

        elements.append(table)

    else:
        elements.append(Paragraph("No deductions recorded.", styles["Normal"]))

    elements.append(Spacer(1, 12))

    # ---------------------------
    # NOTES
    # ---------------------------
    elements.append(Paragraph("Notes", styles["Heading2"]))
    elements.append(Paragraph(settlement.notes or "-", styles["Normal"]))
    elements.append(Spacer(1, 12))

    # ---------------------------
    # SIGNATURE BLOCK
    # ---------------------------
    elements.append(Paragraph("Authorisation", styles["Heading2"]))

    elements.append(Paragraph(
        f"Prepared By: {settlement.prepared_by}", styles["Normal"]
    ))

    elements.append(Paragraph(
        f"Approved By: {settlement.approved_by or 'Pending'}",
        styles["Normal"]
    ))

    doc.build(elements)

    return response

@admin_required
def settled_claims(request):

    settlements = (
        ClaimSettlement.objects
        .filter(is_approved=True)
        .select_related(
            "claim",
            "prepared_by",
            "approved_by"
        )
        .order_by("-settlement_date")
    )

    return render(
        request,
        "members/admin/claims/settled_claims.html",
        {
            "settlements": settlements
        }
    )