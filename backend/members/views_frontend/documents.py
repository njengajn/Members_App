from django.shortcuts import render, redirect, get_object_or_404
from django.http import FileResponse, JsonResponse, Http404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.contrib import messages
import os, tempfile, zipfile
from backend.members.models import (Member, MemberDocument, DocumentRequest,)
from backend.members.services.document_files import (
    prepare_document_file,
    generate_document_thumbnail,
    DocumentUploadValidationError,
)

import mimetypes


# =========================================================
# DOCUMENT UPLOAD
# =========================================================
#
# Handles:
# - Standard uploads
# - AJAX uploads
# - Uploads linked to requests
#
# SECURITY IMPROVEMENTS:
# - Prevent cross-member request uploads
# - Ensure uploaded document belongs to logged-in member
#
# =========================================================
@login_required
def upload_document(request):

    member = get_object_or_404(
        Member,
        user=request.user
    )

    # =====================================================
    # POST -> HANDLE UPLOAD
    # =====================================================
    if request.method == "POST":

        uploaded_file = request.FILES.get("file")

        # =================================================
        # VALIDATE FILE
        # =================================================
        if not uploaded_file:

            if request.headers.get("x-requested-with") == "XMLHttpRequest":

                return JsonResponse(
                    {
                        "error": "No file uploaded"
                    },
                    status=400
                )

            messages.error(
                request,
                "No file uploaded."
            )

            return redirect("members:member_requests")
        original_filename = uploaded_file.name

        # =================================================
        # STEP 7 - CENTRAL VALIDATION + PROCESSING
        # =================================================
        #
        # prepare_document_file() validates the upload before
        # image processing and before the document is saved.
        # =================================================

        try:

            uploaded_file = prepare_document_file(
                uploaded_file=uploaded_file,
                member=member,
                document_title=request.POST.get(
                    "title",
                    uploaded_file.name,
                ),
            )

        except DocumentUploadValidationError as exc:

            # Invalid uploads must not become server errors.
            # AJAX requests receive a safe JSON error; normal
            # requests receive the existing Django message.

            if request.headers.get("x-requested-with") == "XMLHttpRequest":

                return JsonResponse(
                    {
                        "error": str(exc)
                    },
                    status=400
                )

            messages.error(
                request,
                str(exc)
            )

            return redirect("members:member_requests")

        # =================================================
        # CREATE DOCUMENT
        # =================================================
        doc = MemberDocument.objects.create(
            member=member,
            title=request.POST.get(
                "title",
                uploaded_file.name,
            ),
            description=request.POST.get(
                "description",
                "",
            ),
            file=uploaded_file,
            original_filename=original_filename,
        )

        generate_document_thumbnail(doc)

        # =================================================
        # LINK TO DOCUMENT REQUEST
        # =================================================
        request_id = request.POST.get("request_id")

        if request_id:

            try:

                # =========================================
                # SECURITY FIX:
                # Request MUST belong to member
                # =========================================
                doc_request = DocumentRequest.objects.get(
                    id=request_id,
                    member=member,
                )

                # =========================================
                # LINK REQUEST
                # =========================================
                if hasattr(doc, "document_request"):

                    doc.document_request = doc_request
                    doc.save()

                # =========================================
                # MARK COMPLETED
                # =========================================
                if hasattr(doc_request, "completed"):
                    doc_request.completed = True

                if hasattr(doc_request, "status"):
                    try:
                        doc_request.status = (
                            DocumentRequest.STATUS_COMPLETED
                        )
                    except Exception:
                        pass

                doc_request.save()

            except DocumentRequest.DoesNotExist:

                # =========================================
                # SECURITY:
                # Ignore invalid/foreign request IDs
                # =========================================
                pass

        # =================================================
        # AJAX RESPONSE
        # =================================================
        if request.headers.get("x-requested-with") == "XMLHttpRequest":

            return JsonResponse({
                "success": True,
                "id": doc.id,
                "title": doc.title,
                "status": doc.status,
            })

        # =================================================
        # NORMAL RESPONSE
        # =================================================
        messages.success(
            request,
            "Document uploaded successfully."
        )

        return redirect("members:member_requests")

    # =====================================================
    # GET -> SHOW UPLOAD PAGE
    # =====================================================
    return render(
        request,
        "members/documents/upload.html",
        {
            "request_id": request.GET.get("request_id")
        }
    )


# =========================================================
# DOCUMENTS PAGE
# =========================================================
@login_required
def documents_list(request):

    member = get_object_or_404(
        Member,
        user=request.user
    )

    documents = (
        MemberDocument.objects
        .filter(member=member)
        .order_by("-uploaded_at")
    )

    return render(
        request,
        "members/documents.html",
        {
            "documents": documents
        }
    )


# =========================================================
# SECURE MEMBER DOCUMENT VIEW
# =========================================================

@login_required
def view_document_file(request, file_id):
    """
    Securely display a MemberDocument belonging to the
    currently authenticated member.

    SECURITY RULES
    --------------
    1. User must be authenticated.
    2. The document must exist.
    3. The document must belong to request.user.member.
    4. Archived documents are not available to members.
    5. The raw /media/member_documents/ URL is never used
       for authorization.
    6. The file is opened through Django's storage API.

    This endpoint is intended for:
        - image previews
        - PDF viewing
        - browser-viewable document access

    It is NOT the existing download_document() endpoint.
    """

    # =====================================================
    # FIND THE LOGGED-IN MEMBER
    # =====================================================

    member = get_object_or_404(
        Member,
        user=request.user,
    )

    # =====================================================
    # FIND DOCUMENT BELONGING TO THIS MEMBER
    # =====================================================
    #
    # Do NOT retrieve MemberDocument using only file_id.
    #
    # The member restriction is part of the database query.
    # This prevents a member from requesting another member's
    # document by changing the document ID in the URL.
    #

    document = get_object_or_404(
        MemberDocument,
        id=file_id,
        member=member,
    )

    # =====================================================
    # CENTRAL DOCUMENT SECURITY CHECK
    # =====================================================
    #
    # MemberDocument.can_be_viewed_by() already defines the
    # application's document visibility rules:
    #
    # - authenticated users only
    # - staff/admin users allowed
    # - archived documents hidden from members
    # - normal members may view their own documents only
    #
    # The query above already restricts this endpoint to the
    # owning member. This additional check keeps the model's
    # central security rule authoritative.
    #

    if not document.can_be_viewed_by(request.user):
        raise Http404("Document not found.")

    # =====================================================
    # VERIFY FILE EXISTS
    # =====================================================

    if not document.file:
        raise Http404("File not found.")

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
    #
    # Browsers need the actual MIME type:
    #
    # JPG  -> image/jpeg
    # PNG  -> image/png
    # WebP -> image/webp
    # PDF  -> application/pdf
    #
    # Do not return image/*.
    #

    content_type, _ = mimetypes.guess_type(
        document.file.name
    )

    if not content_type:
        content_type = "application/octet-stream"

    # =====================================================
    # RETURN FILE
    # =====================================================
    #
    # as_attachment=False allows supported files such as
    # JPG, PNG and PDF to open in the browser.
    #

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
# SECURE MEMBER DOCUMENT THUMBNAIL
# =========================================================

@login_required
def view_document_thumbnail(request, file_id):
    """
    Securely serve a MemberDocument thumbnail.

    SECURITY:
        - User must be authenticated.
        - Authorised administrators may view any MemberDocument.
        - Members may view only their own documents.
        - MemberDocument.can_be_viewed_by() remains
          authoritative for member access.
        - Archived documents remain unavailable to members.
        - Raw thumbnail MEDIA_URL is never exposed.
    """

    # =====================================================
    # ADMIN ACCESS
    # =====================================================
    #
    # Administrators do not need to have a Member record.
    #
    # They are allowed to access authorised MemberDocuments
    # through the secure endpoint.
    #

    if request.user.is_staff:

        document = get_object_or_404(
            MemberDocument,
            id=file_id,
        )

    # =====================================================
    # MEMBER ACCESS
    # =====================================================
    #
    # Non-admin authenticated users must have a Member
    # record and may only access their own document.
    #

    else:

        member = get_object_or_404(
            Member,
            user=request.user,
        )

        document = get_object_or_404(
            MemberDocument,
            id=file_id,
            member=member,
        )

        # =================================================
        # CENTRAL SECURITY CHECK
        # =================================================

        if not document.can_be_viewed_by(request.user):
            raise Http404("Document not found.")

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
# DOWNLOAD SINGLE DOCUMENT
# =========================================================

@login_required
def download_document(request, file_id):

    member = get_object_or_404(
        Member,
        user=request.user
    )

    doc = get_object_or_404(
        MemberDocument,
        id=file_id,
        member=member,
    )

    if not doc.file:
        raise Http404("File not found")

    return FileResponse(
        doc.file.open("rb"),
        as_attachment=True,
        filename=os.path.basename(doc.file.name),
    )


# =========================================================
# DOWNLOAD ALL DOCUMENTS AS ZIP
# =========================================================

@login_required
def download_zip(request):

    member = get_object_or_404(
        Member,
        user=request.user
    )

    documents = (
        MemberDocument.objects
        .filter(member=member)
        .exclude(file="")
    )

    # =====================================================
    # TEMP ZIP FILE
    # =====================================================
    temp_zip = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".zip"
    )

    with zipfile.ZipFile(
        temp_zip.name,
        "w",
        zipfile.ZIP_DEFLATED
    ) as z:

        for doc in documents:

            try:

                if doc.file and os.path.exists(doc.file.path):

                    z.write(
                        doc.file.path,
                        arcname=os.path.basename(
                            doc.file.name
                        )
                    )

            except Exception:
                # Skip broken files safely
                continue

    return FileResponse(
        open(temp_zip.name, "rb"),
        as_attachment=True,
        filename="my_documents.zip",
    )


# =========================================================
# DOCUMENT REQUESTS
# =========================================================

@login_required
def document_requests(request):

    member = get_object_or_404(
        Member,
        user=request.user
    )

    requests = (
        DocumentRequest.objects
        .filter(
            member=member,
            completed=False
        )
        .order_by("-created_at")
    )

    return render(
        request,
        "members/documents/document_requests.html",
        {
            "requests": requests
        }
    )


# =========================================================
# UPLOAD REQUESTED DOCUMENT
# =========================================================

@login_required
def upload_requested_document(request, request_id):

    member = get_object_or_404(
        Member,
        user=request.user
    )

    doc_request = get_object_or_404(
        DocumentRequest,
        id=request_id,
        member=member,
    )

    if request.method == "POST":

        uploaded_file = request.FILES.get("file")

        if not uploaded_file:

            messages.error(
                request,
                "Please select a file."
            )

            return redirect(
                "members:upload_requested_document",
                request_id=request_id
            )

        # =================================================
        # CREATE DOCUMENT
        # =================================================
        original_filename = uploaded_file.name

        # =================================================
        # STEP 7 - CENTRAL VALIDATION + PROCESSING
        # =================================================

        try:

            uploaded_file = prepare_document_file(
                uploaded_file=uploaded_file,
                member=member,
                document_title=doc_request.title,
            )

        except DocumentUploadValidationError as exc:

            # Validation failure occurs before MemberDocument
            # creation and before the request is completed.

            messages.error(
                request,
                str(exc)
            )

            return redirect(
                "members:upload_requested_document",
                request_id=request_id
            )

        doc = MemberDocument.objects.create(
            member=member,
            file=uploaded_file,
            original_filename=original_filename,
            title=doc_request.title,
            document_request=doc_request,
        )

        generate_document_thumbnail(doc)

        # =================================================
        # MARK REQUEST COMPLETE
        # =================================================
        if hasattr(doc_request, "completed"):
            doc_request.completed = True

        if hasattr(doc_request, "status"):
            try:
                doc_request.status = (
                    DocumentRequest.STATUS_COMPLETED
                )
            except Exception:
                pass

        doc_request.save()

        messages.success(
            request,
            "Requested document uploaded successfully."
        )

        return redirect("members:member_requests")

    return render(
        request,
        "members/documents/upload_requested.html",
        {
            "request_obj": doc_request,
        },
    )


# =========================================================
# MEMBER REQUESTS PAGE
# =========================================================

@login_required
def member_requests(request):

    member = get_object_or_404(
        Member,
        user=request.user
    )

    requests = (
        DocumentRequest.objects
        .filter(member=member)
        .order_by("-created_at")
    )

    uploaded_documents = (
        MemberDocument.objects
        .filter(member=member)
        .select_related(
            "document_request",
            "dependant",
            "claim",
        )
        .order_by("-uploaded_at")
    )

    context = {
        "requests": requests,
        "uploaded_documents": uploaded_documents,
    }

    return render(
        request,
        "members/documents/document_requests.html",
        context
    )
    
@login_required
def resubmit_document(request, document_id,):
    """
    Upload a replacement document for a rejected document.

    The document remains linked to the same
    DocumentRequest and is returned to
    Pending Review.
    """


    member = get_object_or_404(
        Member,
        user=request.user,
    )

    # --------------------------------------------------
    # REJECTED DOCUMENT
    # --------------------------------------------------

    document = get_object_or_404(
        MemberDocument,
        id=document_id,
        member=member,
        status=MemberDocument.STATUS_REJECTED,
        can_resubmit=True,
    )

    # --------------------------------------------------
    # SAVE REPLACEMENT
    # --------------------------------------------------

    if request.method == "POST":

        uploaded_file = request.FILES.get(
            "document_file"
        )

        if uploaded_file:

            original_filename = uploaded_file.name

            # =================================================
            # STEP 7 - CENTRAL VALIDATION + PROCESSING
            # =================================================

            try:

                uploaded_file = prepare_document_file(
                    uploaded_file=uploaded_file,
                    member=member,
                    document_title=document.title,
                )

            except DocumentUploadValidationError as exc:

                # Validation failure must leave the rejected
                # document unchanged.

                messages.error(
                    request,
                    str(exc)
                )

                return redirect(
                    "members:resubmit_document",
                    document_id=document.id,
                )

            document.file = uploaded_file

            document.original_filename = original_filename

            document.status = (
                MemberDocument.STATUS_PENDING
            )

            # =================================================
            # REMOVE OLD THUMBNAIL
            # =================================================

            if document.thumbnail:

                try:
                    document.thumbnail.delete(
                        save=False
                    )
                except Exception:
                    pass

            document.thumbnail = None

            # =================================================
            # REPLACE DOCUMENT FILE
            # =================================================

            document.file = uploaded_file

            document.original_filename = original_filename

            document.status = MemberDocument.STATUS_PENDING

            document.rejection_reason = ""

            document.admin_notes = ""

            document.can_resubmit = False

            document.save()

            # =================================================
            # GENERATE NEW THUMBNAIL
            # =================================================

            generate_document_thumbnail(document)

            # =================================================
            # UPDATE REQUEST STATUS
            # =================================================

            if document.document_request:
                document.document_request.update_request_status()

            messages.success(
                request,
                "Replacement document submitted successfully.",
            )

            return redirect(
                "members:member_requests"
            )

    return render(
        request,
        "members/documents/resubmit_document.html",
        {
            "document": document,
        },
    )

# =========================================================
# SECURE MEMBER DOCUMENT MEDIA
# =========================================================

@login_required
def serve_member_document_media(request, path):
    """
    Securely serve a MemberDocument from the existing
    /media/member_documents/ URL structure.

    This view exists specifically to prevent the generic
    public MEDIA_ROOT handler from exposing private
    MemberDocument files.

    SECURITY:
        - User must be authenticated.
        - Requested path must belong to a MemberDocument.
        - Normal members may access only their own document.
        - Archived documents are not available to members.
        - Staff/admin users may access documents.
        - Unknown document paths return 404.
    """

    # =====================================================
    # NORMALISE PATH
    # =====================================================

    requested_path = str(path).replace(
        "\\",
        "/",
    ).lstrip("/")

    # =====================================================
    # FIND THE DOCUMENT
    # =====================================================
    #
    # The stored FileField value includes:
    #
    #     member_documents/YYYY/MM/filename
    #
    # We deliberately query MemberDocument rather than
    # constructing an arbitrary filesystem path.
    #

    stored_name = (
        f"member_documents/{requested_path}"
    )

    document = get_object_or_404(
        MemberDocument,
        file=stored_name,
    )

    # =====================================================
    # CENTRAL AUTHORISATION
    # =====================================================
    #
    # MemberDocument already contains the application's
    # can_be_viewed_by() security helper.
    #
    # This prevents:
    #
    #   logged-out user
    #   another member
    #
    # from accessing this document.
    #

    if not document.can_be_viewed_by(request.user):
        raise Http404("Document not found.")

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
    # MIME TYPE
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