# backend/core/urls.py

from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from backend.members.views_frontend.documents import (
    serve_member_document_media,
)

urlpatterns = [
    path("", include(("backend.members.urls_frontend", "members"), namespace="members")),
    path("admin/", admin.site.urls),
    path("admin-panel/", include(("backend.members.urls_admin", "members_admin"), namespace="members_admin")),
    path("ajax/", include(("backend.members.urls_ajax", "ajax"), namespace="ajax")),
    path("api/", include(("backend.members.urls_api", "api"), namespace="api")),
]

# =========================================================
# PRIVATE MEMBER DOCUMENT MEDIA
# =========================================================
#
# IMPORTANT:
# This route MUST appear before the generic /media/
# route below.
#
# Otherwise Django's generic media server will serve
# member documents without authentication.
#

urlpatterns += [
    re_path(
        r"^media/member_documents/(?P<path>.*)$",
        serve_member_document_media,
        name="secure_member_document_media",
    ),
]

# Temporary production media serving
urlpatterns += [
    re_path(
        r"^media/(?P<path>.*)$",
        serve,
        {"document_root": settings.MEDIA_ROOT},
        name="media",
    ),
]