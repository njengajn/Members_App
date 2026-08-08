from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from backend.members.models import DocumentRequest, Member, MemberDocument
from backend.members.decorators import admin_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages

from backend.members.views_frontend import documents

@admin_required
def admin_documents_list(request, member_id):

    # =====================================================
    # MEMBER
    # =====================================================

    member = get_object_or_404(
        Member,
        id=member_id
    )

    # =====================================================
    # DOCUMENTS
    # =====================================================

    documents = MemberDocument.objects.filter(
        member=member
    ).order_by("-uploaded_at")

    # =====================================================
    # REQUESTS
    # =====================================================

    requests = DocumentRequest.objects.filter(
        member=member
    ).order_by("-created_at")

    # =====================================================
    # CONTEXT
    # =====================================================

    context = {
        "member": member,
        "documents": documents,
        "requests": requests,
    }

    # =====================================================
    # RENDER
    # =====================================================

    return render(
        request,
        "members/admin/documents/admin_documents_list.html",
        context,
    )
    
@admin_required
def admin_document_review(
    request,
    document_id,
    action
):

    # =====================================================
    # GET DOCUMENT
    # =====================================================

    document = get_object_or_404(
        MemberDocument,
        id=document_id
    )

    # =====================================================
    # APPROVE
    # =====================================================

    if action == "approve":

        document.approve(
            user=request.user
        )

    # =====================================================
    # REJECT
    # =====================================================

    elif action == "reject":

        rejection_reason = request.POST.get(
            "rejection_reason",
            ""
        )
        

        document.reject(
            user=request.user,
            reason=rejection_reason,
        )
        
        document.refresh_from_db()


        # IMPORTANT
        document.can_resubmit = True

    # =====================================================
    # SAVE REVIEW
    # =====================================================

    # =====================================================
    # DIRECT REDIRECT
    # =====================================================
    #
    # IMPORTANT:
    #
    # We bypass reverse() entirely because
    # your admin routing currently has
    # namespace inconsistencies.
    #
    # =====================================================

    return redirect(
        f"/admin-panel/admin/documents/member/{document.member_id}/"
    )


@staff_member_required
def documents_list(request, member_id):
    """
    View all documents for a specific member
    """
    member = get_object_or_404(Member, id=member_id)

    documents = MemberDocument.objects.filter(member=member,is_archived=False).order_by("-uploaded_at")

    return render(
        request,
        "members/admin/documents/documents_list.html",
        {
            "member": member,
            "documents": documents,
        },
    )


@staff_member_required
def review_document(request, document_id, action):
    """
    Approve / Reject document
    """
    doc = get_object_or_404(MemberDocument, id=document_id)

    if action == "approve":
        doc.status = MemberDocument.STATUS_APPROVED
    elif action == "reject":
        doc.status = MemberDocument.STATUS_REJECTED

    doc.reviewed_at = timezone.now()
    doc.save()

    return redirect("admin_documents_list", member_id=doc.member_id)


# ✅ NEW FEATURE
@staff_member_required
def request_document(request, member_id):
    """
    Admin requests a document from a member
    """
    member = get_object_or_404(Member, id=member_id)

    if request.method == "POST":
        title = request.POST.get("title")
        description = request.POST.get("description")

        DocumentRequest.objects.create(
            member=member,
            title=title,
            description=description,
        )
        
        messages.success(request, f"Document request '{title}' sent successfully.")

        return redirect("members_admin:admin_documents_list", member_id=member.id)

    return render(
        request,
        "members/admin/documents/request_document.html",
        {
            "member": member,
        },
    )

# =====================================================
# ADMIN UPLOAD REQUESTED DOCUMENT
# =====================================================
@staff_member_required
def upload_requested_document_admin(request, request_id):
    """
    Allows admin to upload a document on behalf
    of a member when received externally
    (email, WhatsApp, physical copy etc.)
    """

    document_request = get_object_or_404(
        DocumentRequest,
        id=request_id
    )

    member = document_request.member

    if request.method == "POST":

        uploaded_file = request.FILES.get("file")

        if not uploaded_file:

            messages.error(
                request,
                "Please select a document."
            )

            return redirect(
                "members_admin:admin_documents_list",
                member_id=member.id,
            )

        # ================================================
        # CREATE DOCUMENT
        # ================================================
        MemberDocument.objects.create(

            member=member,

            title=document_request.title,

            description=(
                "Uploaded by admin "
                "from external member submission."
            ),

            file=uploaded_file,

            document_request=document_request,

            status=MemberDocument.STATUS_APPROVED,

            reviewed_at=timezone.now(),

            reviewed_by=request.user,
        )

        # ================================================
        # MARK REQUEST COMPLETED
        # ================================================
        document_request.status = (
            DocumentRequest.STATUS_COMPLETED
        )

        # Backward compatibility
        if hasattr(document_request, "completed"):
            document_request.completed = True

        document_request.save()

        messages.success(
            request,
            "Document uploaded successfully."
        )

        return redirect(
            "members_admin:admin_documents_list",
            member_id=member.id,
        )

    return redirect(
        "members_admin:admin_documents_list",
        member_id=member.id,
    )
    
# =====================================================
# ADMIN ARCHIVE DOCUMENT
# =====================================================
@staff_member_required
def archive_document(request, document_id):

    document = get_object_or_404(
        MemberDocument,
        id=document_id
    )

    # Prevent double archive
    if not document.is_archived:

        document.is_archived = True

        document.archived_at = timezone.now()

        document.save()

        messages.success(
            request,
            "Document archived successfully."
        )

    return redirect(
        "members_admin:admin_documents_list",
        member_id=document.member_id,
    )


# =====================================================
# ADMIN DELETE DOCUMENT
# =====================================================
@staff_member_required
def delete_document(request, document_id):

    document = get_object_or_404(
        MemberDocument,
        id=document_id
    )

    member_id = document.member_id

    # ================================================
    # DELETE PHYSICAL FILE
    # ================================================
    if document.file:

        try:
            document.file.delete(save=False)
        except Exception:
            pass

    # ================================================
    # DELETE RECORD
    # ================================================
    document.delete()

    messages.success(
        request,
        "Document deleted successfully."
    )

    return redirect(
        "members_admin:admin_documents_list",
        member_id=member_id,
    )

def document_dashboard(request):
    documents = MemberDocument.objects.all().order_by("-uploaded_at")
    requests = (DocumentRequest.objects.filter(completed=False).order_by("-created_at"))

    return render(
        request,
        "members/admin/documents/documents_dashboard.html",
        {
            "documents": documents,
            "requests": requests
        }
    )
    
@staff_member_required
def dashboard(request):
    """
    Admin dashboard showing all documents and requests
    """
    documents = MemberDocument.objects.all().order_by("-uploaded_at")
    requests = (DocumentRequest.objects.filter(completed=False).order_by("-created_at"))

    return render(
        request,
        "members/admin/documents/dashboard.html",
        {
            "documents": documents,
            "requests": requests,
        },
    )


@staff_member_required
def approve_document(request, pk):
    """
    Wrapper view.

    Keeps existing URL and permissions,
    but delegates approval to the model.
    """

    document = get_object_or_404(
        MemberDocument,
        pk=pk,
    )

    # All business logic is handled by the model.
    document.approve(
        user=request.user,
    )

    return redirect("admin_documents")

@staff_member_required
def reject_document(
    request,
    pk,
):
    """
    Display and process the rejection form.
    """

    document = get_object_or_404(
        MemberDocument,
        pk=pk,
    )

    if request.method == "POST":

        rejection_reason = request.POST.get(
            "rejection_reason",
            "",
        ).strip()

        admin_note = request.POST.get(
            "admin_note",
            "",
        ).strip()

        if not rejection_reason:

            messages.error(
                request,
                "Please enter a rejection reason.",
            )

        else:

            # ------------------------------------------
            # Reject document
            # ------------------------------------------

            document.reject(
                user=request.user,
                reason=rejection_reason,
            )

            # ------------------------------------------
            # Internal admin note
            # ------------------------------------------

            document.admin_notes = admin_note

            document.save(
                update_fields=[
                    "admin_notes",
                ]
            )

            messages.success(
                request,
                "Document rejected successfully.",
            )

            return redirect(
                "members_admin:admin_documents_list",
                member_id=document.member_id,
            )

    return render(
        request,
        "members/admin/documents/reject_document.html",
        {
            "document": document,
        },
    )

@staff_member_required
def reject_documentReplacedAbove(request, pk):
    """
    Wrapper view.

    Keeps existing URL and permissions,
    but delegates rejection to the model.
    """

    document = get_object_or_404(
        MemberDocument,
        pk=pk,
    )

    rejection_reason = request.POST.get(
        "rejection_reason",
        "",
    )

    admin_note = request.POST.get(
        "admin_note",
        "",
    )

    document.reject(
        user=request.user,
        reason=rejection_reason,
        admin_note=admin_note,
    )

    return redirect("admin_documents")

@admin_required
def reject_document_form(
        request,
        document_id,
    ):
    """
    Display and process the rejection form.

    This page collects the rejection reason
    before rejecting the document.
    """

    document = get_object_or_404(
        MemberDocument,
        id=document_id,
    )

    if request.method == "POST":

        rejection_reason = request.POST.get(
            "rejection_reason",
            "",
        ).strip()

        admin_note = request.POST.get(
            "admin_note",
            "",
        ).strip()

        if request.method == "POST":

            rejection_reason = request.POST.get(
                "rejection_reason",
                "",
            ).strip()

            admin_note = request.POST.get(
                "admin_note",
                "",
            ).strip()

            if not rejection_reason:

                messages.error(
                    request,
                    "Please enter a rejection reason.",
                )

            else:

                # ------------------------------------------
                # Reject document
                # ------------------------------------------

                document.reject(
                    user=request.user,
                    reason=rejection_reason,
                )

                # ------------------------------------------
                # Save internal notes
                # ------------------------------------------

                document.admin_notes = admin_note

                document.save(
                    update_fields=[
                        "admin_notes",
                    ]
                )

                messages.success(
                    request,
                    "Document rejected successfully.",
                )

                return redirect(
                    f"/admin-panel/admin/documents/member/{document.member_id}/"
                )
    return render(
        request,
        "members/admin/documents/reject_document.html",
        {
            "document": document,
        },
    )