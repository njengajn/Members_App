from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from backend.members.decorators import member_required
from backend.members.forms import DependantForm
from backend.members.models import Member, Dependant, MemberDocument
from backend.members.services.document_files import (
    DocumentUploadValidationError,
    generate_document_thumbnail,
    prepare_document_file,
)
from django.utils import timezone


# ======================================================
# ✅ HELPER: ACTIVE MEMBER CHECK (REUSABLE)
# ======================================================
def ensure_active_member(request):
    """
    Reusable guard to ensure only ACTIVE members proceed
    Returns:
        - member (if valid)
        - None (if blocked)
    """

    member = request.user.member

    if member.status != "active":
        messages.error(
            request,
            "Your account is not active. Wait to be activated or contact KRO"
        )
        return None

    return member


@login_required
@member_required
def members_dependants_list(request):
    """
    List dependants for member

    ✔ FIXED:
    - correct member initialization
    - safe expiry check
    """

    # ✅ ALWAYS GET MEMBER FIRST
    member = ensure_active_member(request)

    if not member:
        return redirect("members:dashboard")

    member.check_can_edit_expiry()

    dependants = Dependant.objects.filter(member=member)

    return render(
        request,
        "members/dependants/members_dependants_list.html",
        {
            "member": member,
            "dependants": dependants,
        }
    )

# ==========================================================
# ADD DEPENDANT
# ==========================================================

@login_required
@member_required
def members_add_dependant(request):
    """
    Add a dependant for the logged-in member.

    Relationship limits:

        Spouse:
            Maximum 1

        Parents:
            Maximum 2 total

        Mother:
            Maximum 1

        Father:
            Maximum 1

    These limits are checked against the existing database
    dependants belonging to the current member.

    JavaScript provides browser-side feedback, but these
    server-side checks are authoritative.

    Parent status rules:

        Alive:
            Normal parent details and location are required.

        Deceased:
            Location is not collected.

        Unknown:
            Parent type and Unknown status are recorded, but
            no identifying or location information is retained.

            UNKNOWN is a deliberate business state.

            The dependant is initially created as pending,
            preserving the existing approval workflow.

            Activation protection is enforced separately so
            an UNKNOWN parent can never become Active.
    """

    # ======================================================
    # CURRENT MEMBER
    # ======================================================

    try:

        member = request.user.member

    except Member.DoesNotExist:

        messages.warning(
            request,
            "You are not registered as a member yet.",
        )

        return redirect(
            "members:member_dashboard"
        )


    # ======================================================
    # EDIT PERMISSION
    # ======================================================

    member.check_can_edit_expiry()

    if not member.can_edit:

        messages.error(
            request,
            "Editing is disabled for your account.",
        )

        return redirect(
            "members:dependants"
        )


    # ======================================================
    # EXISTING DEPENDANT COUNTS
    # ======================================================
    #
    # These values are used:
    #
    # 1. By the template/JavaScript for immediate feedback.
    # 2. Again below by the server before saving.
    #
    # The database remains authoritative.
    # ======================================================

    existing_dependants = (
        Dependant.objects.filter(
            member=member
        )
    )

    existing_spouse_count = (
        existing_dependants
        .filter(
            relationship="SPOUSE"
        )
        .count()
    )

    existing_parent_count = (
        existing_dependants
        .filter(
            relationship="PARENT"
        )
        .count()
    )

    existing_mother_count = (
        existing_dependants
        .filter(
            relationship="PARENT",
            parent_type="MOTHER",
        )
        .count()
    )

    existing_father_count = (
        existing_dependants
        .filter(
            relationship="PARENT",
            parent_type="FATHER",
        )
        .count()
    )


    # ======================================================
    # FORM
    # ======================================================

    form = DependantForm(
        request.POST or None,
        request.FILES or None,
    )


    # ======================================================
    # POST
    # ======================================================

    if request.method == "POST":

        # --------------------------------------------------
        # Additional fields.
        # --------------------------------------------------

        relationship = (
            request.POST.get(
                "relationship",
                "",
            )
            .strip()
            .upper()
        )

        parent_type = (
            request.POST.get(
                "parent_type",
                "",
            )
            .strip()
            .upper()
        )

        country = (
            request.POST.get(
                "country",
                "",
            )
            .strip()
        )

        county = (
            request.POST.get(
                "county",
                "",
            )
            .strip()
        )

        sub_county_town = (
            request.POST.get(
                "sub_county_town",
                "",
            )
            .strip()
        )

        additional_errors = []


        # ==================================================
        # AUTHORITATIVE PARENT STATUS
        # ==================================================
        #
        # Never trust parent_status from POST.
        #
        # The Member record is the source of truth.
        #
        # Preserve all three valid statuses:
        # ALIVE, DECEASED and UNKNOWN.
        # ==================================================

        parent_status = ""

        form_data = request.POST.copy()

        if relationship == "PARENT":

            if parent_type == Dependant.PARENT_MOTHER:

                parent_status = (
                    member.mother_status or ""
                ).strip().upper()

            elif parent_type == Dependant.PARENT_FATHER:

                parent_status = (
                    member.father_status or ""
                ).strip().upper()

            else:

                additional_errors.append(
                    "Please select Mother or Father."
                )


            # Validate the status recorded on the Member.
            if parent_status not in {
                Member.PARENT_ALIVE,
                Member.PARENT_DECEASED,
                Member.PARENT_UNKNOWN,
            }:

                additional_errors.append(
                    "The parent status recorded on your "
                    "membership record is missing or invalid. "
                    "Please contact the administrator."
                )


            # Override the browser-submitted value.
            # The form will validate using the Member's status.
            form_data["parent_status"] = parent_status

        else:

            # Parent-only values are irrelevant to other
            # relationship types.

            parent_type = ""
            parent_status = ""

            form_data["parent_type"] = ""
            form_data["parent_status"] = ""


        # ==================================================
        # FORM VALIDATION
        # ==================================================

        form = DependantForm(
            form_data,
            request.FILES or None,
        )

        form_valid = form.is_valid()


        # ==================================================
        # VALID RELATIONSHIP
        # ==================================================

        if relationship not in {
            "CHILD",
            "SPOUSE",
            "SIBLING",
            "PARENT",
        }:

            additional_errors.append(
                "Please select a valid dependant relationship."
            )


        # ==================================================
        # SPOUSE LIMIT
        # ==================================================

        if relationship == "SPOUSE":

            # ----------------------------------------------
            # Member must be Married.
            # ----------------------------------------------

            marital_status = (
                str(
                    getattr(
                        member,
                        "marital_status",
                        "",
                    )
                    or ""
                )
                .strip()
                .upper()
            )

            if marital_status != "MARRIED":

                additional_errors.append(
                    "A spouse can only be added when "
                    "your marital status is Married."
                )


            # ----------------------------------------------
            # Maximum one spouse.
            # ----------------------------------------------

            if existing_spouse_count >= 1:

                additional_errors.append(
                    "You already have a spouse registered. "
                    "Only one spouse can be registered."
                )


        # ==================================================
        # PARENT LIMITS
        # ==================================================

        if relationship == "PARENT":

            # ----------------------------------------------
            # Maximum two parents.
            # ----------------------------------------------

            if existing_parent_count >= 2:

                additional_errors.append(
                    "You already have two parents registered. "
                    "No additional parent can be added."
                )


            # ----------------------------------------------
            # Maximum one mother.
            # ----------------------------------------------

            if (
                parent_type == "MOTHER"
                and existing_mother_count >= 1
            ):

                additional_errors.append(
                    "You already have a mother registered. "
                    "Only one mother can be registered."
                )


            # ----------------------------------------------
            # Maximum one father.
            # ----------------------------------------------

            if (
                parent_type == "FATHER"
                and existing_father_count >= 1
            ):

                additional_errors.append(
                    "You already have a father registered. "
                    "Only one father can be registered."
                )


        # ==================================================
        # LOCATION RULES
        # ==================================================

        location_required = (
            relationship in {
                "SPOUSE",
                "SIBLING",
            }
            or (
                relationship == "PARENT"
                and parent_status == Member.PARENT_ALIVE
            )
        )

        if location_required:

            if not country:

                additional_errors.append(
                    "Please enter the country."
                )

            if not county:

                additional_errors.append(
                    "Please enter the county."
                )

            if not sub_county_town:

                additional_errors.append(
                    "Please enter the sub-county / town."
                )

        else:

            # Child and Deceased/Unknown Parent do not
            # collect location.

            country = ""
            county = ""
            sub_county_town = ""


        # ==================================================
        # STOP IF VALIDATION FAILED
        # ==================================================

        if (
            not form_valid
            or additional_errors
        ):

            for error in additional_errors:

                messages.error(
                    request,
                    error,
                )

            return render(
                request,
                "members/dependants/"
                "members_add_dependants.html",
                {
                    "form": form,
                    "member": member,

                    # Existing relationship counts.
                    "existing_spouse_count":
                        existing_spouse_count,

                    "existing_parent_count":
                        existing_parent_count,

                    "existing_mother_count":
                        existing_mother_count,

                    "existing_father_count":
                        existing_father_count,
                },
            )


        # ==================================================
        # DOCUMENT
        # ==================================================

        doc_file = (
            form.cleaned_data.get(
                "document_file"
            )
        )

        doc_title = (
            form.cleaned_data.get(
                "document_title"
            )
        )

        processed_file = None

        original_filename = None

        if doc_file:

            original_filename = doc_file.name

            try:

                processed_file = (
                    prepare_document_file(
                        uploaded_file=doc_file,
                        member=member,
                        document_title=(
                            doc_title
                            or "Dependant Document"
                        ),
                    )
                )

            except DocumentUploadValidationError as exc:

                messages.error(
                    request,
                    str(exc),
                )

                return render(
                    request,
                    "members/dependants/"
                    "members_add_dependants.html",
                    {
                        "form": form,
                        "member": member,

                        "existing_spouse_count":
                            existing_spouse_count,

                        "existing_parent_count":
                            existing_parent_count,

                        "existing_mother_count":
                            existing_mother_count,

                        "existing_father_count":
                            existing_father_count,
                    },
                )


        # ==================================================
        # SAVE
        # ==================================================

        with transaction.atomic():

            dependant = form.save(
                commit=False
            )

            dependant.member = member

            dependant.relationship = (
                relationship
            )

            dependant.parent_type = (
                parent_type
            )

            dependant.parent_status = (
                parent_status
            )

            dependant.country = (
                country
            )

            dependant.county = (
                county
            )

            dependant.sub_county_town = (
                sub_county_town
            )

            # --------------------------------------------------
            # Preserve the existing dependant approval workflow.
            #
            # Every newly added dependant starts as PENDING.
            #
            # This is deliberately NOT changed to RETIRED for
            # DECEASED/UNKNOWN parents here.
            #
            # The separate activation lifecycle is responsible
            # for preventing DECEASED/UNKNOWN parents from ever
            # becoming ACTIVE.
            # --------------------------------------------------

            dependant.status = (
                "pending"
            )

            dependant.save()


            # ==================================================
            # SUPPORTING DOCUMENT
            # ==================================================

            if processed_file:

                document = MemberDocument(
                    member=member,
                    dependant=dependant,
                    title=(
                        doc_title
                        or "Dependant Document"
                    ),
                    file=processed_file,
                    original_filename=(
                        original_filename
                    ),
                )

                # Preserve existing document validation.

                document.full_clean()

                document.save()


                # Preserve existing thumbnail processing.

                generate_document_thumbnail(
                    document
                )


        # ==================================================
        # SUCCESS
        # ==================================================

        messages.success(
            request,
            "Dependant added.",
        )

        return redirect(
            "members:dependants"
        )


    # ======================================================
    # GET
    # ======================================================

    return render(
        request,
        "members/dependants/"
        "members_add_dependants.html",
        {
            "form": form,
            "member": member,

            "existing_spouse_count":
                existing_spouse_count,

            "existing_parent_count":
                existing_parent_count,

            "existing_mother_count":
                existing_mother_count,

            "existing_father_count":
                existing_father_count,
        },
    )


@login_required
@member_required
def members_edit_dependant(request, pk):
    """
    Edit an existing dependant belonging to the logged-in member.

    Historical Deceased/Unknown parents are protected using their
    original database values. Parent status is not editable here.

    Ordinary dependant edits return to pending for review.
    Historical non-alive parent records retain their existing status.

    Supporting documents use the established MemberDocument workflow.
    """

    # ======================================================
    # CURRENT MEMBER
    # ======================================================

    try:
        member = request.user.member
    except Member.DoesNotExist:
        messages.warning(
            request,
            "You are not registered as a member yet.",
        )
        return redirect("members:member_dashboard")

    # ======================================================
    # EDIT PERMISSION
    # ======================================================

    member.check_can_edit_expiry()

    if not member.can_edit:
        messages.error(
            request,
            "Editing is disabled for your account.",
        )
        return redirect("members:dependants")

    # ======================================================
    # DEPENDANT OWNERSHIP
    # ======================================================

    dependant = get_object_or_404(
        Dependant,
        pk=pk,
        member=member,
    )

    original_relationship = dependant.relationship
    original_parent_type = dependant.parent_type
    original_parent_status = dependant.parent_status
    original_dependant_status = dependant.status

    historical_non_alive_parent = (
        original_relationship == Dependant.TYPE_PARENT
        and original_parent_status in {
            Dependant.PARENT_DECEASED,
            Dependant.PARENT_UNKNOWN,
        }
    )

    # ======================================================
    # FORM
    # ======================================================

    if request.method == "POST":

        form_data = request.POST.copy()

        submitted_relationship = (
            form_data.get("relationship") or ""
        ).strip().upper()

        submitted_parent_type = (
            form_data.get("parent_type") or ""
        ).strip().upper()

        form = DependantForm(
            form_data,
            request.FILES or None,
            instance=dependant,
        )

        # --------------------------------------------------
        # RELATIONSHIP PROTECTION
        # --------------------------------------------------

        if submitted_relationship != original_relationship:
            form.add_error(
                "relationship",
                "The relationship of an existing dependant cannot be changed here. Please contact an administrator if it needs correcting.",
            )

            return render(
                request,
                "members/dependants/members_dependant_form.html",
                {
                    "form": form,
                    "member": member,
                    "historical_non_alive_parent":
                        historical_non_alive_parent,
                },
            )

        # --------------------------------------------------
        # HISTORICAL NON-ALIVE PARENT
        # --------------------------------------------------

        if historical_non_alive_parent:

            # Restore protected values before form validation.
            form_data["relationship"] = original_relationship
            form_data["parent_type"] = original_parent_type
            form_data["parent_status"] = original_parent_status

            form = DependantForm(
                form_data,
                request.FILES or None,
                instance=dependant,
            )

        # --------------------------------------------------
        # EXISTING ALIVE PARENT
        # --------------------------------------------------

        elif original_relationship == Dependant.TYPE_PARENT:

            if submitted_parent_type != original_parent_type:
                form.add_error(
                    "parent_type",
                    "The parent type of an existing parent record cannot be changed here. Please contact an administrator if it needs correcting.",
                )

                return render(
                    request,
                    "members/dependants/members_dependant_form.html",
                    {
                        "form": form,
                        "member": member,
                        "historical_non_alive_parent": False,
                    },
                )

            if original_parent_type == Dependant.PARENT_MOTHER:
                member_parent_status = (
                    member.mother_status or ""
                ).strip().upper()

            elif original_parent_type == Dependant.PARENT_FATHER:
                member_parent_status = (
                    member.father_status or ""
                ).strip().upper()

            else:
                member_parent_status = ""

            # Do not silently change an existing Alive dependant
            # into a Deceased/Unknown parent record.
            if member_parent_status != Member.PARENT_ALIVE:
                form.add_error(
                    None,
                    "The parent status on your membership record does not match this dependant record. Please contact the administrator before editing this parent.",
                )

                return render(
                    request,
                    "members/dependants/members_dependant_form.html",
                    {
                        "form": form,
                        "member": member,
                        "historical_non_alive_parent": False,
                    },
                )

            # Never trust the browser-submitted parent status.
            form_data["relationship"] = original_relationship
            form_data["parent_type"] = original_parent_type
            form_data["parent_status"] = Member.PARENT_ALIVE

            form = DependantForm(
                form_data,
                request.FILES or None,
                instance=dependant,
            )

        else:
            # Non-parent records cannot acquire parent-only fields.
            form_data["parent_type"] = ""
            form_data["parent_status"] = ""

            form = DependantForm(
                form_data,
                request.FILES or None,
                instance=dependant,
            )

        # ==================================================
        # VALIDATION
        # ==================================================

        if form.is_valid():

            dep = form.save(commit=False)

            # --------------------------------------------------
            # HISTORICAL NON-ALIVE PARENT
            # --------------------------------------------------

            if historical_non_alive_parent:

                dep.relationship = original_relationship
                dep.parent_type = original_parent_type
                dep.parent_status = original_parent_status

                # Preserve historical identity and location.
                dep.first_name = dependant.first_name
                dep.middle_name = dependant.middle_name
                dep.surname = dependant.surname
                dep.dob = dependant.dob

                dep.country = dependant.country
                dep.county = dependant.county
                dep.sub_county_town = dependant.sub_county_town

                # Preserve the existing lifecycle status.
                dep.status = original_dependant_status

            # --------------------------------------------------
            # EXISTING ALIVE PARENT
            # --------------------------------------------------

            elif original_relationship == Dependant.TYPE_PARENT:

                dep.relationship = original_relationship
                dep.parent_type = original_parent_type
                dep.parent_status = Member.PARENT_ALIVE

                dep.status = "pending"

            # --------------------------------------------------
            # OTHER DEPENDANTS
            # --------------------------------------------------

            else:
                dep.status = "pending"

            # ==================================================
            # DOCUMENT PREPARATION
            # ==================================================

            doc_file = form.cleaned_data.get("document_file")

            doc_title = (
                form.cleaned_data.get("document_title") or ""
            ).strip()

            processed_file = None
            original_filename = None

            if doc_file:

                original_filename = doc_file.name

                try:
                    processed_file = prepare_document_file(
                        uploaded_file=doc_file,
                        member=member,
                        document_title=(
                            doc_title or "Dependant Document"
                        ),
                    )

                except DocumentUploadValidationError as exc:
                    messages.error(
                        request,
                        str(exc),
                    )

                    return render(
                        request,
                        "members/dependants/members_dependant_form.html",
                        {
                            "form": form,
                            "member": member,
                            "historical_non_alive_parent":
                                historical_non_alive_parent,
                        },
                    )

            # ==================================================
            # SAVE
            # ==================================================

            with transaction.atomic():

                dep.updated_at = timezone.now()
                dep.save()

                if processed_file:

                    document = MemberDocument(
                        member=member,
                        dependant=dep,
                        title=doc_title or "Dependant Document",
                        file=processed_file,
                        original_filename=original_filename,
                    )

                    document.full_clean()
                    document.save()

                    generate_document_thumbnail(document)

            messages.success(
                request,
                "Dependant updated successfully.",
            )

            return redirect("members:dependants")

    else:
        form = DependantForm(
            instance=dependant,
        )

    # ======================================================
    # GET OR INVALID POST
    # ======================================================

    return render(
        request,
        "members/dependants/members_dependant_form.html",
        {
            "form": form,
            "member": member,
            "historical_non_alive_parent":
                historical_non_alive_parent,
        },
    )

@login_required
@member_required
def members_delete_dependant(request, pk):
    member = request.user.member

    if not member.can_edit:
        messages.error(
            request,
            "Editing is disabled."
        )
        return redirect("members:dependants")

    dependant = get_object_or_404(
        Dependant,
        pk=pk,
        member=member
    )
    dependant.delete()

    messages.success(
        request,
        "Deleted."
    )
    return redirect("members:dependants")


@login_required
@member_required
def members_dependant_detail(request, pk):
    dependant = get_object_or_404(
        Dependant,
        pk=pk,
        member=request.user.member
    )

    return render(
        request,
        "members/dependants/members_dependants_detail.html",
        {"dependant": dependant}
    )
