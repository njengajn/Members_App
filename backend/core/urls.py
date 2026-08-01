# backend/core/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [

    # -----------------------------
    # Member-facing frontend
    # -----------------------------
    path("", include(("backend.members.urls_frontend", "members"), namespace="members")),

    # -----------------------------
    # Django built-in admin (default)
    # -----------------------------
    path("admin/", admin.site.urls),

    # -----------------------------
    # Custom admin portal (separate from Django admin)
    # -----------------------------
    path("admin-panel/", include(("backend.members.urls_admin", "members_admin"), namespace="members_admin")),

    # -----------------------------
    # AJAX
    # -----------------------------
    path("ajax/", include(("backend.members.urls_ajax", "ajax"), namespace="ajax")),

    # -----------------------------
    # API
    # -----------------------------
    path("api/", include(("backend.members.urls_api", "api"), namespace="api")),

]

# Static files (dev only)
urlpatterns += static(settings.STATIC_URL, document_root=settings.BASE_DIR / "static")

# ======================================================
# SERVE MEDIA FILES IN DEVELOPMENT
# ======================================================
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
