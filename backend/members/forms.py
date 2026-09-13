#backend/members/forms.py
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.forms import inlineformset_factory, ModelForm
from django.utils import timezone
from .models import Member, NextOfKin, Dependant, PaymentRequest
from backend.members.models import ClaimSettlementDeduction
from .models import (
    Claim,
    Member,
    Dependant,
    NextOfKin,
    Payment,
    PaymentRequest,
    ClaimBankDetails,
    ClaimSubmissionDeclaration,
    ClaimApprovalVerification,
)
from backend.members.models import ClaimSettlementDeduction
from datetime import date
from dateutil.relativedelta import relativedelta


import re


class UserRegistrationForm(UserCreationForm):
    """
    User account registration.

    Business Rules
    ------------------------------------------------------------------
    • User.email is the master email address.
    • Member.email is copied automatically from User.email.
    """

    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "password1",
            "password2",
        ]

    def save(self, commit=True):
        user = super().save(commit=False)

        user.email = self.cleaned_data["email"]

        if commit:
            user.save()

        return user


class UserLoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={'placeholder': 'Username'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': 'Password'}))

class MemberForm(forms.ModelForm):
    """
    Member profile form.

    Business Rules
    ------------------------------------------------------------------
    • User.email is the master email address.
    • Member.email is displayed for information only.
    • Member.email is synchronised during the registration workflow.
    """

    email = forms.EmailField(
        label="Email Address",
        required=False,
        disabled=True,
    )

    class Meta:
        model = Member
        fields = [
            "first_name",
            "middle_name",
            "surname",
            "dob",
            "phone",
            "email",
            "address",
        ]

        widgets = {
            "dob": forms.DateInput(
                attrs={"type": "date"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if (
            self.instance
            and self.instance.pk
            and self.instance.user
        ):
            self.fields["email"].initial = (
                self.instance.user.email
            )

class MemberForm_onHold_31_07_26(forms.ModelForm):
    """
    Member profile form.

    User.email is the master email address.
    Member.email is displayed for information only.
    """

    email = forms.EmailField(
        disabled=True,
        required=False,
        label="Email Address"
    )

    class Meta:
        model = Member
        fields = [
            "first_name",
            "middle_name",
            "surname",
            "phone",
            "email",
            "address",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.user:
            self.fields["email"].initial = self.instance.user.email


class NextOfKinForm(forms.ModelForm):
    class Meta:
        model = NextOfKin
        fields = ["first_name", "surname", "phone", "email", "relationship"]

class DependantForm(forms.ModelForm):
        """
        Dependant form.

        Includes optional document upload.
        The uploaded document is saved as a MemberDocument
        in the view rather than directly on the Dependant model.
        """

        document_title = forms.CharField(
            max_length=255,
            required=False,
            label="Document Title",
        )

        document_file = forms.FileField(
            required=False,
            label="Upload Document",
        )

        class Meta:
            model = Dependant
            fields = [
                "first_name",
                "middle_name",
                "surname",
                "relationship",
                "dob",
            ]

            widgets = {
                "dob": forms.DateInput(
                    attrs={"type": "date"}
                )
            }

        def clean(self):
            """
            Require a title whenever a document is uploaded.
            """
            cleaned_data = super().clean()

            file = cleaned_data.get("document_file")
            title = cleaned_data.get("document_title")

            if file and not title:
                self.add_error(
                    "document_title",
                    "Document title is required when uploading a file.",
                )

            return cleaned_data

class MemberRegistrationForm(forms.ModelForm):
    """
    Registration form used during the multi-step registration wizard.

    Business Rules
    ------------------------------------------------------------------
    • User account details are collected separately.
    • Email is verified by OTP before this form.
    • Member.email is copied from User.email.
    • applied_at is created automatically.
    • joined_at is populated when membership is approved.
    """

    class Meta:
        model = Member

        exclude = [

            # User relationship
            "user",

            # UID management
            "member_uid",
            "uid_assigned",

            # Organisation / status
            "organization",
            "status",

            # System-managed dates
            "applied_at",
            "joined_at",

            # Email comes from verified User.email
            "email",

            # Portal / editing
            "can_edit",
            "can_edit_expires_at",
            "is_portal_access_enabled",

            # Subscription / retirement
            "subscription_year",
            "retirement_reason",
            "retired_reason",
            "retired_at",
        ]

        widgets = {
            "dob": forms.DateInput(
                attrs={"type": "date"}
            ),
        }

class MemberRegistrationForm_onHold_31_07_26(forms.ModelForm):
    """
    Member registration details.

    User account details are collected separately.

    Business Rules
    ------------------------------------------------------------------
    • Email is collected in UserRegistrationForm.
    • Member.email is copied automatically from User.email.
    • applied_at is automatically recorded.
    • joined_at is populated only when membership is approved.
    """

    class Meta:
        model = Member

        exclude = [
            "user",
            "member_uid",
            "uid_assigned",
            "organization",
            "status",
            "applied_at",
            "joined_at",
            "email",
            "can_edit",
            "can_edit_expires_at",
            "subscription_year",
            "retirement_reason",
            "retired_reason",
            "is_portal_access_enabled",
        ]


class NextOfKinForm(forms.ModelForm):
    class Meta:
        model = NextOfKin
        exclude = ["member", "created_at"]


DependantFormSet = inlineformset_factory(Member, Dependant, form=DependantForm, extra=1, can_delete=True)
NextOfKinFormSet = inlineformset_factory(Member, NextOfKin, form=NextOfKinForm, extra=1, can_delete=True)

DependantFormSet = inlineformset_factory(
        Member,
        Dependant,
        form=DependantForm,
        extra=1,
        can_delete=True,
    )

class ClaimForm(forms.ModelForm):
    """
    Claim form used by both member and admin claim creation.

    Business Rules
    ------------------------------------------------------------------
    MEMBER FLOW
    - A member can only create a dependant claim.
    - The member cannot choose the claim type.
    - Only the member's own active dependants are available.

    ADMIN FLOW
    - The admin can create either a member or dependant claim.
    - When a member is selected, only that member's active dependants
      are available.

    Existing dependant filtering is preserved:
    - Only active dependants are available.
    - Dependants with received/open claims are excluded.
    """

    class Meta:

        model = Claim

        fields = [
            "cause_type",
            "causer_dependant",
            "claimer_is_next_of_kin",
        ]

        widgets = {

            "cause_type": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),

            "causer_dependant": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
        }

    def __init__(
        self,
        *args,
        user=None,
        selected_member=None,
        **kwargs
    ):

        super().__init__(
            *args,
            **kwargs
        )

        self.user = user

        self.selected_member = selected_member

        is_admin = bool(
            user
            and user.is_staff
        )

        # ======================================================
        # BASE DEPENDANT QUERYSET
        # ======================================================
        #
        # Preserve the existing protection against selecting:
        #
        # - inactive dependants
        # - dependants with received claims
        # - dependants with open claims
        # ======================================================

        base_qs = (
            Dependant.objects
            .filter(
                status="active"
            )
            .exclude(
                caused_claims__status__in=[
                    "received",
                    "open",
                ]
            )
        )

        # ======================================================
        # MEMBER FLOW
        # ======================================================
        #
        # Members can ONLY create dependant claims.
        # ======================================================

        if (
            not is_admin
            and hasattr(
                user,
                "member"
            )
        ):

            member = user.member

            # --------------------------------------------------
            # Do not allow the member to choose claim type.
            #
            # The value is also enforced again in clean().
            # --------------------------------------------------

            self.fields[
                "cause_type"
            ].initial = (
                Claim.CLAIM_CAUSER_DEPENDANT
            )

            self.fields[
                "cause_type"
            ].widget = forms.HiddenInput()

            # --------------------------------------------------
            # Only this member's dependants are available.
            # --------------------------------------------------

            self.fields[
                "causer_dependant"
            ].queryset = (
                base_qs.filter(
                    member=member
                )
            )

        # ======================================================
        # ADMIN FLOW
        # ======================================================
        #
        # Admin can create:
        #
        # - member-causer claim
        # - dependant-causer claim
        # ======================================================

        else:

            # --------------------------------------------------
            # Preferred admin flow:
            #
            # Use the member selected through the member search.
            # --------------------------------------------------

            if selected_member:

                qs = (
                    base_qs.filter(
                        member=selected_member
                    )
                )

            # --------------------------------------------------
            # Existing fallback preserved.
            #
            # Supports the existing case where an admin also
            # has a Member record.
            # --------------------------------------------------

            elif (
                user
                and hasattr(
                    user,
                    "member"
                )
            ):

                qs = (
                    base_qs.filter(
                        member=user.member
                    )
                )

            # --------------------------------------------------
            # No member context.
            # --------------------------------------------------

            else:

                qs = (
                    Dependant.objects.none()
                )

            self.fields[
                "causer_dependant"
            ].queryset = qs

        # ======================================================
        # DEPENDANT DISPLAY
        # ======================================================

        self.fields[
            "causer_dependant"
        ].label_from_instance = (
            lambda obj:
            f"{obj.first_name} {obj.surname}"
        )

    def clean(self):
        """
        Server-side validation.

        The views remain responsible for assigning:

        - claim.member
        - claim.causer_full_name
        - claim.claimer
        - claim.created_by

        This form validates only the claim-causer input.
        """

        cleaned_data = super().clean()

        cause_type = cleaned_data.get(
            "cause_type"
        )

        dependant = cleaned_data.get(
            "causer_dependant"
        )

        is_admin = bool(
            self.user
            and self.user.is_staff
        )

        # ======================================================
        # MEMBER FLOW
        # ======================================================
        #
        # Members can ONLY create dependant claims.
        #
        # The server enforces the cause type regardless of the
        # hidden HTML input.
        # ======================================================

        if (
            not is_admin
            and hasattr(
                self.user,
                "member"
            )
        ):

            # --------------------------------------------------
            # Enforce dependant claim type.
            # --------------------------------------------------

            cause_type = (
                Claim.CLAIM_CAUSER_DEPENDANT
            )

            cleaned_data[
                "cause_type"
            ] = cause_type

            # --------------------------------------------------
            # Dependant is required.
            # --------------------------------------------------

            if not dependant:

                self.add_error(
                    "causer_dependant",
                    (
                        "Please select the dependant "
                        "for this claim."
                    )
                )

            # --------------------------------------------------
            # Dependant must belong to signed-in member.
            # --------------------------------------------------

            elif (
                dependant.member_id
                != self.user.member.id
            ):

                self.add_error(
                    "causer_dependant",
                    (
                        "You can only create a claim "
                        "for one of your own dependants."
                    )
                )

        # ======================================================
        # ADMIN FLOW
        # ======================================================

        else:

            # --------------------------------------------------
            # DEPENDANT CLAIM
            # --------------------------------------------------

            if (
                cause_type
                == Claim.CLAIM_CAUSER_DEPENDANT
                and not dependant
            ):

                self.add_error(
                    "causer_dependant",
                    (
                        "Please select the dependant "
                        "for this claim."
                    )
                )

            # --------------------------------------------------
            # MEMBER CLAIM
            # --------------------------------------------------

            if (
                cause_type
                == Claim.CLAIM_CAUSER_MEMBER
                and dependant
            ):

                self.add_error(
                    "causer_dependant",
                    (
                        "A member claim cannot have "
                        "a dependant selected."
                    )
                )

        return cleaned_data

# ==============================================================
# CLAIM BANK DETAILS FORM
# ==============================================================

class ClaimBankDetailsForm(forms.ModelForm):
    """
    Bank details submitted with a claim.

    Validation rules
    ----------------------------------------------------------

    - Bank name is required.
    - Account name is required.
    - Sort code must contain six digits in the format:

        00-00-00

    - Account number must contain exactly eight digits.
    - The bank account must have been open for at least
    six months.

    The account opening date also has a dynamic HTML `max`
    attribute so the browser date picker cannot select a date
    newer than six months ago.
    """

    class Meta:

        model = ClaimBankDetails

        fields = [
            "bank_name",
            "account_name",
            "sort_code",
            "account_number",
            "account_opened_date",
        ]

        widgets = {

            # ==================================================
            # BANK NAME
            # ==================================================

            "bank_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter bank name",
                }
            ),

            # ==================================================
            # ACCOUNT NAME
            # ==================================================

            "account_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter account holder name",
                }
            ),

            # ==================================================
            # SORT CODE
            # ==================================================

            "sort_code": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "00-00-00",
                    "maxlength": "8",
                    "inputmode": "numeric",
                    "autocomplete": "off",
                }
            ),

            # ==================================================
            # ACCOUNT NUMBER
            # ==================================================

            "account_number": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Eight digit account number",
                    "maxlength": "8",
                    "inputmode": "numeric",
                    "autocomplete": "off",
                }
            ),

            # ==================================================
            # ACCOUNT OPENED DATE
            # ==================================================

            "account_opened_date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),
        }

    # ==========================================================
    # INITIALISE
    # ==========================================================

    def __init__(self, *args, **kwargs):

        super().__init__(
            *args,
            **kwargs
        )

        # ------------------------------------------------------
        # The account must have been open for at least six months.
        #
        # Therefore the latest permitted opening date is exactly
        # six calendar months before today.
        #
        # The `max` attribute prevents the browser date picker
        # from allowing a newer date to be selected.
        # ------------------------------------------------------

        today = timezone.localdate()

        maximum_account_opened_date = (
            today
            - relativedelta(months=6)
        )

        self.fields[
            "account_opened_date"
        ].widget.attrs[
            "max"
        ] = maximum_account_opened_date.isoformat()

    # ==========================================================
    # SORT CODE VALIDATION
    # ==========================================================

    def clean_sort_code(self):

        sort_code = self.cleaned_data.get(
            "sort_code"
        )

        if not sort_code:

            raise forms.ValidationError(
                "Please enter the bank sort code."
            )

        sort_code = sort_code.replace(
            " ",
            ""
        )

        if not re.fullmatch(
            r"\d{2}-\d{2}-\d{2}",
            sort_code,
        ):

            raise forms.ValidationError(
                (
                    "Sort code must contain six digits "
                    "in the format 00-00-00."
                )
            )

        return sort_code

    # ==========================================================
    # ACCOUNT NUMBER VALIDATION
    # ==========================================================

    def clean_account_number(self):

        account_number = self.cleaned_data.get(
            "account_number"
        )

        if not account_number:

            raise forms.ValidationError(
                "Please enter the bank account number."
            )

        account_number = (
            account_number.strip()
        )

        if not account_number.isdigit():

            raise forms.ValidationError(
                "Account number must contain digits only."
            )

        if len(account_number) != 8:

            raise forms.ValidationError(
                (
                    "A UK bank account number must "
                    "contain exactly eight digits."
                )
            )

        return account_number

    # ==========================================================
    # ACCOUNT OPENED DATE VALIDATION
    # ==========================================================

    def clean_account_opened_date(self):

        account_opened_date = (
            self.cleaned_data.get(
                "account_opened_date"
            )
        )

        if not account_opened_date:

            raise forms.ValidationError(
                (
                    "Please provide the date the "
                    "account was opened."
                )
            )

        # ------------------------------------------------------
        # The account must have existed for at least six months.
        # ------------------------------------------------------

        today = timezone.localdate()

        minimum_account_age_date = (
            today
            - relativedelta(months=6)
        )

        if (
            account_opened_date
            > minimum_account_age_date
        ):

            raise forms.ValidationError(
                (
                    "The bank account must have been "
                    "open for at least six months."
                )
            )

        return account_opened_date

# ==============================================================
# CLAIM SUBMISSION DECLARATION FORM
# ==============================================================

class ClaimSubmissionDeclarationForm(forms.ModelForm):
    """
    Claimant declarations.

    The next-of-kin confirmation is required only for a
    MEMBER-causer claim.
    """

    class Meta:
        model = ClaimSubmissionDeclaration
        fields = [
            "confirmation_understood",
            "details_confirmed",
            "next_of_kin_contacted",
        ]
        widgets = {
            "confirmation_understood": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "details_confirmed": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "next_of_kin_contacted": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
        }

    def __init__(self, *args, member_claim=False, **kwargs):
        self.member_claim = member_claim
        super().__init__(*args, **kwargs)

        if self.member_claim:
            self.fields["confirmation_understood"].required = False
        else:
            self.fields["next_of_kin_contacted"].required = False

    def clean(self):
        cleaned = super().clean()

        if not self.member_claim:
            if not cleaned.get("confirmation_understood"):
                self.add_error(
                    "confirmation_understood",
                    (
                        "You must confirm that you have "
                        "read and understood the "
                        "confirmation statement."
                    ),
                )

        if not cleaned.get("details_confirmed"):
            self.add_error(
                "details_confirmed",
                (
                    "You must confirm that the "
                    "details are true."
                ),
            )

        if (
            self.member_claim
            and not cleaned.get("next_of_kin_contacted")
        ):
            self.add_error(
                "next_of_kin_contacted",
                (
                    "You must confirm that the next "
                    "of kin has been contacted, is "
                    "aware of the claim and agrees "
                    "with the claim details."
                ),
            )

        if self.member_claim:
            cleaned["confirmation_understood"] = False
        else:
            cleaned["next_of_kin_contacted"] = False

        return cleaned

class ClaimApprovalVerificationForm(forms.ModelForm):
    """
    Form used by an administrator to verify a claim
    before making an approval or rejection decision.

    The administrator must:

    - Explicitly answer Yes or No to the three
      verification statements.
    - Select the method used to confirm the information.
    - Provide details when "Other" is selected.

    A "No" answer is valid verification information.

    The view determines whether the claim may be approved.
    """

    # ==========================================================
    # EXPLICIT YES / NO QUESTIONS
    #
    # TypedChoiceField is used so that:
    #
    # "yes" -> True
    # "no"  -> False
    #
    # Both answers are valid.
    # ==========================================================

    details_match_welfare_record = forms.TypedChoiceField(

        label=(
            "Details in this form match current details "
            "in KRO welfare record."
        ),

        choices=[

            ("yes", "Yes"),

            ("no", "No"),
        ],

        coerce=lambda value: value == "yes",

        empty_value=None,

        widget=forms.RadioSelect,

        required=True,
    )


    telephone_matches_record = forms.TypedChoiceField(

        label=(
            "Telephone number matches the number on record "
            "and has not been recently changed."
        ),

        choices=[

            ("yes", "Yes"),

            ("no", "No"),
        ],

        coerce=lambda value: value == "yes",

        empty_value=None,

        widget=forms.RadioSelect,

        required=True,
    )


    information_correct_declaration = forms.TypedChoiceField(

        label=(
            "The information provided is correct to the "
            "best of my knowledge."
        ),

        choices=[

            ("yes", "Yes"),

            ("no", "No"),
        ],

        coerce=lambda value: value == "yes",

        empty_value=None,

        widget=forms.RadioSelect,

        required=True,
    )


    class Meta:

        model = ClaimApprovalVerification


        fields = [

            # ==================================================
            # VERIFICATION QUESTIONS
            # ==================================================

            "details_match_welfare_record",

            "telephone_matches_record",


            # ==================================================
            # CONFIRMATION METHOD
            #
            # Your model has ONE field allowing the admin
            # to select one method.
            # ==================================================

            "confirmation_method",

            "confirmation_method_other",


            # ==================================================
            # FINAL DECLARATION
            # ==================================================

            "information_correct_declaration",
        ]


        widgets = {


            # ==================================================
            # CONFIRMATION METHOD
            # ==================================================

            "confirmation_method":

                forms.Select(

                    attrs={

                        "class": "form-select",

                    }

                ),


            # ==================================================
            # OTHER METHOD
            # ==================================================

            "confirmation_method_other":

                forms.TextInput(

                    attrs={

                        "class": "form-control",

                        "placeholder": (
                            "State the other method used"
                        ),

                    }

                ),
        }


    def clean(self):
        """
        Validate the administrator's verification details.

        Important:

        A "No" answer is valid.

        The form records what the administrator found.

        The approve_claim view determines whether all
        required answers are Yes before allowing approval.
        """

        cleaned_data = super().clean()


        # ======================================================
        # CONFIRMATION METHOD
        # ======================================================

        confirmation_method = cleaned_data.get(

            "confirmation_method"

        )


        confirmation_method_other = cleaned_data.get(

            "confirmation_method_other"

        )


        # ======================================================
        # METHOD MUST BE SELECTED
        # ======================================================

        if not confirmation_method:

            self.add_error(

                "confirmation_method",

                (
                    "Please select the method used to "
                    "confirm the information."
                ),

            )


        # ======================================================
        # OTHER REQUIRES DESCRIPTION
        # ======================================================

        if (

            confirmation_method
            == ClaimApprovalVerification.METHOD_OTHER

            and not confirmation_method_other

        ):

            self.add_error(

                "confirmation_method_other",

                (
                    "Please state the other confirmation "
                    "method used."
                ),

            )


        return cleaned_data

class PaymentRequestForm(forms.ModelForm):
    class Meta:
        model = PaymentRequest
        fields = ['member', 'amount', 'due_date', 'request_type', 'authorised_by']
        widgets = {
            'member': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter amount'}),
            'due_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'request_type': forms.Select(attrs={'class': 'form-select'}),
            'authorised_by': forms.Select(attrs={'class': 'form-select'}),
        }


class ClaimSettlementDeductionForm(ModelForm):
    class Meta:
        model = ClaimSettlementDeduction
        fields = ["title", "amount"]

        widgets = {
            "title": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "e.g. Admin fee, hall hire, penalties"
            }),
            "amount": forms.NumberInput(attrs={
                "class": "form-control deduction-amount",
                "placeholder": "£ amount",
                "step": "0.01"
            }),
        }

    def clean(self):
        cleaned = super().clean()

        title = cleaned.get("title")
        amount = cleaned.get("amount")

        # -----------------------------------
        # 🔥 CRITICAL FIX
        # IGNORE EMPTY FORMS (prevents id error)
        # -----------------------------------
        if not title and not amount:
            self.cleaned_data["DELETE"] = True

        return cleaned