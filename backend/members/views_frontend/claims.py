from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from backend.members.decorators import member_required
from backend.members.models import Claim, Member, MemberDocument
from backend.members.forms import ClaimForm

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
    MEMBER CLAIM VIEW

    Business Rules
    --------------------------------------------------------------------
    1. User must have a Member record.
    2. Member must be ACTIVE.
    3. Member must have completed the 180-day cooling-off period.
    4. Claims are submitted only for registered dependants.
    5. Multiple supporting documents may be uploaded.
    """

    # ------------------------------------------------------------------
    # Get the logged-in member
    # ------------------------------------------------------------------
    member = getattr(request.user, "member", None)

    # ------------------------------------------------------------------
    # Safety check
    # ------------------------------------------------------------------
    if not member:
        messages.error(
            request,
            "Member account not found."
        )
        return redirect("members:dashboard")

    # ------------------------------------------------------------------
    # Only ACTIVE members can submit claims
    # ------------------------------------------------------------------
    if member.status != Member.STATUS_ACTIVE:
        messages.error(
            request,
            (
                "Your membership is not yet active. "
                "Please wait for approval or contact KRO."
            )
        )
        return redirect("members:dashboard")

    # ------------------------------------------------------------------
    # Enforce 180-day cooling-off period
    # Uses Member.can_make_claim property.
    # ------------------------------------------------------------------
    if not member.can_make_claim:
        messages.error(
            request,
            (
                "Claims can only be submitted after "
                "180 days of active membership."
            )
        )
        return redirect("members:dashboard")

    # ------------------------------------------------------------------
    # Handle form submission
    # ------------------------------------------------------------------
    if request.method == "POST":

        form = ClaimForm(
            request.POST,
            request.FILES,
            user=request.user,
        )

        if form.is_valid():

            claim = form.save(commit=False)

            dependant = claim.causer_dependant

            # ----------------------------------------------------------
            # Populate claim fields automatically
            # ----------------------------------------------------------
            claim.member = member
            claim.created_by = request.user

            # Claims are currently dependant-only
            #claim.cause_type = "dependant" ***hard coding
            claim.cause_type = Claim.CLAIM_CAUSER_DEPENDANT

            claim.causer_full_name = (
                f"{dependant.first_name} "
                f"{dependant.surname}"
            )

            claim.claimer = (
                f"{member.first_name} "
                f"{member.surname}"
            )

            claim.save()

            # ----------------------------------------------------------
            # Save uploaded supporting documents
            # ----------------------------------------------------------
            files = request.FILES.getlist("documents")
            titles = request.POST.getlist("doc_title")
            descriptions = request.POST.getlist("doc_description")

            for i, file in enumerate(files):

                MemberDocument.objects.create(
                    member=member,
                    dependant=dependant,
                    claim=claim,
                    title=(
                        titles[i]
                        if i < len(titles)
                        else "Untitled"
                    ),
                    description=(
                        descriptions[i]
                        if i < len(descriptions)
                        else ""
                    ),
                    file=file,
                )

            messages.success(
                request,
                "Claim submitted successfully."
            )

            return redirect("members:dashboard")

    # ------------------------------------------------------------------
    # Display empty form
    # ------------------------------------------------------------------
    else:

        form = ClaimForm(user=request.user)

    # ------------------------------------------------------------------
    # Render page
    # ------------------------------------------------------------------
    return render(
        request,
        "members/claims/members_create_claim.html",
        {
            "form": form,
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
            "claim": claim  # ✅ CORRECT DICT
        },
    )
