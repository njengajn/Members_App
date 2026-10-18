from django.contrib.staticfiles import finders
from django.db import transaction
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
from reportlab.platypus import Image, SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
)
from reportlab.lib import colors
from django.forms import inlineformset_factory
from backend.members.services.payment_lifecycle import (get_pending_payment_approvals, process_reconciled_payment_request, process_payment_lifecycle)
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
@transaction.atomic
def reconcile_claim(request, request_id):
    """
    Reconcile one closed payment request.

    BUSINESS RULES
    ------------------------------------------------
    1. The request must already be closed.
    2. Pending payment approvals block reconciliation.
    3. The administrator who closed the request may reconcile it.
    4. The administrator who prepares claim reconciliation
       cannot approve that settlement.
    5. Never invoke the global payment lifecycle here.
    6. Claim retirement occurs only after settlement approval.
    7. Non-claim reconciliation uses the original target snapshot.
    8. Unpaid outcomes are saved for historical reporting.
    """

    # Lock and load only the requested payment request.
    payment_request = get_object_or_404(
        PaymentRequest.objects.select_for_update().select_related(
            "member",
            "claim",
        ).prefetch_related(
            "selected_members",
            "paid_members",
            "targeted_members",
        ),
        id=request_id,
    )

    # Reconciliation is allowed only after closure.
    if payment_request.status != PaymentRequest.STATUS_CLOSED:
        messages.warning(
            request,
            "Close request before reconciliation.",
        )
        return redirect(
            "members_admin:admin_payment_detail",
            payment_request.id,
        )

    # The closer is allowed to reconcile.
    # Separation of duties is enforced at settlement approval:
    # the preparer must not approve their own reconciliation.

    # Do not reconcile while non-rejected payment approvals remain.
    if get_pending_payment_approvals(payment_request).exists():
        messages.warning(
            request,
            (
                "Reconciliation cannot proceed because one or more "
                "payments are awaiting approval. Approve or reject "
                "all pending payments first."
            ),
        )
        return redirect(
            "members_admin:admin_payment_detail",
            payment_request.id,
        )

    claim = getattr(payment_request, "claim", None)

    # =========================================================
    # CLAIM RECONCILIATION
    # =========================================================
    if claim is not None:
        settlement, _ = ClaimSettlement.objects.get_or_create(
            claim=claim,
            defaults={
                "settlement_date": timezone.now(),
            },
        )

        # An approved settlement must not be edited or prepared again.
        if settlement.is_approved:
            messages.info(
                request,
                "This settlement has already been finalised.",
            )
            return redirect(
                "members_admin:claim_settlement_detail",
                settlement.id,
            )

        DeductionFormSet = modelformset_factory(
            ClaimSettlementDeduction,
            form=ClaimSettlementDeductionForm,
            extra=1,
            can_delete=True,
        )

        if request.method == "POST":
            formset = DeductionFormSet(
                request.POST,
                queryset=settlement.deduction_items.all(),
            )
            notes = request.POST.get("notes", "")

            if formset.is_valid():
                # Recheck before changing deductions or settlement data.
                if get_pending_payment_approvals(
                    payment_request
                ).exists():
                    messages.warning(
                        request,
                        (
                            "Reconciliation was not saved because "
                            "a payment is awaiting approval. Approve "
                            "or reject it before continuing."
                        ),
                    )
                    return redirect(
                        "members_admin:admin_payment_detail",
                        payment_request.id,
                    )

                instances = formset.save(commit=False)

                for obj in instances:
                    obj.settlement = settlement
                    obj.save()

                # Apply requested deletions from the formset.
                for obj in formset.deleted_objects:
                    obj.delete()

                # Record preparation, not approval.
                # Do not retire the claim's causer in this function.
                settlement.notes = notes
                settlement.prepared_by = request.user
                settlement.is_approved = False
                settlement.approved_by = None
                settlement.save()

                messages.success(
                    request,
                    "Reconciliation submitted for approval.",
                )
                return redirect(
                    "members_admin:claim_settlement_detail",
                    settlement.id,
                )

            messages.error(
                request,
                "Please correct errors before submitting.",
            )

        else:
            formset = DeductionFormSet(
                queryset=settlement.deduction_items.all(),
            )

        return render(
            request,
            "members/admin/claims/reconcile_claim.html",
            {
                "settlement": settlement,
                "payment_request": payment_request,
                "formset": formset,
                "empty_form": formset.empty_form,
            },
        )

    # =========================================================
    # NON-CLAIM RECONCILIATION
    # =========================================================
    # Use the saved target population from request creation.
    # Do not filter by current member status: a targeted member
    # must remain in the historical report after retirement.

    target_member_ids = set(
        payment_request.targeted_members.values_list(
            "id",
            flat=True,
        )
    )

    # Older requests may not have a target snapshot. Do not silently
    # replace their historical population with today's active members.
    if not target_member_ids:
        messages.error(
            request,
            (
                "Reconciliation cannot proceed because this payment "
                "request has no saved target population. Establish "
                "the original target members before reconciling."
            ),
        )
        return redirect(
            "members_admin:admin_payment_detail",
            payment_request.id,
        )

    total_required = payment_request.amount
    total_collected = payment_request.total_paid or 0

    # Preserve the existing paid-members source, restricted to the
    # original target population for this request.
    paid_member_ids = set(
        payment_request.paid_members.filter(
            id__in=target_member_ids,
        ).values_list(
            "id",
            flat=True,
        )
    )

    unpaid_member_ids = target_member_ids - paid_member_ids

    total_members = len(target_member_ids)
    paid_count = len(paid_member_ids)
    unpaid_count = len(unpaid_member_ids)

    compliance = (
        int((paid_count / total_members) * 100)
        if total_members
        else 0
    )

    # =========================================================
    # CONFIRM NON-CLAIM RECONCILIATION
    # =========================================================
    if request.method == "POST":
        # Check again immediately before recording reconciliation.
        if get_pending_payment_approvals(
            payment_request
        ).exists():
            messages.warning(
                request,
                (
                    "Reconciliation was not saved because a payment "
                    "is awaiting approval. Approve or reject it first."
                ),
            )
            return redirect(
                "members_admin:admin_payment_detail",
                payment_request.id,
            )

        # Recalculate the outcome immediately before saving, using
        # the locked request and the saved target population.
        target_member_ids = set(
            payment_request.targeted_members.values_list(
                "id",
                flat=True,
            )
        )

        if not target_member_ids:
            messages.error(
                request,
                (
                    "Reconciliation cannot proceed because this payment "
                    "request has no saved target population."
                ),
            )
            return redirect(
                "members_admin:admin_payment_detail",
                payment_request.id,
            )

        paid_member_ids = set(
            payment_request.paid_members.filter(
                id__in=target_member_ids,
            ).values_list(
                "id",
                flat=True,
            )
        )

        unpaid_member_ids = target_member_ids - paid_member_ids

        # Persist the unpaid snapshot in the same transaction as
        # reconciliation and request-specific lifecycle processing.
        payment_request.unpaid_members.set(unpaid_member_ids)

        payment_request.is_reconciled = True
        payment_request.reconciled_by = request.user
        payment_request.reconciled_at = timezone.now()
        payment_request.save(
            update_fields=[
                "is_reconciled",
                "reconciled_by",
                "reconciled_at",
                "updated_at",
            ],
        )

        # Process this request only. Never invoke the global lifecycle.
        processed = process_reconciled_payment_request(
            request_id=payment_request.id,
            performed_by=request.user,
        )

        if not processed:
            # Roll back reconciliation and any changes made in this
            # atomic transaction.
            transaction.set_rollback(True)
            messages.error(
                request,
                (
                    "Reconciliation could not be completed. "
                    "No changes have been saved."
                ),
            )
            return redirect(
                "members_admin:admin_payment_detail",
                payment_request.id,
            )

        messages.success(
            request,
            "Payment request reconciled successfully.",
        )
        return redirect(
            "members_admin:admin_payment_detail",
            payment_request.id,
        )

    # GET: display the existing reconciliation summary.
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
        },
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
@transaction.atomic
def approve_claim_settlement(request, settlement_id):
    """
    Approve a prepared claim settlement.

    BUSINESS RULES
    ------------------------------------------------
    1. Approval requires POST.
    2. The settlement must have been prepared.
    3. The preparer cannot approve their own reconciliation.
    4. The payment request must be closed.
    5. Pending payment approvals block settlement approval.
    6. Claim retirement occurs only after successful approval.
    7. Never run the global payment lifecycle here.
    """

    # Approval must be an explicit form submission.
    if request.method != "POST":
        messages.warning(
            request,
            "Submit the approval form to approve this settlement.",
        )
        return redirect(
            "members_admin:claim_settlement_detail",
            settlement_id,
        )

    # Lock the settlement to prevent concurrent approvals.
    settlement = get_object_or_404(
        ClaimSettlement.objects.select_for_update(),
        id=settlement_id,
    )
    claim = settlement.claim

    # Do not approve or process retirement twice.
    if settlement.is_approved:
        messages.info(
            request,
            "This settlement has already been approved.",
        )
        return redirect(
            "members_admin:claim_settlement_detail",
            settlement.id,
        )

    # Reconciliation must be prepared before it can be approved.
    if settlement.prepared_by is None:
        messages.error(
            request,
            "This settlement has not been prepared for approval.",
        )
        return redirect(
            "members_admin:claim_settlement_detail",
            settlement.id,
        )

    # Enforce separation of duties: the preparer cannot approve.
    if settlement.prepared_by_id == request.user.id:
        messages.error(
            request,
            "You cannot approve your own reconciliation.",
        )
        return redirect(
            "members_admin:claim_settlement_detail",
            settlement.id,
        )

    # Lock the payment request linked to this claim.
    payment_request = (
        PaymentRequest.objects
        .select_for_update()
        .filter(claim=claim)
        .first()
    )

    if payment_request is None:
        messages.error(
            request,
            "No payment request is linked to this claim settlement.",
        )
        return redirect(
            "members_admin:claim_settlement_detail",
            settlement.id,
        )

    # The request must already be closed.
    if payment_request.status != PaymentRequest.STATUS_CLOSED:
        messages.warning(
            request,
            "The payment request must be closed before settlement approval.",
        )
        return redirect(
            "members_admin:claim_settlement_detail",
            settlement.id,
        )

    # Do not approve while non-rejected payments remain unresolved.
    if get_pending_payment_approvals(payment_request).exists():
        messages.warning(
            request,
            (
                "Settlement approval cannot proceed because one or "
                "more payments are awaiting approval. Approve or "
                "reject all pending payments first."
            ),
        )
        return redirect(
            "members_admin:claim_settlement_detail",
            settlement.id,
        )

    # Record approval and claim settlement within the atomic transaction.
    approved_at = timezone.now()

    settlement.is_approved = True
    settlement.approved_by = request.user
    settlement.settlement_date = approved_at
    settlement.save(
        update_fields=[
            "is_approved",
            "approved_by",
            "settlement_date",
        ],
    )

    claim.status = Claim.STATUS_SETTLED
    claim.settlement_date = approved_at
    claim.save(
        update_fields=[
            "status",
            "settlement_date",
        ],
    )

    # Apply claim-specific retirement to this request only.
    # If processing fails, roll back the approval and claim updates.
    processed = process_reconciled_payment_request(
        request_id=payment_request.id,
        performed_by=request.user,
    )

    if not processed:
        transaction.set_rollback(True)
        messages.error(
            request,
            (
                "Claim settlement approval could not be completed. "
                "No changes have been saved."
            ),
        )
        return redirect(
            "members_admin:claim_settlement_detail",
            settlement.id,
        )

    messages.success(
        request,
        "Claim settlement approved successfully.",
    )
    return redirect(
        "members_admin:claim_settlement_detail",
        settlement.id,
    )


def export_claim_pdf(request, settlement_id):
    """
    Export a claim settlement report.

    Authorisation displays full admin names when available.
    The report distinguishes pending reconciliation,
    pending approval and finalised settlements.
    """

    settlement = get_object_or_404(
        ClaimSettlement,
        id=settlement_id,
    )

    response = HttpResponse(
        content_type="application/pdf"
    )

    response["Content-Disposition"] = (
        f'attachment; filename="claim_{settlement.id}.pdf"'
    )

    doc = SimpleDocTemplate(response)
    styles = getSampleStyleSheet()
    elements = []

    # REPORT LOGO
    # =====================================================

    logo_path = finders.find(
        "images/logo.png"
    )

    if logo_path:

        logo = Image(
            logo_path,
            width=100,
            height=50,
            hAlign="CENTER",
        )

        elements.append(
            logo
        )

        elements.append(
            Spacer(1, 8)
        )

    # =====================================================
    # HEADER
    # =====================================================

    elements.append(
        Paragraph(
            "CLAIM SETTLEMENT REPORT",
            styles["Title"],
        )
    )

    elements.append(
        Spacer(1, 12)
    )

    elements.append(
        Paragraph(
            f"Claim: {settlement.claim.member}",
            styles["Normal"],
        )
    )

    elements.append(
        Paragraph(
            f"Payment Request ID: {settlement.claim.payment_request.id}",
            styles["Normal"],
        )
    )

    # Display a readable date and time.
    if settlement.settlement_date:
        settlement_date = settlement.settlement_date.strftime(
            "%Y-%m-%d %H:%M"
        )
    else:
        settlement_date = "Pending"

    elements.append(
        Paragraph(
            f"Settlement Date: {settlement_date}",
            styles["Normal"],
        )
    )

    elements.append(
        Spacer(1, 12)
    )

    # =====================================================
    # FINANCIAL SUMMARY TABLE
    # =====================================================

    summary_data = [
        ["Description", "Amount (£)"],
        ["Total Collected", f"{settlement.total_collected:.2f}"],
        ["Total Deductions", f"{settlement.total_deductions:.2f}"],
        ["Net Paid", f"{settlement.amount_paid:.2f}"],
    ]

    summary_table = Table(summary_data)

    summary_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ])
    )

    elements.append(
        Paragraph(
            "Financial Summary",
            styles["Heading2"],
        )
    )

    elements.append(summary_table)
    elements.append(Spacer(1, 12))

    # =====================================================
    # DEDUCTIONS TABLE
    # =====================================================

    elements.append(
        Paragraph(
            "Deductions Breakdown",
            styles["Heading2"],
        )
    )

    deductions = settlement.deduction_items.all()

    if deductions.exists():
        data = [
            ["Item", "Amount (£)"],
        ]

        for deduction in deductions:
            data.append([
                deduction.title,
                f"{deduction.amount:.2f}",
            ])

        table = Table(data)

        table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ])
        )

        elements.append(table)

    else:
        elements.append(
            Paragraph(
                "No deductions recorded.",
                styles["Normal"],
            )
        )

    elements.append(
        Spacer(1, 12)
    )

    # =====================================================
    # NOTES
    # =====================================================

    elements.append(
        Paragraph(
            "Notes",
            styles["Heading2"],
        )
    )

    elements.append(
        Paragraph(
            settlement.notes or "-",
            styles["Normal"],
        )
    )

    elements.append(
        Spacer(1, 12)
    )

    # =====================================================
    # AUTHORISATION
    # =====================================================

    elements.append(
        Paragraph(
            "Authorisation",
            styles["Heading2"],
        )
    )

    # -----------------------------------------------------
    # ADMINISTRATOR FULL NAMES
    # -----------------------------------------------------

    prepared_by_user = settlement.prepared_by
    approved_by_user = settlement.approved_by

    if prepared_by_user:
        prepared_by = (
            prepared_by_user.get_full_name().strip()
            or prepared_by_user.get_username()
        )
    else:
        prepared_by = "Pending"

    if approved_by_user:
        approved_by = (
            approved_by_user.get_full_name().strip()
            or approved_by_user.get_username()
        )
    else:
        approved_by = "Pending"

    # -----------------------------------------------------
    # RECONCILIATION / APPROVAL STATUS
    # -----------------------------------------------------

    if settlement.is_approved:
        authorisation_status = "Finalised"

    elif settlement.prepared_by:
        authorisation_status = "Pending Approval"

    else:
        authorisation_status = "Pending Reconciliation"

    authorisation_data = [
        ["Prepared By", prepared_by],
        ["Approved By", approved_by],
        ["Settlement Date", settlement_date],
        ["Status", authorisation_status],
    ]

    authorisation_table = Table(
        authorisation_data,
        colWidths=[180, 310],
    )

    authorisation_table.setStyle(
        TableStyle([
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.5,
                colors.grey,
            ),
            (
                "FONTNAME",
                (0, 0),
                (0, -1),
                "Helvetica-Bold",
            ),
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "TOP",
            ),
            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                6,
            ),
            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                6,
            ),
        ])
    )

    elements.append(authorisation_table)

    # =====================================================
    # BUILD PDF
    # =====================================================

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