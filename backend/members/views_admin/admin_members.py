from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages

from backend.core import settings
from backend.members import models
from backend.members.models import (
    Member,
    Dependant,
    NextOfKin,
    AuditLog,
    Payment,
    Claim,
)
from .admin_auth import admin_required
from django.core.mail import send_mail
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer
)

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from backend.members.models import MembershipStatusHistory



# ======================================================
# HELPERS
# ======================================================

def is_admin(user):
    return user.is_authenticated and user.is_staff


# ======================================================
# MEMBERS LIST (SEARCH FIXED)
# ======================================================

@user_passes_test(is_admin)
def members_list(request):
    """
    Admin member list with search.
    FIX:
    - full_name is NOT a DB field → replaced with first_name/surname
    - Added UID search support
    """
    search = request.GET.get("search", "")

    members = Member.objects.all()

    if search:
        members = members.filter(
            models.Q(member_uid__icontains=search) |
            models.Q(first_name__icontains=search) |
            models.Q(surname__icontains=search)            
        )

    return render(
        request,
        "members/admin/members/admin_members_list.html",
        {"members": members}
    )


# ======================================================
# MEMBER DETAIL
# ======================================================

@user_passes_test(is_admin)
def member_detail(request, member_id):
    member = get_object_or_404(Member, pk=member_id)
    return render(
        request,
        "members/admin/members/admin_members_detail.html",
        {"member": member}
    )


# ======================================================
# ADMIN MEMBERS (LEGACY VIEW)
# ======================================================

@admin_required
def admin_members(request):
    members = Member.objects.all()
    return render(request, "members/admin/members.html", {"members": members})


# ======================================================
# EDIT MEMBER
# ======================================================

@admin_required
def edit_member(request, pk):
    """
    WARNING FIX:
    - Do NOT manually assign UID here
    - Just update status → model handles UID
    """
    member = get_object_or_404(Member, pk=pk)

    if request.method == "POST":
        member.status = request.POST.get("status")
        member.save()  # ✅ UID handled in model

        return redirect("members:admin_members")

    return render(
        request,
        "members/admin/edit_member.html",
        {"member": member}
    )


# ======================================================
# ADMIN MEMBERS LIST
# ======================================================

@admin_required
def admin_members_list(request):
    members = Member.objects.all().order_by("-id")

    return render(
        request,
        "members/admin/members/admin_members_list.html",
        {"members": members},
    )


# ======================================================
# UPDATE MEMBER STATUS (CRITICAL FIX)
# ======================================================

@admin_required
def update_member_status(request, member_id):
    """
    FIXES:
    - Removed UID generation from here
    - Model handles UID when status → ACTIVE
    """

    member = get_object_or_404(Member, id=member_id)

    if request.method == "POST":
        new_status = request.POST.get("status")

        if new_status in ["pending", "approved", "active", "retired"]:
            member.status = new_status
            member.save()  # ✅ UID auto handled

            # -----------------------------------------
            # AUTO DEPENDANT STATUS SYNC
            # -----------------------------------------
            if new_status == "active":
                member.dependants.update(status="active")
                member.can_edit = False
            elif new_status == "retired":
                member.dependants.update(status="retired")
                member.can_edit = False

            member.save()

            messages.success(request, "Member status updated successfully.")
        else:
            messages.error(request, "Invalid status selected.")

    return redirect(
        "members_admin:admin_member_detail",
        member_id=member.id,
    )


# ======================================================
# ADMIN MEMBER DETAIL
# ======================================================

@admin_required
def admin_member_detail(request, member_id):
    member = get_object_or_404(Member, id=member_id)

    dependants = member.dependants.all().order_by("status", "first_name")
    next_of_kin = NextOfKin.objects.filter(member=member).first()

    claims = Claim.objects.filter(member=member).order_by("-created_at")
    payments = Payment.objects.filter(member=member).order_by("-approved_at")

    context = {
        "member": member,
        "dependants": dependants,
        "next_of_kin": next_of_kin,
        "claims": claims,
        "payments": payments,
    }

    return render(
        request,
        "members/admin/members/admin_members_detail.html",
        context,
    )


# ======================================================
# APPROVE MEMBER (CRITICAL FIX)
# ======================================================

@staff_member_required
def approve_member(request, pk):
    """
    FIX:
    ❌ Removed manual UID generation
    ✅ Model now controls UID

    Flow:
    pending → active → UID auto-generated
    """

    member = get_object_or_404(Member, pk=pk)

    if member.status == Member.STATUS_ACTIVE:
        messages.warning(request, "Member already active.")
        return redirect("admin_members")

    member.status = Member.STATUS_ACTIVE
    member.can_edit = False
    member.save()  # ✅ UID generated here

    messages.success(request, "Member approved successfully.")

    return redirect("admin_members")


# ======================================================
# REJECT MEMBER
# ======================================================

@staff_member_required
def reject_member(request, pk):
    member = get_object_or_404(Member, pk=pk)

    # ⚠️ Ensure STATUS_REJECTED exists in model if used
    member.status = Member.STATUS_RETIRED
    member.can_edit = False
    member.save()

    messages.warning(request, "Member rejected.")

    return redirect("admin_members")


# ======================================================
# TOGGLE EDIT PERMISSION
# ======================================================

@staff_member_required
def toggle_member_edit(request, pk):
    member = get_object_or_404(Member, pk=pk)

    member.can_edit = not member.can_edit
    member.save()

    messages.info(request, f"Edit permission set to {member.can_edit}")

    return redirect("admin_members")


# ======================================================
# MEMBER CARD
# ======================================================

@staff_member_required
def member_card_view(request, pk):
    member = get_object_or_404(Member, pk=pk)

    return render(
        request,
        "admin/member_card.html",
        {"member": member}
    )


# ======================================================
# DEPENDANT STATUS
# ======================================================

@admin_required
def update_dependant_status(request, dependant_id):
    dependant = get_object_or_404(Dependant, id=dependant_id)

    if request.method == "POST":
        new_status = request.POST.get("status")

        if new_status in ["active", "inactive"]:
            dependant.status = new_status
            dependant.save()
            messages.success(request, "Dependant status updated.")
        else:
            messages.error(request, "Invalid status.")

    return redirect(
        "members_admin:admin_member_detail",
        member_id=dependant.member.id,
    )


# ======================================================
# INLINE DEPENDANT UPDATE
# ======================================================

@admin_required
def update_dependant_inline(request, dependant_id):
    """
    Inline dependant update (FIXED — matches URL)
    """

    dependant = get_object_or_404(Dependant, id=dependant_id)

    if request.method == "POST":

        # -----------------------------------
        # BLOCK IF MEMBER RETIRED
        # -----------------------------------
        if dependant.member.status == "retired":
            messages.error(request, "Cannot modify dependant of retired member.")
            return redirect(
                "members_admin:admin_member_detail",
                member_id=dependant.member.id,
            )

        # -----------------------------------
        # UPDATE FIELDS (SAFE)
        # -----------------------------------
        dependant.status = request.POST.get("status", dependant.status)

        # -----------------------------------
        # SAVE
        # -----------------------------------
        dependant.save(update_fields=["status"])

        messages.success(request, "Dependant status updated successfully.")

    return redirect(
        "members_admin:admin_member_detail",
        member_id=dependant.member.id,
    )

# ======================================================
# NEXT OF KIN
# ======================================================

@admin_required
def edit_next_of_kin(request, member_id):
    member = get_object_or_404(Member, id=member_id)
    nok = getattr(member, "next_of_kin", None)

    if request.method == "POST":
        if not nok:
            nok = NextOfKin(member=member)

        nok.first_name = request.POST.get("first_name")
        nok.surname = request.POST.get("surname")
        nok.relationship = request.POST.get("relationship")
        nok.phone = request.POST.get("phone")
        nok.email = request.POST.get("email")
        nok.save()

        messages.success(request, "Next of Kin updated.")

        return redirect(
            "members_admin:admin_member_detail",
            member_id=member.id,
        )

    return render(
        request,
        "members/admin/members/admin_edit_nok.html",
        {
            "member": member,
            "nok": nok,
        },
    )


# ======================================================
# ACTIVITY LOG
# ======================================================

@admin_required
def admin_activity_log(request):
    logs = AuditLog.objects.select_related("admin", "target_member") \
        .order_by("-created_at")[:100]

    return render(
        request,
        "members/admin/admin_activity_log.html",
        {"logs": logs}
    )
    
@staff_member_required
def admin_members_dashboard(request):
    """
    Admin dashboard showing all members
    """

    members = Member.objects.select_related("user").order_by("-created_at")

    return render(request, "admin/members_dashboard.html", {
        "members": members
    })
    
from django.utils import timezone
from datetime import timedelta

@staff_member_required
def admin_update_member_permissions(request, member_id):

    member = get_object_or_404(Member, id=member_id)
    member.is_portal_access_enabled = "portal_access" in request.POST
    
    if request.method == "POST":

        # CRITICAL SAFETY CHECK - MEMBER/ADMIN SHOULD NOT CHANGE OWN STATUS.
        if request.user == member.user:
            messages.error(request, "You cannot modify your own account.")
            return redirect("members_admin:admin_member_detail", member_id=member.id)

        member.status = request.POST.get("status")

        #  SAFE CHECKBOX HANDLING
        can_edit_requested = "can_edit" in request.POST

        if can_edit_requested:
            member.enable_can_edit()

            #  NOTIFY USER - VIA EMAIL
            if member.user and member.user.email:
                send_mail(
                    subject="Dependants Editing Enabled",
                    message=(
                        "You have been granted permission to manage dependants. "
                        "This access will expire in 24 hours."
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[member.user.email],
                    fail_silently=True,
                )
        else:
            member.disable_can_edit()

        member.save()

        messages.success(request, "Member updated successfully.")

    return redirect("members_admin:admin_member_detail", member_id=member.id)

@staff_member_required
def dependant_detail(request, pk):
    dependant = get_object_or_404(Dependant, id=pk)

    return render(request,
        "members/admin/members/dependant_detail.html",
        {"dependant": dependant}
    )
    
@admin_required
def bulk_update_dependants(request, member_id):
    """
    Bulk update dependant status.

    ✔ Safe
    ✔ Respects lifecycle rules
    """

    member = get_object_or_404(Member, id=member_id)

    if request.method != "POST":
        return redirect("members_admin:admin_member_detail", member_id=member.id)

    selected_ids = request.POST.getlist("dependant_ids")
    new_status = request.POST.get("bulk_status")

    if not selected_ids:
        messages.warning(request, "No dependants selected.")
        return redirect("members_admin:admin_member_detail", member.id)

    if new_status not in ["active", "retired"]:
        messages.error(request, "Invalid status selected.")
        return redirect("members_admin:admin_member_detail", member.id)

    # -----------------------------------
    # RULE: member must be active to activate dependants
    # -----------------------------------
    if member.status == Member.STATUS_RETIRED and new_status == "active":
        messages.error(request, "Cannot activate dependants while member is retired.")
        return redirect("members_admin:admin_member_detail", member.id)

    dependants = Dependant.objects.filter(id__in=selected_ids, member=member)

    updated_count = dependants.update(status=new_status)

    messages.success(
        request,
        f"{updated_count} dependant(s) updated to {new_status}."
    )

    return redirect("members_admin:admin_member_detail", member.id)

# ======================================================
# EXPORT MEMBERS - EXCEL
# ======================================================

def export_members_excel(request):

    status = request.GET.get(
        "status",
        "active"
    )


    if status == "all":

        members = Member.objects.all()

    else:

        members = Member.objects.filter(
            status=status
        )


    response = HttpResponse(
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        )
    )


    response[
        "Content-Disposition"
    ] = (
        'attachment; filename="members_list.xlsx"'
    )


    workbook = Workbook()

    sheet = workbook.active

    sheet.title = "Members"


    # HEADER
    sheet.append([
        "Member UID",
        "Full Name",
        "Date Joined",
        "Status",
    ])


    # DATA
    for member in members:

        full_name = " ".join(
            filter(
                None,
                [
                    member.first_name,
                    member.middle_name,
                    member.surname,
                ],
            )
        )


        sheet.append([

            member.member_uid,

            full_name,

            member.joined_at.strftime(
                "%d %b %Y"
            )
            if member.joined_at
            else "",

            member.status.title(),

        ])


    # AUTO WIDTH
    for column in sheet.columns:

        max_length = 0

        column_letter = (
            column[0].column_letter
        )


        for cell in column:

            if cell.value:

                max_length = max(
                    max_length,
                    len(str(cell.value))
                )


        sheet.column_dimensions[
            column_letter
        ].width = max_length + 3


    workbook.save(response)


    return response

# ======================================================
# EXPORT MEMBERS - PDF
# ======================================================

def export_members_pdf(request):

    status = request.GET.get(
        "status",
        "active"
    )


    if status == "all":

        members = Member.objects.all()

    else:

        members = Member.objects.filter(
            status=status
        )


    response = HttpResponse(
        content_type="application/pdf"
    )


    response[
        "Content-Disposition"
    ] = (
        'attachment; filename="members_list.pdf"'
    )


    document = SimpleDocTemplate(
        response
    )


    styles = getSampleStyleSheet()


    elements = []


    title = Paragraph(
        "Members List",
        styles["Heading2"]
    )


    elements.append(title)

    elements.append(
        Spacer(1, 12)
    )


    data = [

        [
            "Member UID",
            "Full Name",
            "Date Joined",
            "Status",
        ]

    ]


    for member in members:


        full_name = " ".join(

            filter(
                None,
                [
                    member.first_name,
                    member.middle_name,
                    member.surname,
                ]
            )

        )


        data.append([

            member.member_uid,

            full_name,

            member.joined_at.strftime(
                "%d %b %Y"
            )
            if member.joined_at
            else "",

            member.status.title(),

        ])


    table = Table(
        data,
        repeatRows=1
    )


    table.setStyle(

        TableStyle([

            (
                "BACKGROUND",
                (0,0),
                (-1,0),
                colors.darkgreen
            ),

            (
                "TEXTCOLOR",
                (0,0),
                (-1,0),
                colors.white
            ),

            (
                "GRID",
                (0,0),
                (-1,-1),
                0.5,
                colors.grey
            ),

            (
                "FONT",
                (0,0),
                (-1,0),
                "Helvetica-Bold"
            ),

            (
                "ALIGN",
                (0,0),
                (-1,-1),
                "LEFT"
            ),

        ])

    )


    elements.append(table)


    document.build(elements)


    return response


@staff_member_required
def membership_history(request):

    records = (
        MembershipStatusHistory.objects
        .select_related(
            "member",
            "performed_by"
        )
        .order_by("-created_at")
    )

    return render(
        request,
        "members/admin/members/membership_history.html",
        {
            "records": records,
        },
    )