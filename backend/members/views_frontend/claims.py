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

@login_required
def members_create_claimOnHold(request):
    
    member = ensure_active_member(request)
    if not member:
        return redirect("members:dashboard")
    
    if request.method == "POST":
        form = ClaimForm(
            request.POST,
            request.FILES,
            member=member,   # 🔴 IMPORTANT — passes member to form
        )

        if form.is_valid():
            claim = form.save(commit=False)
            claim.member = member
            claim.status = Claim.STATUS_RECEIVED
            claim.save()

            messages.success(request, "Claim submitted successfully.")
            return redirect("members:dashboard")

        else:
            messages.error(request, "Please correct the errors below.")

    else:
        form = ClaimForm(member=member)  # 🔴 IMPORTANT

    return render(
        request,
        "members/claims/members_create_claim.html",
        {
            "form": form,
            "member": member,
        },
    )


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

    - Only ACTIVE members allowed
    - Enforces dependant-only claim
    - Handles multi-document upload
    """

    member = getattr(request.user, "member", None)

    # 🔒 ACCESS CONTROL
    if not member or member.status != "active":
        messages.error(
            request,
            "Your account does not have active membership. "
            "Wait to be activated or contact KRO"
        )
        return redirect("members:dashboard")

    if request.method == "POST":
        form = ClaimForm(request.POST, request.FILES, user=request.user)

        if form.is_valid():
            claim = form.save(commit=False)

            dependant = claim.causer_dependant

            claim.cause_type = "dependant"
            claim.member = member
            claim.created_by = request.user
            claim.causer_full_name = f"{dependant.first_name} {dependant.surname}"
            claim.claimer = f"{member.first_name} {member.surname}"

            claim.save()

            # ============================
            # DOCUMENTS
            # ============================
            files = request.FILES.getlist("documents")
            titles = request.POST.getlist("doc_title")
            descriptions = request.POST.getlist("doc_description")

            for i, file in enumerate(files):
                MemberDocument.objects.create(
                    member=member,
                    dependant=dependant,
                    claim=claim,
                    title=titles[i] if i < len(titles) else "Untitled",
                    description=descriptions[i] if i < len(descriptions) else "",
                    file=file,
                )

            messages.success(request, "Claim submitted successfully.")
            return redirect("members:dashboard")

    else:
        form = ClaimForm(user=request.user)

    return render(request, "members/claims/members_create_claim.html", {
        "form": form
    })

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
