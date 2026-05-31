from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
#from backend.members.services.claim_service import approve_claim, ClaimService
from backend.members.forms import ClaimForm
from backend.members.services.claim_service import ClaimService
from backend.members.models import Claim, Member, MemberDocument, Payment, PaymentRequest
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count
from backend.members.views_admin import admin_required


@login_required
def approve_claim_view(request, claim_uid):
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
    claim = get_object_or_404(Claim, uid=claim_uid)

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
def approve_claim(request, claim_id):

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
def admin_claim_detail(request, claim_uid):
        claim = get_object_or_404(Claim, uid=claim_uid)
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
    
@admin_required
def admin_create_claimOnHold(request):
    if request.method == "POST":
        member_id = request.POST.get("member_id")
        amount = request.POST.get("amount")
        description = request.POST.get("description")

        Claim.objects.create(
            member_id=member_id,
            amount=amount,
            description=description,
            status="open",
        )

        return redirect("members_admin:claims")

    members = Member.objects.all()

    return render(
        request, 
        "members/admin/admin_create_claim.html",
        {"members": members},
    )

def admin_create_claim(request):
    """
    ADMIN CLAIM VIEW

    ✔ Correct view for creating claims
    ✔ Supports member + dependant claims
    ✔ NOT linked to payment creation
    """

    admin_member = getattr(request.user, "member", None)

    # ---------------------------------------
    # ACCESS CONTROL
    # ---------------------------------------
    if not admin_member or admin_member.status != "active":
        messages.error(
            request,
            "Your account does not have active membership."
        )
        return redirect("members_admin:dashboard")

    selected_member = None

    if request.method == "POST":

        member_id = request.POST.get("selected_member_id")

        if member_id:
            selected_member = Member.objects.filter(
                id=member_id,
                status="active"
            ).first()

        form = ClaimForm(
            request.POST,
            request.FILES,
            user=request.user,
            selected_member=selected_member
        )

        if form.is_valid():

            claim = form.save(commit=False)

            cause_type = request.POST.get("cause_type")

            # ---------------------------------------
            # MEMBER / DEPENDANT LOGIC
            # ---------------------------------------
            if cause_type == "member":
                claim.member = selected_member
                claim.causer_full_name = f"{selected_member.first_name} {selected_member.surname}"
            else:
                dependant = claim.causer_dependant
                claim.member = dependant.member
                claim.causer_full_name = f"{dependant.first_name} {dependant.surname}"

            claim.claimer = request.user.get_full_name()
            claim.created_by = request.user

            claim.save()

            # ---------------------------------------
            # DOCUMENTS
            # ---------------------------------------
            files = request.FILES.getlist("documents")
            titles = request.POST.getlist("doc_title")
            descriptions = request.POST.getlist("doc_description")

            for i, file in enumerate(files):
                MemberDocument.objects.create(
                    member=claim.member,
                    dependant=claim.causer_dependant if claim.causer_dependant else None,
                    claim=claim,
                    title=titles[i] if i < len(titles) else "Untitled",
                    description=descriptions[i] if i < len(descriptions) else "",
                    file=file,
                )

            messages.success(request, "Claim created successfully.")
            return redirect("members_admin:dashboard")

    else:
        form = ClaimForm(user=request.user)

    return render(
        request,
        "members/admin/claims/admin_create_claim.html",
        {
            "form": form
        }
    )

# ============================
# MEMBER SEARCH (SATATUS = ACTIVE ONLY)
# ============================

def search_members(request):
    """
    🔍 SEARCH MEMBERS (FINAL FIX)

    - Searches:
        ✔ first_name
        ✔ surname
        ✔ member_uid
    - Only ACTIVE members
    - Partial + case-insensitive
    """

    q = request.GET.get("q", "").strip()

    if not q:
        return JsonResponse([], safe=False)

    members = Member.objects.filter(
        status="active"
    ).filter(
        Q(first_name__icontains=q) |
        Q(surname__icontains=q) |
        Q(member_uid__icontains=q) |
        Q(user__email__icontains=q) |
        Q(phone__icontains=q)
    ).order_by("first_name")[:10]

    data = []

    for m in members:
        data.append({
            "id": m.id,
            "name": f"{m.first_name} {m.surname}",
            # ✅ SAFE FALLBACK
            "uid": m.member_uid if m.member_uid else "N/A",
            "email": m.user.email if m.user and m.user.email else "",
            "phone": getattr(m, "phone", None),
        })

    return JsonResponse(data, safe=False)
    
    

