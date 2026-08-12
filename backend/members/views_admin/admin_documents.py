from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from backend.members.models import DocumentRequest, Member, MemberDocument
from backend.members.decorators import admin_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from backend.members.views_frontend import documents
from backend.members.services.document_files import prepare_document_file
from django.http import FileResponse, Http404
from django.views.decorators.http import require_GET
from django.views.decorators.clickjacking import xframe_options_sameorigin
import os

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
    
# =========================================================
# SECURE ADMIN PDF PREVIEW
# =========================================================

@admin_required
@require_GET
@xframe_options_sameorigin
def admin_document_preview(request, document_id):
    """
    Securely preview a member PDF document for administrators.

    SECURITY:
    - Requires an authenticated administrator.
    - Looks up the document through MemberDocument.
    - Does not expose the raw /media/ URL to the browser.
    - Only PDF files are allowed through this endpoint.
    - The response is explicitly intended for same-origin
      iframe display.
    - Global X-Frame-Options protection remains unchanged.
    """

    # =====================================================
    # GET DOCUMENT
    # =====================================================
    #
    # admin_required ensures that only authorised admin
    # users can reach this view.
    #
    document = get_object_or_404(
        MemberDocument,
        id=document_id,
    )

    # =====================================================
    # VERIFY FILE EXISTS
    # =====================================================
    if not document.file:
        raise Http404("Document file not found.")

    # =====================================================
    # VERIFY THIS IS A PDF
    # =====================================================
    #
    # Do not allow this endpoint to become a generic
    # file-serving endpoint.
    #
    if not document.is_pdf:
        raise Http404("PDF preview is only available for PDF files.")

    # =====================================================
    # OPEN FILE SAFELY THROUGH DJANGO STORAGE
    # =====================================================
    #
    # Use Django's storage API instead of constructing
    # a filesystem path manually.
    #
    try:
        file_handle = document.file.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("Document file could not be opened.")

    # =====================================================
    # RETURN PDF INLINE
    # =====================================================
    #
    # as_attachment=False tells the browser that this is
    # intended for inline display rather than download.
    #
    response = FileResponse(
        file_handle,
        as_attachment=False,
        filename=os.path.basename(document.file.name),
        content_type="application/pdf",
    )

    # =====================================================
    # SECURITY / BROWSER BEHAVIOUR
    # =====================================================
    #
    # @xframe_options_sameorigin above changes the
    # X-Frame-Options header ONLY for this response.
    #
    # The PDF can therefore be displayed in an iframe
    # belonging to the same application, while the rest
    # of the application retains its normal protection.
    #

    return response

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


# NEW FEATURE
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
        original_filename = uploaded_file.name

        uploaded_file = prepare_document_file(
            uploaded_file=uploaded_file,
            member=member,
            document_title=document_request.title,
        )
        MemberDocument.objects.create(
            member=member,
            title=document_request.title,
            description=(
                "Uploaded by admin "
                "from external member submission."
            ),
            file=uploaded_file,
            original_filename=original_filename,
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

@admin_required
def reject_document_form(
    request,
    document_id,
    ):
    """
    Display and process the document rejection form.

    GET:
        Display the rejection form.

    POST:
        Validate the rejection reason,
        reject the document,
        save internal admin notes,
        and return to the member's admin document list.
    """

    # =====================================================
    # GET DOCUMENT
    # =====================================================

    document = get_object_or_404(
        MemberDocument,
        id=document_id,
    )

    # =====================================================
    # PROCESS REJECTION
    # =====================================================

    if request.method == "POST":

        rejection_reason = request.POST.get(
            "rejection_reason",
            "",
        ).strip()

        admin_note = request.POST.get(
            "admin_note",
            "",
        ).strip()

        # -------------------------------------------------
        # REJECTION REASON IS REQUIRED
        # -------------------------------------------------

        if not rejection_reason:

            messages.error(
                request,
                "Please enter a rejection reason.",
            )

        else:

            # -------------------------------------------------
            # REJECT DOCUMENT
            # -------------------------------------------------
            #
            # MemberDocument.reject() owns the rejection
            # business logic.
            #
            # IMPORTANT:
            # Do NOT pass admin_note to reject().
            # reject() accepts only user and reason.
            # -------------------------------------------------

            document.reject(
                user=request.user,
                reason=rejection_reason,
            )

            # -------------------------------------------------
            # SAVE INTERNAL ADMIN NOTE
            # -------------------------------------------------

            document.admin_notes = admin_note

            document.save(
                update_fields=[
                    "admin_notes",
                ]
            )

            # -------------------------------------------------
            # SUCCESS MESSAGE
            # -------------------------------------------------

            messages.success(
                request,
                "Document rejected successfully.",
            )

            # -------------------------------------------------
            # RETURN TO MEMBER'S DOCUMENT LIST
            # -------------------------------------------------

            return redirect(
                f"/admin-panel/admin/documents/member/{document.member_id}/"
            )

    # =====================================================
    # GET REQUEST / INVALID POST
    # =====================================================
    #
    # Display the rejection form.
    #
    # A GET request MUST NEVER reject the document.
    # =====================================================

    return render(
        request,
        "members/admin/documents/reject_document.html",
        {
            "document": document,
        },
    )
