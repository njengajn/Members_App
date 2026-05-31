from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages

from backend.members.decorators import member_required
from backend.members.forms import DependantForm
from django.contrib.auth.decorators import login_required
from backend.members.models import Member, Dependant, MemberDocument

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
        messages.error(request, "Your account is not active. Wait to be activated or contact KRO")
        return None

    return member

@login_required
@member_required
def members_dependants_list(request):
    """
    List dependants for member

    ✔ FIXED:
    - correct member initialization
    - safe expiry check
    """

    # ✅ ALWAYS GET MEMBER FIRST
    member = ensure_active_member(request)

    if not member:
        return redirect("members:dashboard")

    member.check_can_edit_expiry()

    dependants = Dependant.objects.filter(member=member)

    return render(
        request,
        "members/dependants/members_dependants_list.html",
        {
            "member": member,
            "dependants": dependants,
        }
    )

@login_required
@member_required
def members_add_dependant(request):
    
    try:
       member = request.user.member
    except Member.DoesNotExist:
       messages.warning(request, "You are not registered as a member yet.")
       return redirect("members:member_dashboard")
   

    # 🔥 RESTRICT EDITING
    if not member.can_edit:
        messages.error(request, "Editing is disabled for your account.")
        return redirect("members:dependants")
    
    member.check_can_edit_expiry()

    form = DependantForm(request.POST or None, request.FILES or None)

    if request.method == "POST":
        if form.is_valid():
            dependant = form.save(commit=False)
            dependant.member = member
            dependant.status = "pending"
            dependant.save()

            # SAVE DOCUMENT
            doc_file = form.cleaned_data.get("document_file")
            doc_title = form.cleaned_data.get("document_title")

            if doc_file:
                MemberDocument.objects.create(
                    member=member,
                    dependant=dependant,
                    title=doc_title or "Dependant Document",
                    file=doc_file,
                )

            messages.success(request, "Dependant added.")
            return redirect("members:dependants")

    return render(request, "members/dependants/members_add_dependants.html", {
        "form": form
    })


@login_required
@member_required
def members_edit_dependant(request, pk):
    member = request.user.member
    
    member.check_can_edit_expiry()

    if not member.can_edit:
        messages.error(request, "Editing is disabled.")
        return redirect("members:dependants")
    
    if not member.can_edit:
        messages.error(request, "You are not allowed to modify dependants.")
        return redirect("members:dependants")

    dependant = get_object_or_404(Dependant, pk=pk, member=member)

    form = DependantForm(request.POST or None, instance=dependant)

    if form.is_valid():
        dep = form.save(commit=False)
        dep.status = "pending"  # 🔁 reset approval
        dep.save()

        messages.success(request, "Updated.")
        return redirect("members:dependants")

    return render(request, "members/dependants/members_dependants_form.html", {
        "form": form
    })


@login_required
@member_required
def members_delete_dependant(request, pk):
    member = request.user.member

    if not member.can_edit:
        messages.error(request, "Editing is disabled.")
        return redirect("members:dependants")

    dependant = get_object_or_404(Dependant, pk=pk, member=member)
    dependant.delete()

    messages.success(request, "Deleted.")
    return redirect("members:dependants")


@login_required
@member_required
def members_dependant_detail(request, pk):
    dependant = get_object_or_404(
        Dependant,
        pk=pk,
        member=request.user.member
    )

    return render(
        request,
        "members/dependants/members_dependants_detail.html",
        {"dependant": dependant}
    )
