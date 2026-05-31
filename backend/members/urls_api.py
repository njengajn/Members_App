from django.urls import path

from backend.members.views_api import (
    api_member_list,
    api_member_detail,
    api_update_status,
)

app_name = "api"

urlpatterns = [

    path("members/", api_member_list, name="member_list"),
    path("members/<int:member_id>/", api_member_detail, name="member_detail"),
    path("members/<int:member_id>/status/", api_update_status, name="update_status"),
]
