from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
#from backend.members.services.claim_service import approve_claim, ClaimService
from backend.members.forms import ClaimForm, ClaimBankDetailsForm, ClaimSubmissionDeclarationForm
from backend.members.services.claim_service import ClaimService
from backend.members.models import Claim, Member, MemberDocument, Payment, NextOfKin, PaymentRequest
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count
from backend.members.services.document_files import DocumentUploadValidationError, generate_document_thumbnail, prepare_document_file
from backend.members.views_admin import admin_required
from django.db import transaction
from .admin_auth import admin_required

@login_required
def approve_claim_view(request, claim_id):
    """
    Approve a claim

    ✔ prevents self-approval
    ✔ creates payment ONLY once
    ✔ uses correct order
    ✔ safe error handling
    """

    # ======================================================
    # GET CLAIM FIRST (🔥 FIX ORDER)
    # ======================================================
    claim = get_object_or_404(Claim, uid=claim_id)

    # ======================================================
    # PREVENT SELF APPROVAL
    # ======================================================
    if claim.created_by == request.user:
        messages.error(request, "You cannot approve a claim you created.")
        return redirect("members_admin:admin_claims_list")

    # ======================================================
    # PREVENT DOUBLE APPROVAL
    # ======================================================
    if claim.status == Claim.STATUS_APPROVED:
        messages.warning(request, "Claim already approved.")
        return redirect("members_admin:admin_claims_list")

    try:
        # ==================================================
        # APPROVE CLAIM (SERVICE)
        # ==================================================
        ClaimService.approve_claim(claim, by_user=request.user)

        # ==================================================
        # CREATE PAYMENT (ONLY IF NOT EXISTS)
        # ==================================================
        existing_payment = Payment.objects.filter(
            claim=claim
        ).exists()

        if not existing_payment:
            Payment.objects.create(
                member=claim.member,
                amount=claim.amount,
                status="pending",
                payment_type="claim",
                claim=claim,
            )

        messages.success(request, "Claim approved successfully.")

    except Exception as e:
        messages.error(request, str(e))

    return redirect("members_admin:admin_claims_list")


@admin_required
def approve_claimNotSure(request, claim_id):

    claim = get_object_or_404(Claim, id=claim_id)

    claim.status = "approved"
    claim.save()

    messages.success(request, "Claim approved.")
    
    return redirect("members_admin:claims")




@staff_member_required
def claims_list(request):
    """
    Show ONLY approved claims without payment requests
    """

    claims = (
        Claim.objects
        .filter(
            status=Claim.STATUS_APPROVED,
            payment_requests__isnull=True,
        )
        .select_related("member", "causer_dependant")
        .order_by("-created_at")
        .distinct()
    )

    return render(
        request,
        "members/admin/admin_claims_list.html",
        {"claims": claims},
    )


@staff_member_required
def claim_list(request):
    """
    Shows ONLY approved claims that do NOT yet have payment requests
    """

    claims = (
        Claim.objects
        .filter(
            status=Claim.STATUS_APPROVED,
            payment_requests__isnull=True,  # 🔐 enforce rule
        )
        .select_related("member", "causer_dependant")
        .order_by("-created_at")
    )

    return render(
        request,
        "members/admin/admin_claims_list.html",
        {"claims": claims},
    )


    
@staff_member_required
def admin_claim_detail(request, claim_id):
        claim = get_object_or_404(Claim, uid=claim_id)
        return render(
            request,
            "members/admin/claim_detail.html",
            {"claim": claim}
        )
    

@staff_member_required
def claims_list_admin(request):
    status = request.GET.get("status")

    claims = Claim.objects.all()

    if status:
        claims = claims.filter(status=status)

    claims = (
        claims
        .select_related("member")
        .order_by("-created_at")
    )

    return render(
        request,
        "members/admin/admin_claims_list.html",
        {"claims": claims},
    )


@staff_member_required
def admin_claims_list(request):

    status_filter = request.GET.get("status")

    claims = Claim.objects.all().order_by("-created_at")

    if status_filter:
        claims = claims.filter(status=status_filter)

    context = {
        "claims": claims,
        "pending_count": Claim.objects.filter(status="pending").count(),
        "approved_count": Claim.objects.filter(status="approved").count(),
        "open_count": Claim.objects.filter(status="open").count(),
        "rejected_count": Claim.objects.filter(status="rejected").count(),
        "settled_count": Claim.objects.filter(status="settled").count(),
    }

    return render(
        request,
        "members/admin/claims/admin_claims_list.html",
        context,
    )

# ==============================================================
# ADMIN CREATE CLAIM
# ==============================================================

@admin_required
def admin_create_claim(request):
    """
    ADMIN CLAIM CREATION

    MEMBER CAUSER
    --------------------------------------------------------------
    - Search/select an active member.
    - Selected member is the causer.
    - Selected member becomes claim.member.
    - Selected member's next of kin becomes the claimer.
    - Next-of-kin contacted confirmation is required.

    DEPENDANT CAUSER
    --------------------------------------------------------------
    - Only the signed-in admin's own active dependants are shown.
    - Member search remains hidden.
    - Selected dependant is the causer.
    - Dependant's member becomes claim.member.
    - Owning member becomes the claimer.
    - Next-of-kin confirmation is not required.

    BANK DETAILS
    --------------------------------------------------------------
    Saved through ClaimBankDetailsForm.

    DECLARATION
    --------------------------------------------------------------
    Saved through ClaimSubmissionDeclarationForm.

    DOCUMENTS
    --------------------------------------------------------------
    Multiple documents remain supported using the existing
    document upload mechanism.
    """

    # ==========================================================
    # ACCESS CONTROL
    # ==========================================================

    admin_member = getattr(
        request.user,
        "member",
        None,
    )

    if (
        not admin_member
        or admin_member.status != "active"
    ):

        messages.error(
            request,
            "Your account does not have active membership."
        )

        return redirect(
            "members_admin:dashboard"
        )

    # ==========================================================
    # INITIAL VALUES
    # ==========================================================

    selected_member = None
    next_of_kin = None

    # ==========================================================
    # GET
    # ==========================================================

    if request.method == "GET":

        form = ClaimForm(
            user=request.user,
            selected_member=None,
        )

        bank_form = ClaimBankDetailsForm()

        declaration_form = (
            ClaimSubmissionDeclarationForm(
                member_claim=False
            )
        )

    # ==========================================================
    # POST
    # ==========================================================

    else:

        # ------------------------------------------------------
        # Determine claim type directly from POST.
        # ------------------------------------------------------

        cause_type = (
            request.POST.get(
                "cause_type"
            )
        )

        member_claim = (
            cause_type
            == Claim.CLAIM_CAUSER_MEMBER
        )

        # ------------------------------------------------------
        # Selected member.
        # ------------------------------------------------------

        member_id = (
            request.POST.get(
                "selected_member_id"
            )
        )

        if member_id:

            selected_member = (
                Member.objects
                .filter(
                    id=member_id,
                    status="active",
                )
                .first()
            )

        # ------------------------------------------------------
        # Claim form.
        # ------------------------------------------------------

        form = ClaimForm(
            request.POST,
            request.FILES,
            user=request.user,
            selected_member=selected_member,
        )

        # ------------------------------------------------------
        # Bank details.
        # ------------------------------------------------------

        bank_form = ClaimBankDetailsForm(
            request.POST
        )

        # ------------------------------------------------------
        # Declaration.
        #
        # IMPORTANT:
        # It receives member_claim BEFORE is_valid() is called.
        # ------------------------------------------------------

        declaration_form = (
            ClaimSubmissionDeclarationForm(
                request.POST,
                member_claim=member_claim,
            )
        )

        # ======================================================
        # VALIDATE CLAIM FORM
        # ======================================================

        claim_valid = form.is_valid()

        # ======================================================
        # CLAIM TYPE / MEMBER VALIDATION
        # ======================================================

        if claim_valid:

            cause_type = (
                form.cleaned_data.get(
                    "cause_type"
                )
            )

            dependant = (
                form.cleaned_data.get(
                    "causer_dependant"
                )
            )

        else:

            dependant = None

        # ======================================================
        # MEMBER CAUSER
        # ======================================================

        if (
            cause_type
            == Claim.CLAIM_CAUSER_MEMBER
        ):

            if not selected_member:

                form.add_error(
                    None,
                    (
                        "Please search for and select "
                        "an active member."
                    )
                )

            if dependant:

                form.add_error(
                    "causer_dependant",
                    (
                        "A member claim cannot have "
                        "a dependant selected."
                    )
                )

            # --------------------------------------------------
            # Get next of kin.
            # --------------------------------------------------

            if selected_member:

                # --------------------------------------------------
                # PREVENT A SECOND MEMBER CLAIM
                # --------------------------------------------------
                # A member cannot be selected for a new MEMBER-type
                # claim when they already have a claim in any of the
                # following active/completed claim states:
                #
                #   Received, Open, Settled, Approved
                #
                # This is deliberately checked server-side as well as
                # in the search endpoint so a forged/stale POST cannot
                # bypass the member search restriction.
                # --------------------------------------------------

                existing_member_claim = (
                    Claim.objects
                    .filter(
                        member=selected_member,
                        status__in=[
                            Claim.STATUS_RECEIVED,
                            Claim.STATUS_OPEN,
                            Claim.STATUS_SETTLED,
                            Claim.STATUS_APPROVED,
                        ],
                    )
                    .exists()
                )

                if existing_member_claim:

                    form.add_error(
                        None,
                        (
                            "The selected member already has a claim "
                            "with a status of Received, Open, Settled, "
                            "or Approved. A new member claim cannot be "
                            "created for this member."
                        ),
                    )

                try:

                    next_of_kin = (
                        selected_member.next_of_kin
                    )

                except NextOfKin.DoesNotExist:

                    next_of_kin = None

                if not next_of_kin:

                    form.add_error(
                        None,
                        (
                            "The selected member does not "
                            "have next of kin details."
                        )
                    )

        # ======================================================
        # DEPENDANT CAUSER
        # ======================================================

        elif (
            cause_type
            == Claim.CLAIM_CAUSER_DEPENDANT
        ):

            if not dependant:

                form.add_error(
                    "causer_dependant",
                    (
                        "Please select an active dependant."
                    )
                )

            elif (
                dependant.member_id
                != admin_member.id
            ):

                form.add_error(
                    "causer_dependant",
                    (
                        "You can only create a dependant "
                        "claim for one of your own "
                        "dependants."
                    )
                )

            elif not admin_member.can_make_claim:

                form.add_error(
                    "causer_dependant",
                    (
                        "You cannot create a dependant claim yet. "
                        "Your 180-day active membership cooling-off "
                        "period has not been completed."
                    )
                )

        # ======================================================
        # INVALID CLAIM TYPE
        # ======================================================

        else:

            form.add_error(
                "cause_type",
                "Please select a valid claim type."
            )

        # ======================================================
        # ADDITIONAL FORM VALIDATION
        # ======================================================

        bank_valid = bank_form.is_valid()

        declaration_valid = (
            declaration_form.is_valid()
        )

        forms_valid = (
            not form.errors
            and bank_valid
            and declaration_valid
        )

        # ======================================================
        # SAVE
        # ======================================================

        if forms_valid:

            try:

                with transaction.atomic():

                    # ==========================================
                    # CLAIM
                    # ==========================================

                    claim = form.save(
                        commit=False
                    )

                    # ==========================================
                    # MEMBER CAUSER
                    # ==========================================

                    if (
                        cause_type
                        == Claim.CLAIM_CAUSER_MEMBER
                    ):

                        claim.member = (
                            selected_member
                        )

                        claim.causer_dependant = None

                        claim.causer_full_name = (
                            f"{selected_member.first_name} "
                            f"{selected_member.surname}"
                        )

                        claim.claimer = (
                            next_of_kin.full_name()
                        )

                        claim.claimer_is_next_of_kin = (
                            True
                        )

                    # ==========================================
                    # DEPENDANT CAUSER
                    # ==========================================

                    else:

                        claim.member = (
                            dependant.member
                        )

                        claim.causer_dependant = (
                            dependant
                        )

                        claim.causer_full_name = (
                            f"{dependant.first_name} "
                            f"{dependant.surname}"
                        )

                        claim.claimer = (
                            f"{dependant.member.first_name} "
                            f"{dependant.member.surname}"
                        )

                        claim.claimer_is_next_of_kin = (
                            False
                        )

                    # ==========================================
                    # ADMIN AUDIT
                    # ==========================================

                    claim.created_by = (
                        request.user
                    )

                    claim.full_clean()

                    claim.save()

                    # ==========================================
                    # BANK DETAILS
                    # ==========================================

                    bank_details = (
                        bank_form.save(
                            commit=False
                        )
                    )

                    bank_details.claim = (
                        claim
                    )

                    bank_details.full_clean()

                    bank_details.save()

                    # ==========================================
                    # DECLARATION
                    # ==========================================

                    declaration = (
                        declaration_form.save(
                            commit=False
                        )
                    )

                    declaration.claim = (
                        claim
                    )

                    # ------------------------------------------
                    # Force false for dependant claims.
                    # ------------------------------------------

                    if (
                        cause_type
                        != Claim.CLAIM_CAUSER_MEMBER
                    ):

                        declaration.next_of_kin_contacted = (
                            False
                        )

                    declaration.full_clean()

                    declaration.save()

                    # ==========================================
                    # DOCUMENTS
                    # ==========================================

                    files = request.FILES.getlist(
                        "documents"
                    )

                    titles = request.POST.getlist(
                        "doc_title"
                    )

                    descriptions = request.POST.getlist(
                        "doc_description"
                    )

                    for i, uploaded_file in enumerate(
                        files
                    ):

                        if not uploaded_file:
                            continue

                        title = (
                            titles[i].strip()
                            if (
                                i < len(titles)
                                and titles[i].strip()
                            )
                            else (
                                "Claim Supporting "
                                f"Document {i + 1}"
                            )
                        )

                        description = (
                            descriptions[i].strip()
                            if (
                                i < len(descriptions)
                                and descriptions[i].strip()
                            )
                            else ""
                        )

                        MemberDocument.objects.create(
                            member=claim.member,
                            dependant=(
                                claim.causer_dependant
                                if claim.causer_dependant
                                else None
                            ),
                            claim=claim,
                            title=title,
                            description=description,
                            file=uploaded_file,
                        )

                messages.success(
                    request,
                    "Claim created successfully."
                )

                return redirect(
                    "members_admin:dashboard"
                )

            except Exception as exc:

                messages.error(
                    request,
                    (
                        "The claim could not be submitted. "
                        f"{exc}"
                    )
                )

    # ==========================================================
    # RENDER
    # ==========================================================

    return render(
        request,
        "members/admin/claims/admin_create_claim.html",
        {
            "form": form,
            "bank_form": bank_form,
            "declaration_form": declaration_form,
            "selected_member": selected_member,
            "next_of_kin": next_of_kin,
            "admin_can_make_dependant_claim": admin_member.can_make_claim,
            "admin_claim_eligibility_date": admin_member.claim_eligibility_date,
            "admin_days_until_claim": admin_member.days_until_claim,
        },
    )

# ==============================================================
# SEARCH ACTIVE MEMBERS
# ==============================================================

def search_members(request):
    """
    Search ACTIVE members for admin claim creation.

    Existing response fields are preserved:

    - id
    - name
    - uid
    - email
    - phone

    Additional field:

    - next_of_kin
    """

    q = request.GET.get(
        "q",
        ""
    ).strip()

    if not q:

        return JsonResponse(
            [],
            safe=False
        )

    # ----------------------------------------------------------
    # MEMBER CLAIM ELIGIBILITY
    # ----------------------------------------------------------
    # Only ACTIVE members who do not already have a claim in one
    # of the protected statuses may be returned for a MEMBER-type
    # claim.
    #
    # Rejected claims are intentionally not included here, so a
    # member whose previous claim was rejected can be searched and
    # selected for a new member claim.
    # ----------------------------------------------------------

    protected_claim_statuses = [
        Claim.STATUS_RECEIVED,
        Claim.STATUS_OPEN,
        Claim.STATUS_SETTLED,
        Claim.STATUS_APPROVED,
    ]

    members = (
        Member.objects
        .filter(
            status="active"
        )
        .filter(
            Q(first_name__icontains=q)
            | Q(surname__icontains=q)
            | Q(member_uid__icontains=q)
            | Q(user__email__icontains=q)
            | Q(phone__icontains=q)
        )
        .exclude(
            id__in=(
                Claim.objects
                .filter(
                    status__in=protected_claim_statuses
                )
                .values("member_id")
            )
        )
        .select_related(
            "user",
            "next_of_kin",
        )
        .order_by(
            "first_name"
        )[:10]
    )

    data = []

    for member in members:

        nok = getattr(
            member,
            "next_of_kin",
            None
        )

        nok_data = None

        if nok:

            nok_data = {
                "name": nok.full_name(),
                "phone": nok.phone or "",
                "email": nok.email or "",
                "relationship": (
                    nok.relationship or ""
                ),
            }

        data.append(
            {
                "id": member.id,

                "name": (
                    f"{member.first_name} "
                    f"{member.surname}"
                ),

                "uid": (
                    member.member_uid
                    if member.member_uid
                    else "N/A"
                ),

                "email": (
                    member.user.email
                    if member.user
                    and member.user.email
                    else ""
                ),

                "phone": getattr(
                    member,
                    "phone",
                    None
                ),

                "next_of_kin": nok_data,
            }
        )

    return JsonResponse(
        data,
        safe=False
    )
