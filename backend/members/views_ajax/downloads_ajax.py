import os
import zipfile
from django.http import HttpResponse, JsonResponse
from django.conf import settings


def download_zip(request):
    """
    AJAX endpoint → Create and return a ZIP file dynamically.
    Example: Download all member documents.
    """

    member_id = request.GET.get("member_id")

    if not member_id:
        return JsonResponse({"status": "error", "message": "member_id required"}, status=400)

    # Example folder path containing files to zip
    folder_path = os.path.join(settings.MEDIA_ROOT, f"members/{member_id}/documents")

    if not os.path.exists(folder_path):
        return JsonResponse({"status": "error", "message": "No documents found."}, status=404)

    # Temporary ZIP path
    zip_path = os.path.join(settings.MEDIA_ROOT, f"member_{member_id}_documents.zip")

    # Create ZIP
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for root, _, files in os.walk(folder_path):
            for file in files:
                abs_path = os.path.join(root, file)
                rel_path = abs_path.replace(folder_path, "").lstrip("\\/")
                zipf.write(abs_path, rel_path)

    # Serve file to browser
    with open(zip_path, "rb") as f:
        response = HttpResponse(f.read(), content_type="application/zip")
        response["Content-Disposition"] = f"attachment; filename=member_{member_id}_documents.zip"

    # Optional cleanup:
    # os.remove(zip_path)

    return response
