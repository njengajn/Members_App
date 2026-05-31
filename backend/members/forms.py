#backend/members/forms.py
from django import forms
from django.contrib.auth.models import User
from .models import Claim, Member, Dependant, NextOfKin, Payment
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.forms import inlineformset_factory
from .models import Member, NextOfKin, Dependant, PaymentRequest
from django.forms import ModelForm
from backend.members.models import ClaimSettlementDeduction

class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]

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
    class Meta:
        model = Member
        fields = ["first_name", "middle_name", "surname", "phone", "email", "address"]


class NextOfKinForm(forms.ModelForm):
    class Meta:
        model = NextOfKin
        fields = ["first_name", "surname", "phone", "email", "relationship"]


class DependantForm(forms.ModelForm):
    class Meta:
        model = Dependant
        fields = ["first_name", "middle_name", "surname",  "dob", "relationship"]


DependantFormSet = inlineformset_factory(
    Member, Dependant, form=DependantForm, extra=1, can_delete=True
)


class ClaimFormOnHold(forms.ModelForm):
    CLAIMER_CHOICES = [
        ("member", "Member"),
        ("next_of_kin", "Next of Kin"),
    ]

    claimer_type = forms.ChoiceField(
        choices=CLAIMER_CHOICES,
        widget=forms.RadioSelect,
        required=False,
    )
    class Meta:
        model = Claim
        fields = [
            "cause_type",
            "causer_dependant",
            "claimer_is_next_of_kin",
        ]

    def __init__(self, *args, **kwargs):
        self.member = kwargs.pop("member", None)
        super().__init__(*args, **kwargs)

        # Limit dependants to this member
        if self.member:
            self.fields["causer_dependant"].queryset = Dependant.objects.filter(
                member=self.member
            )
        else:
            self.fields["causer_dependant"].queryset = Dependant.objects.none()

        self.fields["causer_dependant"].required = False

    def clean(self):
        cleaned = super().clean()
        cause_type = cleaned.get("cause_type")
        dependant = cleaned.get("causer_dependant")

        if cause_type == Claim.CLAIM_CAUSER_DEPENDANT and not dependant:
            raise forms.ValidationError(
                "You must select a dependant for this claim."
            )

        if cause_type == Claim.CLAIM_CAUSER_MEMBER and dependant:
            raise forms.ValidationError(
                "Member claim cannot have a dependant selected."
            )

        return cleaned


class ClaimForm(forms.ModelForm):
    """
    FINAL FORM FIX

    - Excludes dependants with ACTIVE claims
    - Ensures clean dropdown
    """

    class Meta:
        model = Claim
        fields = [
            "cause_type",
            "causer_dependant",
            "claimer_is_next_of_kin",
        ]

    def __init__(self, *args, user=None, selected_member=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.user = user
        self.selected_member = selected_member

        is_admin = user and user.is_staff

        # ----------------------------------------
        # BASE FILTER (IMPORTANT FIX)
        # ----------------------------------------
        base_qs = Dependant.objects.filter(status="active").exclude(
            caused_claims__status__in=["received", "open"]
        )

        # ----------------------------------------
        # MEMBER FLOW
        # ----------------------------------------
        if not is_admin and hasattr(user, "member"):
            member = user.member

            self.fields["cause_type"].initial = "dependant"
            self.fields["cause_type"].widget = forms.HiddenInput()

            self.fields["causer_dependant"].queryset = base_qs.filter(member=member)

        # ----------------------------------------
        # ADMIN FLOW
        # ----------------------------------------
        else:
            if selected_member:
                qs = base_qs.filter(member=selected_member)
            elif hasattr(user, "member"):
                qs = base_qs.filter(member=user.member)
            else:
                qs = Dependant.objects.none()

            self.fields["causer_dependant"].queryset = qs

        self.fields["causer_dependant"].label_from_instance = (
            lambda obj: f"{obj.first_name} {obj.surname}"
        )

class ClaimFormOnHold2(forms.ModelForm):
    """
    FINAL FIX:
    - Correct dependant filtering
    - No global leakage
    """

    class Meta:
        model = Claim
        fields = [
            "cause_type",
            "causer_dependant",
            "claimer_is_next_of_kin",
        ]

    def __init__(self, *args, user=None, selected_member=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.user = user
        self.selected_member = selected_member

        is_admin = user and user.is_staff

        # ============================
        # MEMBER FLOW
        # ============================
        if not is_admin and hasattr(user, "member"):
            member = user.member

            self.fields["cause_type"].initial = "dependant"
            self.fields["cause_type"].widget = forms.HiddenInput()

            self.fields["causer_dependant"].queryset = Dependant.objects.filter(
                member=member,
                status="active"
            ).exclude(
                caused_claims__isnull=False
            )

        # ============================
        # ADMIN FLOW (FIXED)
        # ============================
        else:
            if selected_member:
                qs = Dependant.objects.filter(
                    member=selected_member,
                    status="active"
                )
            elif hasattr(user, "member"):
                # 🔥 ADMIN DEFAULT → own dependants only
                qs = Dependant.objects.filter(
                    member=user.member,
                    status="active"
                )
            else:
                qs = Dependant.objects.none()

            qs = qs.exclude(caused_claims__isnull=False)

            self.fields["causer_dependant"].queryset = qs

        # Clean labels
        self.fields["causer_dependant"].label_from_instance = (
            lambda obj: f"{obj.first_name} {obj.surname}"
        )

    def clean(self):
        cleaned_data = super().clean()

        if not self.data:
            return cleaned_data

        cause_type = cleaned_data.get("cause_type")
        dependant = cleaned_data.get("causer_dependant")

        is_admin = self.user and self.user.is_staff

        if not is_admin:
            cleaned_data["cause_type"] = "dependant"

            if not dependant:
                raise forms.ValidationError("Dependant must be selected.")

        else:
            if cause_type == "dependant" and not dependant:
                raise forms.ValidationError("Select a dependant.")

        return cleaned_data


class ClaimFormOnHold(forms.ModelForm):
    """
    FINAL CLEAN IMPLEMENTATION

    Key guarantees:
    - Admin always sees BOTH claim types
    - Member forced to dependant
    - Dependants filtered correctly
    - No global leakage
    """

    class Meta:
        model = Claim
        fields = [
            "cause_type",
            "causer_dependant",
            "claimer_is_next_of_kin",
        ]

    def __init__(self, *args, user=None, selected_member=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.user = user
        self.selected_member = selected_member

        is_admin = user and user.is_staff

        # ----------------------------------------
        # MEMBER FLOW
        # ----------------------------------------
        if not is_admin and hasattr(user, "member"):
            member = user.member

            # Force dependant only
            self.fields["cause_type"].choices = [
                ("dependant", "Dependant")
            ]
            self.fields["cause_type"].initial = "dependant"
            self.fields["cause_type"].widget = forms.HiddenInput()

            # Only this member's dependants
            self.fields["causer_dependant"].queryset = Dependant.objects.filter(
                member=member,
                status="active"
            ).exclude(
                caused_claims__isnull=False
            )

        # ----------------------------------------
        # ADMIN FLOW (FIXED PROPERLY)
        # ----------------------------------------
        else:
            # Always show BOTH options
            self.fields["cause_type"].choices = [
                ("member", "Member"),
                ("dependant", "Dependant"),
            ]

            self.fields["cause_type"].widget = forms.Select()

            # Show dependants ONLY for selected member
            if selected_member:
                qs = Dependant.objects.filter(
                    member=selected_member,
                    status="active"
                ).exclude(
                    caused_claims__isnull=False
                )
            else:
                # Show NONE until member selected
                qs = Dependant.objects.none()

            self.fields["causer_dependant"].queryset = qs

            # Clean readable label
            self.fields["causer_dependant"].label_from_instance = (
                lambda obj: f"{obj.first_name} {obj.surname}"
            )

    def clean(self):
        cleaned_data = super().clean()

        # Avoid validation on GET
        if not self.data:
            return cleaned_data

        cause_type = cleaned_data.get("cause_type")
        dependant = cleaned_data.get("causer_dependant")

        is_admin = self.user and self.user.is_staff

        if not is_admin:
            if not dependant:
                raise forms.ValidationError("Dependant must be selected.")

        else:
            if cause_type == "dependant" and not dependant:
                raise forms.ValidationError("Dependant must be selected.")

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

class MemberRegistrationForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = [
            "first_name",
            "middle_name",
            "surname",
            "email",
            "phone",
            "address",
        ]



class UserRegistrationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ["username", "email", "password"]

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")
        if password and confirm_password and password != confirm_password:
            raise forms.ValidationError("Passwords do not match.")
        return cleaned_data


class MemberRegistrationForm(forms.ModelForm):
    class Meta:
        model = Member
        exclude = ["user", "member_uid", "joined_at", "status", "can_edit", "organization"]


class DependantForm(forms.ModelForm):
    """
    Dependant form WITHOUT document field from model.

    Instead, added:
    ✔ document_title
    ✔ document_file

    These will be saved into MemberDocument in the view.
    """

    # Extra (non-model) fields for document upload
    document_title = forms.CharField(
        max_length=255,
        required=False,
        label="Document Title"
    )

    document_file = forms.FileField(
        required=False,
        label="Upload Document"
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
            "dob": forms.DateInput(attrs={"type": "date"}),
        }

    def clean(self):
        """
        Optional validation:
        If file is uploaded, title should exist
        """
        cleaned_data = super().clean()
        file = cleaned_data.get("document_file")
        title = cleaned_data.get("document_title")

        if file and not title:
            self.add_error("document_title", "Document title is required when uploading a file.")

        return cleaned_data

class NextOfKinForm(forms.ModelForm):
    class Meta:
        model = NextOfKin
        exclude = ["member", "created_at"]


DependantFormSet = inlineformset_factory(Member, Dependant, form=DependantForm, extra=1, can_delete=True)
NextOfKinFormSet = inlineformset_factory(Member, NextOfKin, form=NextOfKinForm, extra=1, can_delete=True)


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