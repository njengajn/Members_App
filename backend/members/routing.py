from django.urls import re_path
from .consumers import AuditLogConsumer

websocket_urlpatterns = [
    re_path(r'ws/audit-logs/$', AuditLogConsumer.as_asgi()),
]