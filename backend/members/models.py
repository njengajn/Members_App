from django.db import models
from django.conf import settings
from django.forms import ValidationError
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
import uuid
from django.db.models import Max
from django.db.models import Sum
from datetime import timedelta
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth import get_user_model
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


class Organization(models.Model):
    """
    Each organization has its own UID prefix.
    Example:
        KRC- (Karate Club)
        KRO- (Default Org)
    """
    name = models.CharField(max_length=100)

    # Prefix must be unique per organization
    code_prefix = models.CharField(
        max_length=10,
        unique=True,
        default=settings.DEFAULT_MEMBER_PREFIX
    )

    address = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name


class Member(models.Model):
    """
    Member model with controlled UID generation.
    UID is ONLY assigned when member becomes ACTIVE.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="member"
    )

    # -----------------------------
    # STATUS
    # -----------------------------
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_ACTIVE = "active"
    STATUS_RETIRED = "retired"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_RETIRED, "Retired"),
    ]

    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING
    )

    # -----------------------------
    # ORGANIZATION
    # -----------------------------
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="members"
    )

    # -----------------------------
    # UID
    # -----------------------------
    member_uid = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        null=True,
        editable=False
    )

    # Prevent UID being regenerated
    uid_assigned = models.BooleanField(default=False)

    # -----------------------------
    # PERSONAL INFO
    # -----------------------------
    first_name = models.CharField(max_length=200, default="")
    middle_name = models.CharField(max_length=100, blank=True, null=True)
    surname = models.CharField(max_length=200, default="")
    dob = models.DateField()
    phone = models.CharField(max_length=32, blank=True, default="")
    email = models.EmailField(unique=True,  blank=True, null=True,help_text="Automatically synchronised with related User email.")
    address = models.ForeignKey("Address", on_delete=models.SET_NULL, null=True, blank=True, related_name="members")
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)
    applied_at = models.DateTimeField(auto_now_add=True,db_index=True,help_text="Date the application was submitted.")
    joined_at = models.DateTimeField(null=True, blank=True, db_index=True, help_text="Date membership was activated.")
    can_edit = models.BooleanField(default=False, help_text="Allow member to add/edit dependants")
    can_edit_expires_at = models.DateTimeField(null=True, blank=True )
    is_portal_access_enabled = models.BooleanField(default=True)
    retirement_reason = models.CharField(max_length=255, blank=True, null=True) 
    subscription_year = models.PositiveIntegerField(blank=True, null=True)
    retired_reason = models.TextField(blank=True, null=True)
    """
    Timestamp member was retired.
    """
    retired_at = models.DateTimeField(blank=True, null=True)
    # ======================================================
    # GDPR / DATA PROTECTION
    # ======================================================

    gdpr_consent = models.BooleanField(default=False)
    gdpr_consent_at = models.DateTimeField(null=True, blank=True)
    gdpr_consent_ip = models.GenericIPAddressField(null=True, blank=True)
    gdpr_version = models.CharField(max_length=20, default="v1")    
    
    def enable_can_edit(self):
        """
        Enable editing for 24 hours
        """
        self.can_edit = True
        self.can_edit_expires_at = timezone.now() + timedelta(hours=24)
        self.save()

    def disable_can_edit(self):
        """
        Disable editing
        """
        self.can_edit = False
        self.can_edit_expires_at = None
        self.save()

    def check_can_edit_expiry(self):
        """
        Auto-expire logic (safe check)
        """
        if self.can_edit and self.can_edit_expires_at:
            if timezone.now() > self.can_edit_expires_at:
                self.disable_can_edit()

    # -----------------------------
    # SAVE LOGIC
    # -----------------------------
    def save(self, *args, **kwargs):
        """
        Central Member save logic.

        Business Rules
        ------------------------------------------------------------------
        • User.email is the master email address.
        • Member.email mirrors User.email.
        • UID is allocated only on first transition to ACTIVE.
        • uid_assigned prevents UID regeneration.
        """

        previous = None

        if self.pk:
            try:
                previous = Member.objects.get(pk=self.pk)
            except Member.DoesNotExist:
                previous = None

        becoming_active = (
            self.status == self.STATUS_ACTIVE
            and (
                previous is None
                or previous.status != self.STATUS_ACTIVE
            )
        )

        # ------------------------------------------------------
        # SYNCHRONISE EMAIL
        # ------------------------------------------------------

        if self.user_id:
            self.email = self.user.email

        # ------------------------------------------------------
        # FIRST ACTIVATION → UID
        # ------------------------------------------------------

        if becoming_active and not self.uid_assigned:

            from backend.members.utils.member_uid import (
                generate_member_uid
            )

            self.member_uid = generate_member_uid(
                self.organization
            )

            self.uid_assigned = True

        super().save(*args, **kwargs)

        # -----------------------------
        # HELPERS
        # -----------------------------
        
    @property
    def full_name(self):
     return f"{self.first_name} {self.surname}".strip()
  
    def __str__(self):
        return self.full_name

    # ======================================================
    # LIFECYCLE METHODS (PHASE 2 - SAFE)
    # ======================================================

    # =====================================================
    # RETIRE MEMBER
    # =====================================================

    def retire(
        self,
        reason="system",
        payment_request=None,
        admin_user=None,
    ):
        """
        Central lifecycle method.

        Used by:
        - payment lifecycle
        - admin actions
        - auto retirement

        RULE:
        member + dependants ALWAYS synced
        """

        if self.status == self.STATUS_RETIRED:
            return

        # =============================================
        # MEMBER
        # =============================================

        self.status = self.STATUS_RETIRED

        # New field
        self.retired_reason = reason

        # Legacy compatibility
        self.retirement_reason = reason

        self.retired_at = timezone.now()

        self.save(
            update_fields=[
                "status",
                "retired_reason",
                "retirement_reason",
                "retired_at",
            ]
        )

        # =============================================
        # MEMBERSHIP HISTORY
        # =============================================

        MembershipStatusHistory.objects.create(
            member=self,
            action="retired",
            reason=reason,
            performed_by=admin_user,
        )

        # =============================================
        # DEPENDANTS
        # =============================================

        self.dependants.update(
            status="retired"
        )

        # =============================================
        # LOCK ACCOUNT
        # =============================================

        if hasattr(self, "user") and self.user:

            if self.user.is_active:

                self.user.is_active = False

                self.user.save(
                    update_fields=["is_active"]
                )

        # =============================================
        # AUDIT
        # =============================================

        AuditLog.objects.create(
            admin=admin_user,
            action="member_retired",
            target_member=self,
            message=f"Member retired ({reason})"
        )

    # =====================================================
    # RESTORE MEMBER
    # =====================================================

    def restore(self, admin_user=None, reason="Member restored by administrator",):
        """
        Restore member + dependants.
        """

        if self.status != self.STATUS_RETIRED:
            return

        # =====================================
        # RESTORE MEMBER
        # =====================================

        self.status = self.STATUS_ACTIVE

        # Reactivation starts a new membership/claim eligibility period.
        self.joined_at = timezone.now()

        # Portal access is restored.
        self.is_portal_access_enabled = True

        # Clear retirement fields.
        self.retired_reason = None
        self.retirement_reason = None
        self.retired_at = None

        self.save(
            update_fields=[
                "status",
                "joined_at",
                "is_portal_access_enabled",
                "retired_reason",
                "retirement_reason",
                "retired_at",
            ]
        )

        # =====================================
        # RECORD MEMBERSHIP HISTORY
        # =====================================

        MembershipStatusHistory.objects.create(
            member=self,
            action="reactivated",
            reason=reason,
            performed_by=admin_user,
        )

        # =====================================
        # RESTORE DEPENDANTS
        # =====================================

        self.dependants.update(
            status="active"
        )

        # =====================================
        # UNLOCK ACCOUNT
        # =====================================

        if hasattr(self, "user") and self.user:

            if not self.user.is_active:

                self.user.is_active = True

                self.user.save(
                    update_fields=["is_active"]
                )

        # =====================================
        # AUDIT
        # =====================================

        AuditLog.objects.create(
            admin=admin_user,
            action="member_restored",
            target_member=self,
            message=(
                "Member restored "
                "(dependants restored)"
            )
        )

        # =====================================================
    # MEMBERSHIP VALIDITY
    # =====================================================

    def is_valid(self):
        """
        Membership validity based on:
        June 1st annual subscription cycle.

        RULES:
        Jan-May:
            previous year payment still valid

        June onwards:
            current year payment required
        """

        now = timezone.now()

        current_year = now.year

        # -------------------------------------
        # BEFORE JUNE
        # -------------------------------------

        if now.month < 6:

            required_year = current_year - 1

        # -------------------------------------
        # JUNE OR LATER
        # -------------------------------------

        else:

            required_year = current_year

        return (
            self.status == self.STATUS_ACTIVE and
            self.subscription_year == required_year
        )

       
    @property
    def can_make_claim(self):
        """
        Returns True only when the member is currently ACTIVE
        and has completed the 180-day claim cooling-off period.
        """

        if self.status != self.STATUS_ACTIVE:
            return False

        if not self.joined_at:
            return False

        return timezone.now() >= (
            self.joined_at + timedelta(days=180)
        )
    

    @property
    def membership_age_days(self):
        """
        Number of days since the member's current activation.

        Pending members have no active membership period.
        Retired members are not currently active.
        """

        if self.status != self.STATUS_ACTIVE:
            return None

        if not self.joined_at:
            return None

        return (timezone.now() - self.joined_at).days
    
    @property
    def claim_eligibility_date(self):
        """
        Date the currently active member completes
        the 180-day claim cooling-off period.
        """

        if self.status != self.STATUS_ACTIVE:
            return None

        if not self.joined_at:
            return None

        return self.joined_at + timedelta(days=180)


    
    @property
    def claim_progress_percent(self):
        """
        Progress through the 180-day cooling-off period.

        Returns:
            int: 0-100
        """
        if not self.joined_at:
            return 0

        days = self.membership_age_days or 0

        return min(round((days / 180) * 100), 100)


    @property
    def days_until_claim(self):
        """
        Number of days remaining before the currently active
        member becomes eligible to submit a claim.
        """

        if self.status != self.STATUS_ACTIVE:
            return None

        if not self.joined_at:
            return None

        remaining = 180 - (
            self.membership_age_days or 0
        )

        return max(remaining, 0)


class NextOfKin(models.Model):
    member = models.OneToOneField(Member, on_delete=models.CASCADE, related_name="next_of_kin")
    first_name = models.CharField(max_length=100, default="")
    middle_name = models.CharField(max_length=100, blank=True, null=True)
    surname = models.CharField(max_length=100, default="")
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(max_length=100, default="")
    relationship = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    
    def full_name(self):
        return f"{self.first_name} {self.middle_name} {self.surname} ({self.relationship})"
    
    def __str__(self):
        return self.full_name()


class Dependant(models.Model):
     
    TYPE_SPOUSE = "SPOUSE"
    TYPE_CHILD = "CHILD"
    TYPE_SIBLING = "SIBLING"
    TYPE_PARENT = "PARENT"
    RELATIONSHIP_TYPE_CHOICES = [
        (TYPE_SPOUSE, "Spouse"),
        (TYPE_CHILD, "Child"),
        (TYPE_SIBLING, "Sibling"),
        (TYPE_PARENT, "Parent"),
    ]
    STATUS_ACTIVE = "active"
    STATUS_PENDING = "pending"
    STATUS_RETIRED = "retired"
    DEP_STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_PENDING, "pending"),
        (STATUS_RETIRED, "Retired"),
        
    ]

    member = models.ForeignKey("Member", related_name="dependants", on_delete=models.CASCADE)
    first_name = models.CharField(max_length=50, default="")
    middle_name = models.CharField(max_length=50, blank=True, null=True)
    surname = models.CharField(max_length=50, default="")
    relationship = models.CharField(max_length=50, choices=RELATIONSHIP_TYPE_CHOICES, blank=True)
    dob = models.DateField()
    status = models.CharField(max_length=16, choices=DEP_STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)


    def full_name(self):
        return f"{self.first_name} {self.surname} ({self.relationship})"

    def __str__(self):
        return f"{self.full_name()} — {self.relationship} of {self.member}"
    
# ======================================================
# ADDRESS MODEL
# ======================================================

class Address(models.Model):
    """
    Reusable address model.
    One address can be linked to multiple members.
    """

    house_number = models.CharField(
        max_length=50,
        help_text="House number or name"
    )

    line_1 = models.CharField(max_length=255)
    line_2 = models.CharField(max_length=255, blank=True)

    town = models.CharField(max_length=100)
    county = models.CharField(max_length=100, blank=True)
    postcode = models.CharField(max_length=10)
    country = models.CharField(max_length=100, default="UK")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (
            "house_number",
            "line_1",
            "town",
            "postcode",
        )

    def __str__(self):
        return f"{self.house_number}, {self.line_1}, {self.town} {self.postcode}"
    

class Claim(models.Model):
     # Claim lifecycle statuses
    STATUS_RECEIVED = "received"
    STATUS_OPEN = "open"
    STATUS_APPROVED = "approved"
    STATUS_SETTLED = "settled"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = [
        (STATUS_RECEIVED, "Received"),
        (STATUS_OPEN, "Open"),
        (STATUS_SETTLED, "Settled"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_APPROVED, "Approved"),
    ]
    
    CLAIM_CAUSER_MEMBER = "member"
    CLAIM_CAUSER_DEPENDANT = "dependant"
    CAUSE_TYPE_CHOICES = [
        (CLAIM_CAUSER_MEMBER, "Member"),
        (CLAIM_CAUSER_DEPENDANT, "Dependant"),
    ]
    

    uid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False) 
    member = models.ForeignKey("Member", on_delete=models.CASCADE, related_name="claims")    # the claimant (member who files the claim)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="received")
    
    # Claimer — who is making the claim (either the member themselves or the member's next of kin).
    # The form should allow only the member or the member.next_of_kin full_name
    claimer = models.CharField(max_length=200, default="") # Cause: whether the causer is the member or one of their dependants
    causer_full_name = models.CharField(max_length=200, default="")
    cause_type = models.CharField(max_length=40, choices=CAUSE_TYPE_CHOICES, default= "dependant")  # Cause: whether the causer is the member or one of their dependants
    claimer_is_next_of_kin = models.BooleanField(default=False)
    causer_dependant = models.ForeignKey(
        "Dependant", on_delete=models.SET_NULL, null=True, blank=True, related_name="caused_claims")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="claims_created", on_delete=models.SET_NULL, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    VALID_TRANSITIONS = {
        STATUS_RECEIVED: [STATUS_OPEN, STATUS_REJECTED],
        STATUS_OPEN: [STATUS_SETTLED],
        STATUS_SETTLED: [],
        STATUS_REJECTED: [],
    }
    settled = models.BooleanField(default=False)
    
    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    def transition_to(self, new_status, *, by_user=None):
        if not self.can_transition_to(new_status):
            raise ValidationError(
                f"Invalid transition from {self.status} → {new_status}"
            )
        self.status = new_status
        self.save(update_fields=["status"])

    def save(self, *args, **kwargs):
        try:
            uuid.UUID(str(self.uid))
        except (ValueError, TypeError, AttributeError):
            self.uid = uuid.uuid4()
        super().save(*args, **kwargs)

    
    def __str__(self):

        # If dependant is the cause
        if self.cause_type == self.CLAIM_CAUSER_DEPENDANT and self.causer_dependant:
            return f"Claim - {self.causer_dependant.full_name}"

        # Default: member
        if self.member:
            return f"Claim - {self.member.member_uid} {self.member.full_name}"

        return f"Claim #{self.id}"
    
        
    def clean(self):
        """
        VALIDATION RULES:
        - Dependant required if cause_type = dependant
        - Member claim must NOT have dependant
        - ONLY ONE CLAIM PER DEPENDANT (GLOBAL)
        """

    # ----------------------------------------
    # CAUSE VALIDATION
    # ----------------------------------------
        if self.cause_type == self.CLAIM_CAUSER_DEPENDANT and not self.causer_dependant:
            raise ValidationError("Dependant must be selected.")

        if self.cause_type == self.CLAIM_CAUSER_MEMBER and self.causer_dependant:
            raise ValidationError("Member claim cannot have a dependant.")

    # ----------------------------------------
    # ONE CLAIM PER DEPENDANT
    # ----------------------------------------
        if self.causer_dependant:
            existing = Claim.objects.filter(causer_dependant=self.causer_dependant)

            # Exclude self when editing
            if self.pk:
                existing = existing.exclude(pk=self.pk)

            if existing.exists():
                raise ValidationError("This dependant already has a claim.")
            
    def is_settled(self):
        return hasattr(self, "settlement")
    
class ClaimRecord(models.Model):
    """
    ClaimRecord is a record associated with a Claim once it becomes OPEN, and updated when SETTLED.
    Admin-only create/update (but auto-created by signal when Claim goes to OPEN).
    """
    claim = models.OneToOneField(Claim, related_name="record", on_delete=models.CASCADE)
    causer_name = models.CharField(max_length=200)
    claimant = models.ForeignKey("Member", related_name="claim_records", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"ClaimRecord for {self.claim.uid}"
    
class PaymentRequest(models.Model):

    REQUEST_TYPES = [
        ("membership", "Membership"),
        ("subscription", "Subscription"),
        ("claim", "Claim"),
        ("other", "Other"),
    ]

    STATUS_ACTIVE = "active"
    STATUS_CLOSED = "closed"
    STATUS_ARCHIVED = "archived"
    

    STATUS_CHOICES = [
        ("active", "Active"),
        ("closed", "Closed"),
        ("archived", "Archived"),
    ]
 
    # =========================
    # PAYMENT METHODS
    # =========================
    METHOD_MANUAL = "manual"
    METHOD_CARD = "card"
    METHOD_BOTH = "both"

    PAYMENT_METHOD_CHOICES = [
        (METHOD_MANUAL, "Manual (Bank Transfer)"),
        (METHOD_CARD, "Card (Stripe)"),
        (METHOD_BOTH, "Both"),
    ]

    uid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    member = models.ForeignKey(
        "Member",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="payment_requests",
    )

    claim = models.OneToOneField(
        "Claim",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_request"
    )

    days = models.PositiveIntegerField(default=3)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    due_date = models.DateTimeField()
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
    )
    request_type = models.CharField(
        max_length=32,
        choices=REQUEST_TYPES,
        default="claim",
    )
    authorised_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authorized_payment_requests",
    )
    viewable_by_all = models.BooleanField(default=True)
    selected_members = models.ManyToManyField(
        "Member",
        related_name="selected_payment_requests",
        blank=True,
    )
    paid_members = models.ManyToManyField(
        "Member",
        related_name="paid_payment_requests",
        blank=True,
    )
    payment_method = models.CharField(
        max_length=10,
        choices=PAYMENT_METHOD_CHOICES,
        default=METHOD_BOTH
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    admin_notes = models.TextField(blank=True)
    title = models.CharField(max_length=255)
    
    # =====================================================
    # RECONCILIATION TRACKING
    # =====================================================

    is_reconciled = models.BooleanField(default=False)

    reconciled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reconciled_requests"
    )
    reconciled_at = models.DateTimeField(
        null=True,
        blank=True
    )
    
    # =====================================================
    # ARCHIVE TRACKING
    # =====================================================

    archived_at = models.DateTimeField(
        null=True,
        blank=True
    )
    
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="archived_payment_requests",
    )
    send_notifications = models.BooleanField(
        default=True,
        help_text=(
            "Send notifications when this "
            "payment request is created."
        ),
    )

    # -----------------------------
    #  Correct helpers
    # -----------------------------

    def is_fully_paid(self):
        """
        Only meaningful for restricted requests.
        """
        if self.viewable_by_all:
            return False
        return (
            self.selected_members.exists()
            and self.selected_members.count() == self.paid_members.count()
        )
        
    def member_payment_status(self, member):
        """
        SINGLE SOURCE OF TRUTH

        PRIORITY:
        1. pending
        2. completed
        3. unpaid
        """

        if self.payments.filter(
            member=member,
            status=Payment.STATUS_PENDING
        ).exists():
            return "pending"

        if self.payments.filter(
            member=member,
            status=Payment.STATUS_COMPLETED
        ).exists():
            return "paid"

        return "unpaid"

    @property
    def total_paid(self):
        return self.payments.filter(
            status=Payment.STATUS_COMPLETED
        ).aggregate(
            total=Sum("amount")
        )["total"] or 0

        
    @property
    def is_overdue(self):
        """
        GLOBAL overdue (request-level)
        """
        return (
            self.status == self.STATUS_ACTIVE and
            self.due_date and
            self.due_date < timezone.now()
        )
        
    def is_partially_paid(self):
        """
        At least one payment exists but not fully paid.
        """
        return self.payments.filter(
            status=Payment.STATUS_COMPLETED
        ).exists() and not self.is_fully_paid()
        
    def is_member_overdue(self, member):
        """
        MEMBER-SPECIFIC overdue (CRITICAL FIX)
        """

        # 🚫 NEVER overdue if already paid
        if self.member_payment_status(member) == "paid":
            return False

        return self.is_overdue

        
    def save(self, *args, **kwargs):
        skip_validation = kwargs.pop("skip_validation", False)

        if not skip_validation:
            self.full_clean()

        super().save(*args, **kwargs)

    @property
    def payment_progress_percent(self):
        if self.amount == 0:
            return 0
        return int((self.total_paid / self.amount) * 100)

    def __str__(self):
        return f"{self.title} - {self.amount}"
    
    def is_completed(self):
        """
        ONLY completed when fully paid
        """

        if not self.viewable_by_all:
            if self.selected_members.exists():
                return self.selected_members.count() == self.paid_members.count()

        # global requests
        return self.total_paid >= self.amount
     
    def paid_member_statuses(self):
        return MemberPaymentStatus.objects.filter(
            payment_request=self,
            status=MemberPaymentStatus.STATUS_PAID
    )
    
    @property
    def lifecycle_status(self):
        """
        Derived status for UI/dashboard.
        """

        if self.is_completed():
            if self.is_fully_paid():
                return "completed_full"
            return "completed_partial"

        if self.is_partially_paid():
            return "in_progress"

        return "pending"
    
    @property
    def is_archived(self):
        return self.status == "archived"

    @property
    def is_active(self):
        return self.status == "active"

class Payment(models.Model):
    # ======================================================
    # WHAT the payment is for
    # ======================================================
    PAYMENT_TYPES = [
        ("membership", "Membership Fee"),
        ("subscription", "Subscription"),
        ("claim", "Claim Payment"),
        ("other", "Other"),
    ]

    # ======================================================
    # HOW the payment was made
    # ======================================================
    PAYMENT_METHODS = [
        ("manual", "Manual (Bank Transfer)"),
        ("card", "Card Payment"),
    ]

    # ======================================================
    # STATUS
    # ======================================================
    STATUS_PENDING = "pending"
    STATUS_COMPLETED = "completed"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_REJECTED, "Rejected"),
    ]

    uid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    payment_request = models.ForeignKey(PaymentRequest, related_name="payments", on_delete=models.CASCADE, null=True, blank=True)
    member = models.ForeignKey("Member", related_name="payments", on_delete=models.CASCADE)
    member_uid_snapshot = models.CharField(max_length=64, blank=True)  # snapshot UID for audit
    full_name_snapshot = models.CharField(max_length=200, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_type = models.CharField(max_length=32, choices=PAYMENT_TYPES)
    paid_at = models.DateTimeField(auto_now_add=True)
    # nullable for manual payments
    external_payment_id = models.CharField(max_length=255, unique=True, null=True, blank=True, help_text="Stripe/Paypal ID etc.")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="approved_payments")
    approved_at = models.DateTimeField(null=True, blank=True)
    proof = models.FileField(upload_to="payment_proofs/", null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_payments")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    payment_method = models.CharField(max_length=20,choices=PAYMENT_METHODS, default="manual"    )
    updated_at = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):
        """
        Unified save method:
        ✔ snapshots
        ✔ validation
        """
        # Snapshot UID 
        if not self.member_uid_snapshot:
            self.member_uid_snapshot = str(self.member.member_uid)

        # Snapshot name 
        if not self.full_name_snapshot:
            if hasattr(self.member, "user") and self.member.user:
                self.full_name_snapshot = (
                    self.member.user.get_full_name()
                    or self.member.user.username
                )
            else:
                self.full_name_snapshot = str(self.member)

        # Validation
        self.full_clean()

        super().save(*args, **kwargs)
        
    def clean(self):
        if self.payment_type == "claim" and not self.payment_request:
            raise ValidationError("Claim payments must be linked to a PaymentRequest.")
        
    class Meta:
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["payment_type"]),
            models.Index(fields=["paid_at"]),
    ]

    ALLOWED_TRANSITIONS = {
        STATUS_PENDING: {STATUS_COMPLETED, STATUS_REJECTED},
        STATUS_COMPLETED: set(),
        STATUS_REJECTED: set(),
    }
    
    class Meta:
        unique_together = ("member", "payment_request")

    def __str__(self):
        return f"Payment {self.id} by {self.member} amount {self.amount}"


class MemberPaymentStatus(models.Model):
    """
    Tracks per-member per-payment-request status. 
    Note: Member.status (pending/active/retired) is separate from this. This is in memeber class
    MemberPaymentStatus.status choices are only 'paid' or 'unpaid'.
    """
    STATUS_PAID = "paid"
    STATUS_UNPAID = "unpaid"
    STATUS_CHOICES = [
        (STATUS_PAID, "Paid"),
        (STATUS_UNPAID, "Unpaid"),
    ]

    uid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    member = models.ForeignKey("Member", on_delete=models.CASCADE, related_name="payment_statuses")
    payment_request = models.ForeignKey(PaymentRequest, on_delete=models.CASCADE, related_name="member_statuses")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_UNPAID)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("member", "payment_request")

    def __str__(self):
        return f"{self.member} - {self.payment_request} ({self.status})"


class ClaimRegister(models.Model):
    uid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    claim = models.ForeignKey("Claim", on_delete=models.CASCADE, related_name="claim_registers")
    paid_members = models.ManyToManyField(Member, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=200, default="")

    def add_paid_member(self, member: Member):
        self.paid_members.add(member)

    def paid_member_names(self):
        return [str(m) for m in self.paid_members.all()]

    def __str__(self):
        return f"Register for claim {self.claim.uid}"
    
    def retire_causer(self):
        """Apply business rules for retirement."""
        if self.causer_dependant:
            self.causer_dependant.status = 'retired'
            self.causer_dependant.save()
        elif self.causer_member:
            self.causer_member.status = 'retired'
            self.causer_member.save()
            for dep in self.causer_member.dependants.all():
                dep.status = 'retired'
                dep.save()
                

# Safe, canonical helpers

def paid_member_ids(payment_request):
    return set(
        payment_request.payments.filter(
            status=Payment.STATUS_COMPLETED
        ).values_list("member_id", flat=True)
    )


def unpaid_members(payment_request):
    if payment_request.viewable_by_all:
        eligible = Member.objects.all()
    else:
        eligible = payment_request.selected_members.all()

    paid_ids = paid_member_ids(payment_request)
    return eligible.exclude(id__in=paid_ids)

class MemberDocument(models.Model):
    """
    Core document model used across:
    - Member uploads
    - Admin requested documents
    - Claim attachments
    - Dependant documents
    """

    # ======================================================
    # STATUS MANAGEMENT
    # ======================================================
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    # ======================================================
    # RELATIONSHIPS
    # ======================================================

    # Main member owner
    member = models.ForeignKey(
        "members.Member",
        on_delete=models.CASCADE,
        related_name="documents",
        db_index=True,
    )

    # Optional dependant (child/spouse etc.)
    dependant = models.ForeignKey(
        "members.Dependant",
        on_delete=models.CASCADE,
        related_name="documents",
        null=True,
        blank=True,
        help_text="Attach document to a dependant if applicable",
    )

    # Optional claim linkage
    claim = models.ForeignKey(
        "members.Claim",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
        help_text="Attach document to a specific claim",
    )

    # Linked admin request
    document_request = models.ForeignKey(
        "members.DocumentRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_documents",
        help_text="If uploaded in response to admin request",
    )

    # ======================================================
    # CONTENT
    # ======================================================
    title = models.CharField(
        max_length=255
    )

    description = models.TextField(
        blank=True
    )

    file = models.FileField(
        upload_to="member_documents/%Y/%m/",
    )

    thumbnail = models.ImageField(
        upload_to="member_documents/%Y/%m/thumbnails/",
        null=True,
        blank=True,
        help_text=(
            "Private thumbnail generated for image documents. "
            "Access through the secure document thumbnail endpoint."
        ),
    )

    # ======================================================
    # STATUS & AUDIT
    # ======================================================
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )

    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_member_documents",
    )

    # ======================================================
    # REJECTION / RESUBMISSION
    # ======================================================
    rejection_reason = models.TextField(
        blank=True,
        help_text="Reason provided when document is rejected",
    )
    
    admin_notes = models.TextField(
        blank=True,
        help_text="Internal notes added by administrators during review."
    )

    can_resubmit = models.BooleanField(
        default=False,
        help_text="Allow member to upload replacement document",
    )

    resubmitted_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    
    original_filename = models.CharField(max_length=255, blank=True,)

    # ======================================================
    # SECURITY / VISIBILITY
    # ======================================================
    is_private = models.BooleanField(
        default=True,
        help_text=(
            "Documents are private and only viewable "
            "by the owning member and admins."
        ),
    )
    
    # ======================================================
    # ARCHIVING
    # ======================================================
    is_archived = models.BooleanField(
        default=False,
        db_index=True,
    )

    archived_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    # ======================================================
    # DISPLAY
    # ======================================================
    class Meta:
        ordering = ["-uploaded_at"]

        indexes = [
            models.Index(fields=["member", "status"]),
            models.Index(fields=["uploaded_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        target = self.dependant if self.dependant else self.member
        return f"{target} - {self.title}"

    # ======================================================
    # HELPERS
    # ======================================================
    @property
    def filename(self):
        """
        Returns clean filename.
        """
        if not self.file:
            return ""

        return self.file.name.split("/")[-1]

    @property
    def file_extension(self):
        """
        Returns normalized extension.
        """
        if not self.file:
            return ""

        return self.file.name.split(".")[-1].lower()

    @property
    def file_type(self):
        """
        Returns normalized file type for UI rendering.
        """

        ext = self.file_extension

        if ext in ["jpg", "jpeg", "png", "gif", "webp"]:
            return "image"

        if ext in ["pdf"]:
            return "pdf"

        if ext in ["zip", "rar", "7z"]:
            return "archive"

        if ext in ["doc", "docx"]:
            return "word"

        if ext in ["xls", "xlsx"]:
            return "excel"

        return "file"

    @property
    def is_image(self):
        return self.file_type == "image"

    @property
    def is_pdf(self):
        return self.file_type == "pdf"

    @property
    def is_pending(self):
        return self.status == self.STATUS_PENDING

    @property
    def is_approved(self):
        return self.status == self.STATUS_APPROVED

    @property
    def is_rejected(self):
        return self.status == self.STATUS_REJECTED

    @property
    def has_request(self):
        """
        Whether document is linked to admin request.
        """
        return self.document_request is not None

    # ======================================================
    # VALIDATION
    # ======================================================
    def clean(self):
        """
        Prevent cross-member request attachment.
        Critical security validation.
        """

        # ==================================================
        # Ensure linked request belongs to same member
        # ==================================================
        if self.document_request:

            if self.document_request.member != self.member:
                raise ValidationError(
                    "Document request does not belong "
                    "to this member."
                )

        # ==================================================
        # Ensure dependant belongs to same member
        # ==================================================
        if self.dependant:

            if self.dependant.member != self.member:
                raise ValidationError(
                    "Dependant does not belong "
                    "to this member."
                )

    # ======================================================
    # BUSINESS LOGIC
    # ======================================================
    def approve(self, user=None):
        """
        Approve a document.

        The linked request is automatically
        marked completed.
        """

        self.status = self.STATUS_APPROVED

        self.reviewed_by = user

        self.reviewed_at = timezone.now()

        self.rejection_reason = ""

        self.can_resubmit = False

        self.save()

        if self.document_request:

            self.document_request.mark_completed()
        
    def reject(self, user=None, reason="", ):
        """
        Reject a document.

        The request remains pending
        awaiting another upload.
        """

        self.status = self.STATUS_REJECTED

        self.reviewed_by = user

        self.reviewed_at = timezone.now()

        self.rejection_reason = reason

        self.can_resubmit = True

        self.save()

        if self.document_request:

            self.document_request.mark_pending()

    # ======================================================
    # SECURITY HELPERS
    # ======================================================
    def can_be_viewed_by(self, user):
        """
        Centralized permission helper.
        """

        if not user.is_authenticated:
            return False

        # Admin/staff access
        if user.is_staff or user.is_superuser:
            return True

        # Archived documents hidden from members
        if self.is_archived:
            return False

        # Owner access only
        try:
            return self.member.user == user
        except Exception:
            return False
        
    def archive(self):
        """
        Soft archive document.
        Keeps audit trail while hiding from active UI.
        """

        if not self.is_archived:

            self.is_archived = True

            self.archived_at = timezone.now()

            self.save()


    def unarchive(self):
        """
        Restore archived document.
        """

        if self.is_archived:

            self.is_archived = False

            self.archived_at = None

            self.save()

class AuditLog(models.Model):
    """
    Unified Audit Log Model

    ✔ Extended with:
        - is_high_risk (alerts)
    """

    # =====================================================
    # ACTION TYPES
    # =====================================================
    ACTION_MEMBER_STATUS = "member_status_change"
    ACTION_DEPENDANT_UPDATE = "dependant_update"
    ACTION_NOK_UPDATE = "nok_update"
    ACTION_PAYMENT_CREATED = "payment_created"
    ACTION_PAYMENT_APPROVED = "payment_approved"
    ACTION_PAYMENT_REJECTED = "payment_rejected"
    ACTION_PAYMENT_PROOF_UPLOADED = "payment_proof_uploaded"
    ACTION_CLAIM_APPROVED = "claim_approved"

    ACTION_CHOICES = [
        (ACTION_MEMBER_STATUS, "Member Status Change"),
        (ACTION_DEPENDANT_UPDATE, "Dependant Update"),
        (ACTION_NOK_UPDATE, "Next Of Kin Update"),
        (ACTION_PAYMENT_CREATED, "Payment Created"),
        (ACTION_PAYMENT_APPROVED, "Payment Approved"),
        (ACTION_PAYMENT_REJECTED, "Payment Rejected"),
        (ACTION_PAYMENT_PROOF_UPLOADED, "Payment Proof Uploaded"),
        (ACTION_CLAIM_APPROVED, "Claim Approved"),
    ]

    # =====================================================
    # WHO PERFORMED ACTION
    # =====================================================
    admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admin_actions",  # ✅ KEEP (already used in project)
    )

    # =====================================================
    # ACTION TYPE
    # =====================================================
    action = models.CharField(
        max_length=50,
        choices=ACTION_CHOICES
    )

    # =====================================================
    # RELATED OBJECTS
    # =====================================================
    target_member = models.ForeignKey(
        "Member",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="audit_logs",  # ✅ KEEP
    )

    payment = models.ForeignKey(
        "Payment",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="audit_logs",
    )

    # =====================================================
    # EXTRA INFO
    # =====================================================
    message = models.TextField(blank=True)
    description = models.TextField(blank=True)

    # ✅ NEW (SAFE ADDITION)
    is_high_risk = models.BooleanField(
        default=False,
        help_text="Flag high-risk admin/system actions"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_action_display()} by {self.admin} on {self.created_at}"

    # =====================================================
    # CENTRAL LOGGER (UPDATED)
    # =====================================================
    @classmethod
    def log_action(cls, *, admin=None, action=None, member=None, payment=None, message="", description=""):
        """
        CENTRAL LOGGING

        ✔ Adds high-risk detection
        ✔ Keeps backward compatibility
        """

        HIGH_RISK_ACTIONS = [
            cls.ACTION_MEMBER_STATUS,
            cls.ACTION_PAYMENT_APPROVED,
            cls.ACTION_PAYMENT_REJECTED,
        ]

        return cls.objects.create(
            admin=admin,
            action=action,
            target_member=member,
            payment=payment,
            message=message,
            description=description,
            is_high_risk=action in HIGH_RISK_ACTIONS
        )
        
        # =========================
        # REAL-TIME ALERT
        # =========================
        try:
            channel_layer = get_channel_layer()

            async_to_sync(channel_layer.group_send)(
                "audit_logs",
                {
                    "type": "send_alert",
                    "message": f"⚠️ {action} triggered"
                }
            )
        except Exception:
            pass  # fail silently

        return log
        
class PaymentAuditLog(models.Model):
    """
    FULL TRACEABILITY FOR PAYMENTS
    """

    ACTION_CHOICES = [
        ("created", "Created"),
        ("attempted", "Attempted"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    member = models.ForeignKey("Member", on_delete=models.SET_NULL, null=True)
    payment_request = models.ForeignKey("PaymentRequest", on_delete=models.SET_NULL, null=True)

    action = models.CharField(max_length=20, choices=ACTION_CHOICES)

    method = models.CharField(max_length=10, blank=True, null=True)

    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action} - {self.payment_request}"


class EmailOTP(models.Model):
    """
    SECURE OTP STORAGE (HASHED)

    ✔ Allows safe migration (null=True)
    ✔ All NEW records will always have hash
    """

    PURPOSE_REGISTRATION = "registration"
    PURPOSE_RESET = "password_reset"

    PURPOSE_CHOICES = [
        (PURPOSE_REGISTRATION, "Registration"),
        (PURPOSE_RESET, "Password Reset"),
    ]

    email = models.EmailField()

    # ✅ FIX: allow null for migration safety
    otp_hash = models.CharField(max_length=255, null=True, blank=True)

    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)

    created_at = models.DateTimeField(auto_now_add=True)

    is_used = models.BooleanField(default=False)

    # =========================================
    # SET OTP (HASH)
    # =========================================
    def set_otp(self, raw_otp):
        self.otp_hash = make_password(raw_otp)

    # =========================================
    # CHECK OTP
    # =========================================
    def check_otp(self, raw_otp):
        if not self.otp_hash:
            return False
        return check_password(raw_otp, self.otp_hash)

    # =========================================
    # EXPIRY
    # =========================================
    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(minutes=5)

    def __str__(self):
        return f"{self.email} - {self.purpose}"
    
"""
Stores ONLY non-derivable data.
"""


class ClaimSettlement(models.Model):
    
    STATUS_DRAFT = "draft"
    STATUS_SUBMITTED = "submitted"
    STATUS_APPROVED = "approved"
    
    uid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    claim = models.OneToOneField(
        "Claim",
        on_delete=models.CASCADE,
        related_name="settlement"
    )
    notes = models.TextField(blank=True)
    settlement_date = models.DateTimeField(default=timezone.now)    
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_claim_settlements"
    )

    prepared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prepared_claim_settlements"
    )
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)   
    status = models.CharField(
        max_length=20,
        choices=[
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("approved", "Approved"),
        ],
        default="draft"
    )

    # -----------------------------
    # DERIVED PROPERTIES (NOT STORED)
    # -----------------------------

    @property
    def total_collected(self):
        """
        Derived from PaymentRequest → Payments
        """
        pr = getattr(self.claim, "payment_request", None)
        if not pr:
            return 0
        return pr.total_paid
    
    @property
    def total_deductions(self):
        return sum(item.amount for item in self.deduction_items.all())
    @property
    
    def deductions(self):
        return (
            self.deduction_items.aggregate(
                total=models.Sum("amount")
            )["total"] or 0
        )

    @property
    def amount_paid(self):
        return self.total_collected - self.total_deductions

    def __str__(self):
        return f"Settlement for Claim {self.claim.uid}"


User = get_user_model()

class ClaimSettlementDeduction(models.Model):
    settlement = models.ForeignKey(
        "ClaimSettlement",
        on_delete=models.CASCADE,
        related_name="deduction_items"
    )

    title = models.CharField(max_length=255)  # e.g. "Admin fee"
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.title} - {self.amount}"


class LoginAttempt(models.Model):
    """
    Tracks login attempts for rate limiting + anomaly detection
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    email = models.EmailField()

    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)

    success = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)


class AccountLock(models.Model):
    """
    Locks account after repeated failures
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE)

    locked_until = models.DateTimeField()
    reason = models.CharField(max_length=255, blank=True)

    def is_locked(self):
        return timezone.now() < self.locked_until


class SecurityEvent(models.Model):
    """
    Audit log (admin dashboard)
    """

    EVENT_TYPES = [
        ("login_failed", "Login Failed"),
        ("login_success", "Login Success"),
        ("account_locked", "Account Locked"),
        ("suspicious_ip", "Suspicious IP"),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    event_type = models.CharField(max_length=50, choices=EVENT_TYPES)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)


class DocumentRequest(models.Model):
    """
    Admin requests documents from a member.
    Member uploads document → links back here.
    """

    STATUS_PENDING = "pending"
    STATUS_COMPLETED = "completed"
    STATUS_OVERDUE = "overdue"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_OVERDUE, "Overdue"),
    ]

    member = models.ForeignKey(
        "members.Member",
        on_delete=models.CASCADE,
        related_name="document_requests",
    )

    dependant = models.ForeignKey(
        "members.Dependant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    # 🔥 NEW: deadline support
    due_date = models.DateField(null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.member} → {self.title}"

    @property
    def is_completed(self):
        return self.status == self.STATUS_COMPLETED
    
    def update_request_status(self):
        """
        Synchronise the request with its uploaded documents.

        This is the ONLY place that updates

            status
            completed

        Every approval/rejection should call this method.
        """

        # --------------------------------------------------
        # ACTIVE DOCUMENTS
        # --------------------------------------------------

        documents = self.submitted_documents.filter(
            is_archived=False,
        )

        # --------------------------------------------------
        # DEFAULT VALUES
        # --------------------------------------------------

        new_status = self.STATUS_PENDING
        new_completed = False

        # --------------------------------------------------
        # APPROVED DOCUMENT EXISTS
        # --------------------------------------------------

        if documents.filter(
            status=MemberDocument.STATUS_APPROVED
        ).exists():

            new_status = self.STATUS_COMPLETED
            new_completed = True

        # --------------------------------------------------
        # OVERDUE
        # --------------------------------------------------

        elif (
            self.due_date
            and
            timezone.localdate() > self.due_date
        ):

            new_status = self.STATUS_OVERDUE
            new_completed = False

        # --------------------------------------------------
        # SAVE ONLY IF SOMETHING CHANGED
        # --------------------------------------------------

        if (
            self.status != new_status
            or
            self.completed != new_completed
        ):

            self.status = new_status
            self.completed = new_completed

            self.save(
                update_fields=[
                    "status",
                    "completed",
                ]
            )
        
    def mark_completed(self):
        """
        Marks this request as completed.

        Called only after a linked document
        has been approved.
        """

        if self.status != self.STATUS_COMPLETED:

            self.status = self.STATUS_COMPLETED

            self.completed = True

            self.save(
                update_fields=[
                    "status",
                    "completed",
                ]
            )
            
    def mark_pending(self):
        """
        Returns the request to Pending.

        Used when

        • document rejected

        • replacement required

        """

        if self.status != self.STATUS_PENDING or self.completed:

            self.status = self.STATUS_PENDING

            self.completed = False

            self.save(
                update_fields=[
                    "status",
                    "completed",
                ]
            )
        
# =========================================================
# NOTIFICATIONS
# =========================================================

class Notification(models.Model):
    """
    Central in-app notification system.

    Used for:
    - subscription reminders
    - retirement alerts
    - payment confirmations
    - lifecycle notifications
    """

    TYPE_PAYMENT = "payment"
    TYPE_ALERT = "alert"
    TYPE_SYSTEM = "system"

    NOTIFICATION_TYPES = [
        (TYPE_PAYMENT, "Payment"),
        (TYPE_ALERT, "Alert"),
        (TYPE_SYSTEM, "System"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications"
    )

    title = models.CharField(
        max_length=255
    )

    message = models.TextField()

    notification_type = models.CharField(
        max_length=20,
        choices=NOTIFICATION_TYPES,
        default=TYPE_SYSTEM
    )

    is_read = models.BooleanField(
        default=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    # =====================================
    # HELPERS
    # =====================================

    def mark_as_read(self):

        if not self.is_read:

            self.is_read = True

            self.save(update_fields=["is_read"])

    def __str__(self):

        return f"{self.user} - {self.title}"
    
    
class MagicLoginToken(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    is_used = models.BooleanField(
        default=False
    )

    def is_expired(self):

        return (
            timezone.now() >
            self.created_at + timedelta(minutes=15)
        )
        
        
class EmailVerification(models.Model):

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False
    )

    is_verified = models.BooleanField(
        default=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )
    
class OrganizationBranding(models.Model):

    organization = models.OneToOneField(
        "Organization",
        on_delete=models.CASCADE
    )

    primary_color = models.CharField(
        max_length=20,
        default="#0d6efd"
    )

    secondary_color = models.CharField(
        max_length=20,
        default="#4f46e5"
    )

    logo = models.ImageField(
        upload_to="organization_branding/"
    )

    email_footer = models.TextField(
        blank=True
    )


class MembershipStatusHistory(models.Model):

    ACTION_CHOICES = [
        ("retired", "Retired"),
        ("reactivated", "Reactivated"),
    ]

    member = models.ForeignKey(
        "Member",
        on_delete=models.CASCADE,
        related_name="status_history"
    )

    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES
    )

    reason = models.TextField(
        blank=True,
        null=True
    )

    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.member.member_uid} "
            f"{self.action} "
            f"{self.created_at:%Y-%m-%d}"
        )
    


