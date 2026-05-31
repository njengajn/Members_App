from django.contrib import admin, messages
from django.utils.html import format_html
from .models import (
    Member,
    Organization,
    Dependant,
    Claim,
    ClaimRecord,
    PaymentRequest,
    Payment,
    NextOfKin,
    ClaimRegister,
    MemberPaymentStatus,
    Address,
    ClaimSettlement,
    Notification
)
from backend.members.services.claim_service import ClaimService
from django.utils import timezone


# ==========================================================
# ORGANIZATION ADMIN (SINGLE DEFINITION)
# ==========================================================
@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "code_prefix")
    search_fields = ("name",)


# ==========================================================
# MEMBER PAYMENT STATUS INLINE
# ==========================================================
class MemberPaymentStatusInline(admin.TabularInline):
    model = MemberPaymentStatus
    extra = 0
    readonly_fields = ("uid", "member", "status", "updated_at")
    can_delete = False


# ==========================================================
# CLAIM RECORD ADMIN
# ==========================================================
@admin.register(ClaimRecord)
class ClaimRecordAdmin(admin.ModelAdmin):
    list_display = (
        "claim",
        "causer_name",
        "claimant",
        "created_at",
        "get_settlement_date",
    )

    # ---------------------------------------
    # DERIVED FIELD (3NF SAFE)
    # ---------------------------------------
    def get_settlement_date(self, obj):
        """
        Pull settlement date from ClaimSettlement (source of truth)
        """
        if hasattr(obj.claim, "settlement") and obj.claim.settlement:
            return obj.claim.settlement.settlement_date
        return "-"

    get_settlement_date.short_description = "Settlement Date"


# ==========================================================
# MEMBER PAYMENT STATUS ADMIN
# ==========================================================
@admin.register(MemberPaymentStatus)
class MemberPaymentStatusAdmin(admin.ModelAdmin):
    list_display = ("uid", "member", "payment_request", "status", "updated_at")
    list_filter = ("status", "payment_request")
    search_fields = ("member__member_uid", "member__first_name", "member__surname")


# ==========================================================
# DEPENDANT ADMIN
# ==========================================================
@admin.register(Dependant)
class DependantAdmin(admin.ModelAdmin):
    list_display = ("first_name", "surname", "relationship", "member", "status", "dob")
    list_filter = ("status", "relationship")
    search_fields = ("first_name", "surname", "member__member_uid")


# ==========================================================
# NEXT OF KIN ADMIN
# ==========================================================
@admin.register(NextOfKin)
class NextOfKinAdmin(admin.ModelAdmin):
    list_display = ("first_name", "surname", "relationship", "phone", "email")
    search_fields = ("first_name", "surname", "phone", "email")


# ==========================================================
# CLAIM ADMIN
# ==========================================================
@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    list_display = ("uid", "member", "status", "created_at")
    actions = ["approve_selected_claims"]

    def approve_selected_claims(self, request, queryset):
        for claim in queryset:
            ClaimService.approve_claim(
                claim=claim,
                approved_by=request.user,
            )

    approve_selected_claims.short_description = "Approve selected claims"


# ==========================================================
# CLAIM REGISTER ADMIN
# ==========================================================
@admin.register(ClaimRegister)
class ClaimRegisterAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "member_name",
        "causer_name",
        "claim_status",
        "created_at",
    )

    def member_name(self, obj):
        return obj.claim.member.user.get_full_name()

    def causer_name(self, obj):
        if obj.claim.cause_type == Claim.CLAIM_CAUSER_DEPENDANT and obj.claim.causer_dependant:
            return obj.claim.causer_dependant.full_name
        return obj.claim.member.user.get_full_name()

    def claim_status(self, obj):
        return obj.claim.get_status_display()


# ==========================================================
# PAYMENT ADMIN
# ==========================================================
@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("member", "amount", "payment_type", "paid_at")
    list_filter = ("member", "payment_type")
    search_fields = ("member__member_uid", "member__first_name", "member__surname")
    readonly_fields = ("payment_request",)
    ordering = ("-paid_at",)


# ==========================================================
# PAYMENT REQUEST ADMIN
# ==========================================================
@admin.register(PaymentRequest)
class PaymentRequestAdmin(admin.ModelAdmin):
    list_display = ("member", "amount", "status", "request_type", "due_date")
    list_filter = ("status", "request_type")
    search_fields = ("member__member_uid", "member__user__username")
    readonly_fields = ("created_at",)
    inlines = [MemberPaymentStatusInline]


# ==========================================================
# INLINE CLASSES
# ==========================================================
class DependantInline(admin.TabularInline):
    model = Dependant
    extra = 1
    show_change_link = True
    classes = ["collapse"]
    verbose_name_plural = "Dependants"


class NextOfKinInline(admin.StackedInline):
    model = NextOfKin
    extra = 0
    max_num = 1
    classes = ["collapse"]
    verbose_name_plural = "Next of Kin"

class RiskStatusFilter(admin.SimpleListFilter):
    title = "Payment Risk"
    parameter_name = "payment_risk"

    def lookups(self, request, model_admin):
        return (
            ("at_risk", "At Risk"),
            ("safe", "Safe"),
        )

    def queryset(self, request, queryset):
        from backend.members.models import PaymentRequest

        at_risk_ids = set()

        requests = PaymentRequest.objects.filter(
            status=PaymentRequest.STATUS_ACTIVE
        )

        for member in queryset:
            for pr in requests:
                if pr.member_payment_status(member) != "paid" and pr.is_member_overdue(member):
                    at_risk_ids.add(member.id)

        if self.value() == "at_risk":
            return queryset.filter(id__in=at_risk_ids)

        if self.value() == "safe":
            return queryset.exclude(id__in=at_risk_ids)

        return queryset

# ==========================================================
# MEMBER ADMIN
# ==========================================================
@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):

    list_display = (
        "uid_badge",
        "full_name",
        "status",
        "organization",
        "address_display",
        "uid_status",
        "due_countdown",
        "risk_status",
        "can_edit",
        "joined_at",
    )

    list_filter = ("organization", "status", "can_edit")

    search_fields = (
        "member_uid",
        "first_name",
        "surname",
        "user__username",
        "address__postcode",
    )

    ordering = ("-joined_at",)

    fieldsets = (
        ("Status & Organisation", {
            "fields": ("status", "organization", "retirement_reason")
        }),
        ("User Link", {"fields": ("user",)}),
        ("Personal Info", {
            "fields": ("first_name", "middle_name", "surname", "email", "phone", "avatar")
        }),
        ("Address", {"fields": ("address",)}),
        ("Permissions", {
            "fields": ("can_edit", "can_edit_expires_at", "is_portal_access_enabled")
        }),
        ("System Fields", {
            "fields": ("member_uid", "uid_assigned", "joined_at"),
            "classes": ("collapse",)
        }),
    )

    readonly_fields = ("member_uid", "uid_assigned", "joined_at")

    # ---------- Display helpers ----------
    def address_display(self, obj):
        return obj.address or "-"

    address_display.short_description = "Address"

    def uid_badge(self, obj):
        if obj.member_uid:
            return format_html(
                '<span style="background:#16a34a;color:white;padding:4px 8px;border-radius:6px;">{}</span>',
                obj.member_uid
            )
        return format_html(
            '<span style="background:#dc2626;color:white;padding:4px 8px;border-radius:6px;">NO UID</span>'
        )

    def uid_status(self, obj):
        if obj.status == Member.STATUS_ACTIVE and not obj.member_uid:
            return format_html('<span style="color:red;font-weight:bold;">⚠ Missing UID</span>')
        return "OK"

    # ---------- Bulk action ----------
    actions = ["assign_to_reading_org"]

    def assign_to_reading_org(self, request, queryset):
        try:
            org = Organization.objects.get(name="Reading Organisation")
        except Organization.DoesNotExist:
            self.message_user(request, "Reading Organisation not found.")
            return

        updated = queryset.update(organization=org)
        self.message_user(request, f"{updated} members assigned to Reading Organisation.")

    assign_to_reading_org.short_description = "Assign selected members to Reading Organisation"

    class Media:
        css = {
            "all": [
                "https://cdnjs.cloudflare.com/ajax/libs/flowbite/2.3.0/flowbite.min.css",
                "https://cdn.jsdelivr.net/npm/tailwindcss@3.4.1/dist/tailwind.min.css",
                "/static/admin/flowbite_admin.css",
            ]
        }
        js = [
            "https://cdnjs.cloudflare.com/ajax/libs/flowbite/2.3.0/flowbite.min.js",
            "/static/admin/flowbite_admin.js",
        ]
        
    def risk_status(self, obj):
        """
        Shows if member is at risk of retirement:
        - has overdue payment
        - AND is unpaid
        """

        from backend.members.models import PaymentRequest

        requests = PaymentRequest.objects.filter(
            status=PaymentRequest.STATUS_ACTIVE
        )

        for pr in requests:
            if pr.member_payment_status(obj) != "paid" and pr.is_member_overdue(obj):
                return format_html(
                    '<span style="color:white;background:#dc2626;padding:4px 8px;border-radius:6px;">AT RISK</span>'
                )

        return format_html(
            '<span style="color:white;background:#16a34a;padding:4px 8px;border-radius:6px;">SAFE</span>'
        )

    risk_status.short_description = "Risk"
    
    def due_countdown(self, obj):
        """
        Countdown to due date:
        - shows days remaining
        - overdue status
        """

        now = timezone.now()

        requests = PaymentRequest.objects.filter(
            status=PaymentRequest.STATUS_ACTIVE
        )

        for pr in requests:

            if pr.member_payment_status(obj) == "paid":
                continue

            if not pr.due_date:
                continue

            delta = pr.due_date - now
            days = delta.days

            if days < 0:
                return format_html(
                    '<span style="background:#dc2626;color:white;padding:4px 8px;border-radius:6px;">OVERDUE</span>'
                )

            if days == 0:
                return format_html(
                    '<span style="background:#f59e0b;color:white;padding:4px 8px;border-radius:6px;">DUE TODAY</span>'
                )

            return format_html(
                f'<span style="background:#2563eb;color:white;padding:4px 8px;border-radius:6px;">{days}d left</span>'
            )

        return "-"
    
    
    def save_related(self, request, form, formsets, change):
        """
        Enforce dependant lifecycle rules.
        """

        super().save_related(request, form, formsets, change)

        member = form.instance

        # -----------------------------------
        # RULE: dependants cannot be active if member is retired
        # -----------------------------------
        if member.status == Member.STATUS_RETIRED:
            updated = member.dependants.filter(status="active").update(status="retired")

            if updated:
                self.message_user(
                    request,
                    "Dependants cannot be active while member is retired.",
                    level=messages.WARNING
                )
                
    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status == Member.STATUS_RETIRED:
            return self.readonly_fields + ("status",)
        return self.readonly_fields


# ==========================================================
# ADDRESS ADMIN
# ==========================================================
@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("house_number", "line_1", "town", "postcode", "country")
    search_fields = ("house_number", "line_1", "line_2", "town", "county", "postcode")
    list_filter = ("town", "county", "postcode", "country")
    ordering = ("town", "line_1")


# ==========================================================
# CLAIM SETTLEMENT ADMIN
# ==========================================================
@admin.register(ClaimSettlement)
class ClaimSettlementAdmin(admin.ModelAdmin):

    list_display = (
        "claim",
        "get_causer",
        "created_at",
        "settlement_date",
        "get_amount_paid",
    )

    readonly_fields = (
        "created_at",
        "get_total_collected",
        "get_amount_paid",
    )

    def get_causer(self, obj):
        return obj.claim.causer_full_name

    def get_total_collected(self, obj):
        return obj.total_collected

    def get_amount_paid(self, obj):
        return obj.amount_paid

    get_causer.short_description = "Causer"
    get_total_collected.short_description = "Total Collected"
    get_amount_paid.short_description = "Amount Paid"
    
    
# =========================================================
# NOTIFICATIONS ADMIN
# =========================================================

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "title",
        "notification_type",
        "is_read",
        "created_at",
    )

    list_filter = (
        "notification_type",
        "is_read",
    )

    search_fields = (
        "user__username",
        "title",
        "message",
    )

    readonly_fields = (
        "created_at",
    )

    ordering = (
        "-created_at",
    )