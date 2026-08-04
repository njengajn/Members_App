# backend/core/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from django.views.static import serve
from django.urls import re_path

urlpatterns = [
    path("", include(("backend.members.urls_frontend", "members"), namespace="members")),
    path("admin/", admin.site.urls),
    path("admin-panel/", include(("backend.members.urls_admin", "members_admin"), namespace="members_admin")),
    path("ajax/", include(("backend.members.urls_ajax", "ajax"), namespace="ajax")),
    path("api/", include(("backend.members.urls_api", "api"), namespace="api")),
]

# Static (development)
urlpatterns += static(
    settings.STATIC_URL,
    document_root=settings.BASE_DIR / "static",
)


# Media (TEMPORARY TEST)
urlpatterns += static(
    settings.MEDIA_URL,
    document_root=settings.MEDIA_ROOT,
)


urlpatterns += [
    re_path(
        r"^media/(?P<path>.*)$",
        serve,
        {"document_root": settings.MEDIA_ROOT},
        name="media",
    ),
]