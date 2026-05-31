# backend/members/security/admin.py

from django.contrib import admin
from backend.members.models import AccountLock


@admin.register(AccountLock)
class AccountLockAdmin(admin.ModelAdmin):

    list_display = ("user", "locked_until", "reason")

    actions = ["unlock_accounts"]

    def unlock_accounts(self, request, queryset):
        queryset.delete()