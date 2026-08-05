# backend/core/urls.py

from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve

urlpatterns = [
    path("", include(("backend.members.urls_frontend", "members"), namespace="members")),
    path("admin/", admin.site.urls),
    path("admin-panel/", include(("backend.members.urls_admin", "members_admin"), namespace="members_admin")),
    path("ajax/", include(("backend.members.urls_ajax", "ajax"), namespace="ajax")),
    path("api/", include(("backend.members.urls_api", "api"), namespace="api")),
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