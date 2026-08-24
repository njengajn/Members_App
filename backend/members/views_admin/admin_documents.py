from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from backend.members.models import DocumentRequest, Member, MemberDocument
from backend.members.decorators import admin_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from backend.members.views_frontend import documents
from backend.members.services.document_files import (
    prepare_document_file,
    generate_document_thumbnail,
    DocumentUploadValidationError,
)
from django.http import FileResponse, Http404
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.clickjacking import xframe_options_sameorigin
import os
import mimetypes

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
# SECURE ADMIN MEMBER DOCUMENT VIEW
# =========================================================

@admin_required
def admin_document_file(request, document_id):
    """
    Securely serve a MemberDocument to an authorised admin.

    SECURITY RULES
    --------------
    1. The user must pass the existing admin_required
       decorator.
    2. The document must exist.
    3. The file is opened through Django's storage API.
    4. The raw /media/member_documents/ URL is never used
       by the admin document interface.

    Intended for:
        - JPG/PNG/WebP image previews
        - PDF/document viewing
        - authorised admin file access
    """

    # =====================================================
    # FIND DOCUMENT
    # =====================================================

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
    # OPEN THROUGH DJANGO STORAGE
    # =====================================================

    try:
        file_handle = document.file.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("Document file could not be opened.")

    # =====================================================
    # DETERMINE MIME TYPE
    # =====================================================

    content_type, _ = mimetypes.guess_type(
        document.file.name
    )

    if not content_type:
        content_type = "application/octet-stream"

    # =====================================================
    # RETURN FILE
    # =====================================================

    return FileResponse(
        file_handle,
        as_attachment=False,
        filename=(
            document.original_filename
            or document.file.name.rsplit("/", 1)[-1]
        ),
        content_type=content_type,
    )

# =========================================================
# SECURE ADMIN DOCUMENT THUMBNAIL
# =========================================================

@admin_required
def admin_document_thumbnail(request, document_id):
    """
    Securely serve a MemberDocument thumbnail to an
    authorised administrator.

    The thumbnail is never served directly through MEDIA_URL.
    """

    # =====================================================
    # FIND DOCUMENT
    # =====================================================

    document = get_object_or_404(
        MemberDocument,
        id=document_id,
    )

    # =====================================================
    # VERIFY THUMBNAIL EXISTS
    # =====================================================

    if not document.thumbnail:
        raise Http404("Thumbnail not found.")

    # =====================================================
    # OPEN THROUGH DJANGO STORAGE
    # =====================================================

    try:
        file_handle = document.thumbnail.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404(
            "Thumbnail could not be opened."
        )

    # =====================================================
    # RETURN THUMBNAIL
    # =====================================================

    return FileResponse(
        file_handle,
        as_attachment=False,
        filename=(
            document.thumbnail.name.rsplit(
                "/",
                1,
            )[-1]
        ),
        content_type="image/jpeg",
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

    # =====================================================
    # ADMIN DOCUMENT LIST
    # =====================================================
    # Admins need to see both active and archived documents
    # so that archived documents can be restored or permanently
    # deleted.
    documents = MemberDocument.objects.filter(
        member=member,
    ).order_by("-uploaded_at")

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
    (email, WhatsApp, physical copy etc.).

    Step 7:
    - prepare_document_file() performs the central upload
      validation before image processing or saving.
    - DocumentUploadValidationError is handled here so an
      invalid upload produces a safe user-facing message
      instead of a server error.
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
        # ORIGINAL BROWSER FILENAME
        # ================================================
        #
        # Keep the original filename before
        # prepare_document_file() generates the secure
        # stored filename.
        # ================================================

        original_filename = uploaded_file.name

        # ================================================
        # STEP 7 - CENTRAL VALIDATION + PROCESSING
        # ================================================
        #
        # Validation is centralised in document_files.py.
        # Do not duplicate validation rules in this view.
        #
        # Validation happens before the document is created.
        # ================================================

        try:

            uploaded_file = prepare_document_file(
                uploaded_file=uploaded_file,
                member=member,
                document_title=document_request.title,
            )

        except DocumentUploadValidationError as exc:

            # ============================================
            # SAFE VALIDATION ERROR
            # ============================================
            #
            # The invalid upload must not result in a 500.
            # Nothing has been saved at this point.
            # ============================================

            messages.error(
                request,
                str(exc)
            )

            return redirect(
                "members_admin:admin_documents_list",
                member_id=member.id,
            )

        # ================================================
        # CREATE DOCUMENT
        # ================================================

        now = timezone.now()

        doc = MemberDocument.objects.create(
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
            reviewed_at=now,
            reviewed_by=request.user,
            approved_at=now,
            approved_by=request.user,
        )

        generate_document_thumbnail(doc)

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
    """
    Archive an active document.

    Archive is a soft-delete operation:
        - The database record is retained.
        - The uploaded file is retained.
        - The document becomes hidden from normal
          member access.
        - The document can later be restored.

    IMPORTANT:
        Archiving changes database state, therefore this
        endpoint MUST only accept POST requests.

        The template submits the action through a POST form
        containing Django's CSRF token.
    """

    # -------------------------------------------------
    # SECURITY: STATE-CHANGING ACTION MUST BE POST
    # -------------------------------------------------

    if request.method != "POST":

        messages.error(
            request,
            "Invalid request method.",
        )

        return redirect(
            "members_admin:admin_documents_list",
            member_id=get_object_or_404(
                MemberDocument,
                id=document_id,
            ).member_id,
        )

    document = get_object_or_404(
        MemberDocument,
        id=document_id,
    )

    # -------------------------------------------------
    # ARCHIVE ONLY ACTIVE DOCUMENTS
    # -------------------------------------------------
    # MemberDocument.archive() owns the actual archive
    # state transition and returns False if the document
    # is already archived.

    if document.archive():

        messages.success(
            request,
            "Document archived successfully.",
        )

    else:

        messages.info(
            request,
            "Document is already archived.",
        )

    return redirect(
        "members_admin:admin_documents_list",
        member_id=document.member_id,
    )

# =====================================================
# ADMIN RESTORE DOCUMENT
# =====================================================
@staff_member_required
def restore_document(request, document_id):
    """
    Restore an archived document.

    Only archived documents can be restored.

    Restoring:
        - removes the archived flag
        - clears archived_at
        - keeps the original document record
        - keeps the uploaded file
        - keeps the document's review history

    IMPORTANT:
        Restoring changes database state, therefore this
        endpoint MUST only accept POST requests.

        The template submits the action through a POST form
        containing Django's CSRF token.
    """

    # -------------------------------------------------
    # SECURITY: STATE-CHANGING ACTION MUST BE POST
    # -------------------------------------------------

    if request.method != "POST":

        messages.error(
            request,
            "Invalid request method.",
        )

        return redirect(
            "members_admin:admin_documents_list",
            member_id=get_object_or_404(
                MemberDocument,
                id=document_id,
            ).member_id,
        )

    document = get_object_or_404(
        MemberDocument,
        id=document_id,
    )

    # -------------------------------------------------
    # RESTORE ONLY ARCHIVED DOCUMENTS
    # -------------------------------------------------
    # MemberDocument.unarchive() owns the actual restore
    # state transition and returns False if the document
    # is already active.

    if document.unarchive():

        messages.success(
            request,
            "Document restored successfully.",
        )

    else:

        messages.info(
            request,
            "Document is already active.",
        )

    return redirect(
        "members_admin:admin_documents_list",
        member_id=document.member_id,
    )

# =====================================================
# ADMIN DELETE DOCUMENT PERMANENTLY
# =====================================================
@staff_member_required
def delete_document(request, document_id):
    """
    Permanently delete an archived document.

    Permanent deletion is deliberately restricted to
    archived documents so that active documents cannot
    bypass the archive lifecycle.

    This removes:
        - the original uploaded file
        - the generated thumbnail
        - the database record

    IMPORTANT:
        Permanent deletion changes database state and
        removes uploaded files, therefore this endpoint
        MUST only accept POST requests.

        The template submits the action through a POST form
        containing Django's CSRF token.
    """

    # -------------------------------------------------
    # SECURITY: STATE-CHANGING ACTION MUST BE POST
    # -------------------------------------------------

    if request.method != "POST":

        messages.error(
            request,
            "Invalid request method.",
        )

        return redirect(
            "members_admin:admin_documents_list",
            member_id=get_object_or_404(
                MemberDocument,
                id=document_id,
            ).member_id,
        )

    document = get_object_or_404(
        MemberDocument,
        id=document_id,
    )

    member_id = document.member_id

    # -------------------------------------------------
    # SAFETY GUARD
    # -------------------------------------------------
    # Active documents MUST be archived first.
    #
    # This is an important second layer of protection.
    # Even if somebody manually submits a POST request,
    # an active document cannot be permanently deleted.

    if not document.is_archived:

        messages.error(
            request,
            "Only archived documents can be permanently deleted.",
        )

        return redirect(
            "members_admin:admin_documents_list",
            member_id=member_id,
        )

    # -------------------------------------------------
    # DELETE ORIGINAL FILE
    # -------------------------------------------------

    if document.file:

        try:
            document.file.delete(save=False)
        except Exception:
            # Do not allow a storage-level deletion error
            # to leave the application in an inconsistent
            # request state.
            pass

    # -------------------------------------------------
    # DELETE GENERATED THUMBNAIL
    # -------------------------------------------------

    if document.thumbnail:

        try:
            document.thumbnail.delete(save=False)
        except Exception:
            # Thumbnail cleanup failure should not prevent
            # deletion of the database record.
            pass

    # -------------------------------------------------
    # DELETE DATABASE RECORD
    # -------------------------------------------------

    document.delete()

    messages.success(
        request,
        "Document permanently deleted.",
    )

    return redirect(
        "members_admin:admin_documents_list",
        member_id=member_id,
    )

@admin_required
def document_dashboard(request):
    """
    Documents dashboard.

    Provides operational document metrics and recent activity
    using the existing MemberDocument lifecycle.
    """

    today = timezone.localdate()

    # =====================================================
    # BASE QUERYSETS
    # =====================================================

    active_documents = MemberDocument.objects.filter(
        is_archived=False,
    )

    archived_documents = MemberDocument.objects.filter(
        is_archived=True,
    )

    # =====================================================
    # STATUS METRICS
    # =====================================================

    pending_review = active_documents.filter(
        status=MemberDocument.STATUS_PENDING,
    ).count()

    approved = active_documents.filter(
        status=MemberDocument.STATUS_APPROVED,
    ).count()

    awaiting_resubmission = active_documents.filter(
        status=MemberDocument.STATUS_REJECTED,
        can_resubmit=True,
    ).count()

    rejected = active_documents.filter(
        status=MemberDocument.STATUS_REJECTED,
    ).count()

    archived = archived_documents.count()

    # =====================================================
    # UPLOAD METRICS
    # =====================================================

    todays_uploads = MemberDocument.objects.filter(
        uploaded_at__date=today,
    ).count()

    documents_with_files = (
        MemberDocument.objects
        .exclude(file="")
        .order_by("-uploaded_at")
    )

    file_sizes = []

    for document in documents_with_files:
        try:
            if document.file:
                file_sizes.append(
                    (document, document.file.size)
                )
        except (OSError, ValueError):
            # Ignore files that are no longer available
            # in storage.
            continue

    total_storage_bytes = sum(
        size for _, size in file_sizes
    )

    average_upload_size = (
        total_storage_bytes / len(file_sizes)
        if file_sizes
        else 0
    )

    largest_uploads = sorted(
        file_sizes,
        key=lambda item: item[1],
        reverse=True,
    )[:5]

    # =====================================================
    # RECENT ACTIVITY
    # =====================================================

    allowed_activity_limits = {10, 20, 100}

    try:
        activity_limit = int(request.GET.get("activity_limit", 10))
    except (TypeError, ValueError):
        activity_limit = 10

    if activity_limit not in allowed_activity_limits:
        activity_limit = 10

    recent_activity = []

    activity_documents = (
        MemberDocument.objects
        .select_related("member", "dependant")
        .order_by("-uploaded_at")
    )

    for document in activity_documents:

        if document.uploaded_at:
            recent_activity.append({
                "document": document,
                "action": "Uploaded",
                "timestamp": document.uploaded_at,
            })

        if document.approved_at:
            recent_activity.append({
                "document": document,
                "action": "Approved",
                "timestamp": document.approved_at,
            })

        if document.rejected_at:
            recent_activity.append({
                "document": document,
                "action": "Rejected",
                "timestamp": document.rejected_at,
            })

        if document.resubmitted_at:
            recent_activity.append({
                "document": document,
                "action": "Resubmitted",
                "timestamp": document.resubmitted_at,
            })

        if document.archived_at:
            recent_activity.append({
                "document": document,
                "action": "Archived",
                "timestamp": document.archived_at,
            })

    recent_activity.sort(
        key=lambda item: item["timestamp"],
        reverse=True,
    )

    # =====================================================
    # MEMBER-DIVERSE ACTIVITY
    # =====================================================

    selected_activity = []
    deferred_activity = []

    seen_members = set()

    # First pass: give each member their newest activity.
    for activity in recent_activity:
        member_id = activity["document"].member_id

        if member_id not in seen_members:
            selected_activity.append(activity)
            seen_members.add(member_id)

            if len(selected_activity) >= activity_limit:
                break

    # Second pass: fill any remaining places with the next
    # most recent activities across all members.
    if len(selected_activity) < activity_limit:

        selected_ids = {
            id(activity)
            for activity in selected_activity
        }

        deferred_activity = [
            activity
            for activity in recent_activity
            if id(activity) not in selected_ids
        ]

        selected_activity.extend(
            deferred_activity[
                :activity_limit - len(selected_activity)
            ]
        )

    recent_activity = selected_activity

    # =====================================================
    # CONTEXT
    # =====================================================

    context = {
        "pending_review": pending_review,
        "approved": approved,
        "rejected": rejected,
        "awaiting_resubmission": awaiting_resubmission,
        "archived": archived,
        "todays_uploads": todays_uploads,
        "storage_used": total_storage_bytes,
        "average_upload_size": average_upload_size,
        "largest_uploads": largest_uploads,
        "recent_activity": recent_activity,
        "activity_limit": activity_limit,
        "activity_limits": [10, 20, 100],
    }

    return render(
        request,
        "members/admin/documents/documents_dashboard.html",
        context,
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
