from django.shortcuts import render, redirect, get_object_or_404
from django.http import FileResponse, JsonResponse, Http404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.contrib import messages
import os, tempfile, zipfile
from backend.members.models import (Member, MemberDocument, DocumentRequest,)
from backend.members.services.document_files import (prepare_document_file,)
from backend.members.services.document_files import prepare_document_file

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

        uploaded_file = prepare_document_file(
            uploaded_file=uploaded_file,
            member=member,
            document_title=request.POST.get(
                "title",
                uploaded_file.name,
            ),
        )

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

        uploaded_file = prepare_document_file(
            uploaded_file=uploaded_file,
            member=member,
            document_title=doc_request.title,
        )

        MemberDocument.objects.create(
            member=member,
            file=uploaded_file,
            original_filename=original_filename,
            title=doc_request.title,
            document_request=doc_request,
        )
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

            uploaded_file = prepare_document_file(
                uploaded_file=uploaded_file,
                member=member,
                document_title=document.title,
            )

            document.file = uploaded_file

            document.original_filename = original_filename

            document.status = (
                MemberDocument.STATUS_PENDING
            )

            document.rejection_reason = ""

            document.admin_notes = ""

            document.can_resubmit = False

            document.save()

            # Keep the linked request in sync
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