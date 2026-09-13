from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from backend.members.decorators import member_required
from backend.members.models import Claim, Member, MemberDocument
from backend.members.forms import ClaimForm, ClaimBankDetailsForm, ClaimSubmissionDeclarationForm
from backend.members.services.document_files import (
    DocumentUploadValidationError,
    generate_document_thumbnail,
    prepare_document_file,
)
from django.db import transaction

# ======================================================
# ✅ HELPER: ACTIVE MEMBER CHECK (REUSABLE)
# ======================================================
def ensure_active_member(request):
    """
    Reusable guard to ensure only ACTIVE members proceed
    Returns:
        - member (if valid)
        - None (if blocked)
    """

    member = request.user.member

    if member.status != "active":
        messages.error(request, "Your account is not active.")
        return None

    return member


def create_claim_entry(request):
    """
    FINAL SAFE ROUTER

    Cannot loop because:
    - Targets are DIFFERENT URLs
    """

    if request.user.is_staff:
        return redirect("/admin-panel/claims/create-admin/")

    return redirect("/claims/create/member/")

@login_required
@member_required
def member_create_claim(request):
    """
    Allow a member to create a claim for one of their own
    eligible dependants.

    Member claim rules:

    - A member can only create a dependant claim.
    - The member cannot choose the claim type.
    - The dependant must belong to the signed-in member.
    - ClaimForm restricts the dependant queryset accordingly.
    - The signed-in member is the claimer.
    - The selected dependant is the causer.
    - Bank details are captured for this claim.
    - The member must complete the submission declaration.

    A successful submission redirects to the newly created
    member claim detail page so the success message is visible
    and the member can immediately confirm the claim was sent.
    """

    # ==========================================================
    # MEMBER
    # ==========================================================

    try:

        member = request.user.member

    except AttributeError:

        messages.error(
            request,
            (
                "You must have a member profile "
                "to create a claim."
            ),
        )

        return redirect(
            "members:dashboard"
        )

    # ==========================================================
    # ACTIVE MEMBER CHECK
    # ==========================================================

    if member.status != "active":

        messages.error(
            request,
            "Only active members can create claims.",
        )

        return redirect(
            "members:dashboard"
        )

    # ==========================================================
    # POST
    # ==========================================================

    if request.method == "POST":

        form = ClaimForm(
            request.POST,
            request.FILES,
            user=request.user,
        )

        bank_details_form = (
            ClaimBankDetailsForm(
                request.POST,
            )
        )

        declaration_form = (
            ClaimSubmissionDeclarationForm(
                request.POST,
            )
        )

        # ======================================================
        # VALIDATE ALL FORMS
        # ======================================================

        if (
            form.is_valid()
            and bank_details_form.is_valid()
            and declaration_form.is_valid()
        ):

            try:

                with transaction.atomic():

                    # --------------------------------------------------
                    # CLAIM
                    # --------------------------------------------------

                    claim = form.save(
                        commit=False
                    )

                    dependant = (
                        form.cleaned_data.get(
                            "causer_dependant"
                        )
                    )

                    # --------------------------------------------------
                    # MEMBER OWNERSHIP
                    # --------------------------------------------------

                    claim.member = member

                    claim.created_by = (
                        request.user
                    )

                    # Member portal currently permits only
                    # dependant-causer claims.
                    claim.cause_type = (
                        Claim.CLAIM_CAUSER_DEPENDANT
                    )

                    claim.causer_dependant = (
                        dependant
                    )

                    claim.causer_full_name = (
                        f"{dependant.first_name} "
                        f"{dependant.surname}"
                    )

                    claim.claimer = (
                        f"{member.first_name} "
                        f"{member.surname}"
                    )

                    claim.claimer_is_next_of_kin = (
                        False
                    )

                    claim.save()

                    # --------------------------------------------------
                    # BANK DETAILS
                    # --------------------------------------------------

                    bank_details = (
                        bank_details_form.save(
                            commit=False
                        )
                    )

                    bank_details.claim = claim

                    bank_details.save()

                    # --------------------------------------------------
                    # SUBMISSION DECLARATION
                    # --------------------------------------------------

                    declaration = (
                        declaration_form.save(
                            commit=False
                        )
                    )

                    declaration.claim = claim

                    declaration.save()

                    # ==================================================
                    # SUPPORTING DOCUMENTS
                    # ==================================================

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

                        original_filename = (
                            uploaded_file.name
                        )

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

                        # --------------------------------------------------
                        # CENTRAL VALIDATION + PROCESSING
                        # --------------------------------------------------

                        processed_file = (
                            prepare_document_file(
                                uploaded_file=uploaded_file,
                                member=member,
                                document_title=title,
                            )
                        )

                        # --------------------------------------------------
                        # CREATE DOCUMENT
                        # --------------------------------------------------

                        document = MemberDocument(
                            member=member,
                            dependant=dependant,
                            claim=claim,
                            title=title,
                            description=description,
                            file=processed_file,
                            original_filename=original_filename,
                        )

                        document.full_clean()
                        document.save()

                        # --------------------------------------------------
                        # THUMBNAIL
                        # --------------------------------------------------

                        generate_document_thumbnail(
                            document
                        )

            except DocumentUploadValidationError as exc:

                messages.error(
                    request,
                    (
                        "The claim could not be submitted. "
                        f"{exc}"
                    ),
                )

            except Exception as exc:

                messages.error(
                    request,
                    (
                        "The claim could not be submitted. "
                        f"{exc}"
                    ),
                )

            else:

                # ==================================================
                # SUCCESS
                # ==================================================

                messages.success(
                    request,
                    (
                        "Your claim has been submitted "
                        "successfully."
                    ),
                )

                # --------------------------------------------------
                # IMPORTANT:
                # ``members:claims`` does not exist.
                #
                # Use the existing member claim-detail URL and
                # pass the newly created claim primary key.
                # --------------------------------------------------

                return redirect(
                    "members:member_claims",
                    pk=claim.pk,
                )

    # ==========================================================
    # GET
    # ==========================================================

    else:

        form = ClaimForm(
            user=request.user,
        )

        bank_details_form = (
            ClaimBankDetailsForm()
        )

        declaration_form = (
            ClaimSubmissionDeclarationForm()
        )

    # ==========================================================
    # RENDER
    # ==========================================================

    return render(
        request,
        "members/claims/members_create_claim.html",
        {
            "form": form,
            "bank_details_form": bank_details_form,
            "declaration_form": declaration_form,
        },
    )

@login_required
@member_required
def members_claims_list(request):

    member = request.user.member

    claims = (
        Claim.objects
        .filter(member=member)
        .order_by("-created_at")
    )

    return render(
        request,
        "members/claims/members_claims_list.html",
        {
            "claims": claims
        }
    )


@login_required
@member_required
def member_claims_list(request):

    member = request.user.member

    claims = Claim.objects.filter(
        member=member
    ).order_by("-created_at")

    return render(
        request,
        "members/claims/members_claims_list.html",
        {
            "claims": claims
        }
    )

    
@login_required
@member_required
def members_claim_detail(request, pk):
    """
    Member claim detail

    FIXES:
    ✔ correct context dictionary
    ✔ prevents set error
    ✔ ensures member ownership
    """

    member = request.user.member

    claim = get_object_or_404(
        Claim,
        pk=pk,
        member=member  # security
    )

    return render(
        request,
        "members/claims/members_claims_detail.html",
        {
            "claim": claim
        },
    )
