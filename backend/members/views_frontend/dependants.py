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


        parent_status = (
            request.POST.get(
                "parent_status",
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


        # ==================================================
        # FORM VALIDATION
        # ==================================================

        form_valid = form.is_valid()

        additional_errors = []


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
            # Parent type is required.
            # ----------------------------------------------

            if parent_type not in {
                "MOTHER",
                "FATHER",
            }:

                additional_errors.append(
                    "Please select Mother or Father."
                )


            # ----------------------------------------------
            # Parent status is required.
            # ----------------------------------------------

            if parent_status not in {
                "ALIVE",
                "DECEASED",
                "UNKNOWN",
            }:

                additional_errors.append(
                    "Please select the parent status."
                )


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


        else:

            # Parent-only values are irrelevant to all
            # other relationship types.

            parent_type = ""
            parent_status = ""


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
                and parent_status == "ALIVE"
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
    Edit an existing dependant.

    Existing behaviour:
    - Only the logged-in member can edit their own dependant.
    - Editing must be enabled for the member.
    - A normal dependant edit resets the dependant to pending
      so that the updated information can be reviewed again.

    Parent business rules:
    - Parent type must be Mother or Father.
    - Parent status must be Alive, Deceased or Unknown.
    - An Alive parent may retain their details.
    - A Deceased parent is always retired.
    - An Unknown parent has no identifying or location information.
    - An Unknown parent is always retired.
    - Deceased and Unknown parents can never become Active.
    """

    member = request.user.member

    # Preserve the existing edit-expiry check.
    member.check_can_edit_expiry()

    # Editing must be enabled.
    if not member.can_edit:
        messages.error(
            request,
            "Editing is disabled."
        )
        return redirect("members:dependants")

    # Only allow the logged-in member to edit their own dependant.
    dependant = get_object_or_404(
        Dependant,
        pk=pk,
        member=member
    )

    form = DependantForm(
        request.POST or None,
        instance=dependant
    )

    if form.is_valid():
        dep = form.save(commit=False)

        relationship = (
            dep.relationship or ""
        ).strip().upper()

        parent_type = (
            dep.parent_type or ""
        ).strip().upper()

        parent_status = (
            dep.parent_status or ""
        ).strip().upper()

        # ==========================================================
        # PARENT
        # ==========================================================

        if relationship == Dependant.TYPE_PARENT:

            # Parent type must be Mother or Father.
            if parent_type not in {
                Dependant.PARENT_MOTHER,
                Dependant.PARENT_FATHER,
            }:
                form.add_error(
                    "parent_type",
                    "Please select Mother or Father."
                )

            # Parent status must be explicitly selected.
            if parent_status not in {
                Dependant.PARENT_ALIVE,
                Dependant.PARENT_DECEASED,
                Dependant.PARENT_UNKNOWN,
            }:
                form.add_error(
                    "parent_status",
                    "Please select the parent's status."
                )

            # ------------------------------------------------------
            # UNKNOWN PARENT
            # ------------------------------------------------------
            #
            # UNKNOWN is a deliberate business state.
            #
            # It means we know this is a parent and whether the
            # parent is Mother/Father, but we do not have any
            # identifying or location information.
            #
            # The dependant can NEVER be Active in this state.
            # ------------------------------------------------------

            if parent_status == Dependant.PARENT_UNKNOWN:

                # Explicitly remove all identifying information.
                dep.first_name = ""
                dep.middle_name = ""
                dep.surname = ""
                dep.dob = None

                # Explicitly remove all location information.
                dep.country = ""
                dep.county = ""
                dep.sub_county_town = ""

                # UNKNOWN parents are permanently protected
                # from activation.
                dep.status = Dependant.STATUS_RETIRED

            # ------------------------------------------------------
            # DECEASED PARENT
            # ------------------------------------------------------

            elif parent_status == Dependant.PARENT_DECEASED:

                # A deceased parent can never become Active.
                dep.status = Dependant.STATUS_RETIRED

            # ------------------------------------------------------
            # ALIVE PARENT
            # ------------------------------------------------------

            elif parent_status == Dependant.PARENT_ALIVE:

                # Preserve the existing approval workflow.
                # Editing an eligible parent requires review again.
                dep.status = Dependant.STATUS_PENDING

        # ==========================================================
        # NON-PARENT DEPENDANT
        # ==========================================================

        else:
            # Preserve existing behaviour:
            # editing an ordinary dependant resets approval.
            dep.status = Dependant.STATUS_PENDING

        # If the server-side lifecycle checks above added an error,
        # do not save the dependant.
        if form.errors:
            return render(
                request,
                "members/dependants/members_dependants_form.html",
                {
                    "form": form,
                    "member": member,
                }
            )

        # Save only after all server-side rules have passed.
        dep.save()

        messages.success(
            request,
            "Updated."
        )

        return redirect(
            "members:dependants"
        )

    return render(
        request,
        "members/dependants/members_dependants_form.html",
        {
            "form": form,
            "member": member,
        }
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
