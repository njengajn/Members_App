import logging
from collections import Counter

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import strip_tags
from django.views.decorators.http import require_http_methods

from backend.members.models import Member


logger = logging.getLogger(__name__)
User = get_user_model()

MEMBERS_PER_PAGE = 25
SELECTION_SESSION_KEY = "member_invitation_selected_ids"
CLEAR_SELECTION_SESSION_KEY = "clear_member_invitation_selection"

def _eligible_members_for_invitation():
    """
    Return members eligible to receive a portal invitation.

    This deliberately does not change membership status or portal access.
    Members are ordered by UID in ascending order.
    """
    return (
        Member.objects
        .filter(
            status=Member.STATUS_ACTIVE,
            is_portal_access_enabled=True,
            user__is_active=True,
        )
        .select_related("user", "organization")
        .order_by("member_uid", "pk")
    )

def _send_member_invitation(member, setup_url):
    """Send one invitation using the existing password-reset route."""

    email = (member.user.email or "").strip()

    subject = "Your KRO member portal invitation"

    context = {
        "member": member,
        "password_setup_url": setup_url,
    }

    html_body = render_to_string(
        "members/emails/member_invitation.html",
        context,
    )

    text_body = strip_tags(html_body)

    email_message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
    )
    email_message.attach_alternative(html_body, "text/html")

    return email_message.send(fail_silently=False)


@staff_member_required
@require_http_methods(["GET", "POST"])
def admin_member_invitations(request):
    """
    Admin page for inviting eligible members to set up portal passwords.

    GET:
        Search and paginate eligible members.

    POST:
        Validate the complete submitted selection, then send invitations.
    """
    eligible_members = _eligible_members_for_invitation()

    if request.method == "POST":
        raw_ids = request.POST.getlist("member_ids")

        if not raw_ids:
            messages.error(
                request,
                "Select at least one member to invite.",
            )
            return redirect("members_admin:member_invitations")

        # Validate IDs before using them in a database query.
        try:
            selected_ids = list(
                dict.fromkeys(int(value) for value in raw_ids)
            )
        except (TypeError, ValueError):
            messages.error(
                request,
                "The selection contains an invalid member ID. "
                "No invitations were sent.",
            )
            return redirect("members_admin:member_invitations")

        if any(member_id <= 0 for member_id in selected_ids):
            messages.error(
                request,
                "The selection contains an invalid member ID. "
                "No invitations were sent.",
            )
            return redirect("members_admin:member_invitations")

        # Validate the complete selection, not just the current page.
        selected = list(
            eligible_members.filter(pk__in=selected_ids)
        )

        if len(selected) != len(selected_ids):
            messages.error(
                request,
                "One or more selected members are no longer eligible. "
                "No invitations were sent. Refresh the page and review "
                "your selection.",
            )
            return redirect("members_admin:member_invitations")

        # Require one unique, nonblank email per selected account.
        emails = []

        for member in selected:
            email = (member.user.email or "").strip()

            if not email:
                messages.error(
                    request,
                    f"{member.full_name} has no registered email address. "
                    "No invitations were sent.",
                )
                return redirect("members_admin:member_invitations")

            if User.objects.filter(email__iexact=email).count() != 1:
                messages.error(
                    request,
                    f"The email address for {member.full_name} is not "
                    "unique across user accounts. No invitations were sent.",
                )
                return redirect("members_admin:member_invitations")

            emails.append(email)

        duplicates = [
            email
            for email, count in Counter(
                email.casefold() for email in emails
            ).items()
            if count > 1
        ]

        if duplicates:
            messages.error(
                request,
                "The selected members include duplicate email addresses. "
                "No invitations were sent.",
            )
            return redirect("members_admin:member_invitations")

        public_site_url = (settings.PUBLIC_SITE_URL or "").strip().rstrip("/")

        if not public_site_url:
            messages.error(
                request,
                "Not able to connect you at the moment. Please contact support.",
            )
            return redirect("members_admin:member_invitations")

        setup_url = (
            f"{public_site_url}"
            f"{reverse('members:password_reset')}"
        )

        sent = []
        failed = []

        for member in selected:
            try:
                result = _send_member_invitation(member, setup_url)

                if result == 1:
                    sent.append(member.full_name)
                else:
                    failed.append(member.full_name)

            except Exception:
                logger.exception(
                    "Invitation email failed for member ID %s",
                    member.pk,
                )
                failed.append(member.full_name)

        if sent:
            messages.success(
                request,
                f"Invitation email sent to {len(sent)} member(s).",
            )

        if failed:
            messages.warning(
                request,
                "Invitation email could not be confirmed for "
                f"{len(failed)} member(s): {', '.join(failed)}. "
                "Check the email logs before retrying.",
            )

        # Clear the browser's remembered selection after an actual
        # sending attempt. Validation failures above preserve it.
        request.session[CLEAR_SELECTION_SESSION_KEY] = True

        return redirect("members_admin:member_invitations")

    # Search is applied before pagination.
    search_query = request.GET.get("q", "").strip()[:100]

    members = eligible_members

    if search_query:
        members = members.filter(
            Q(member_uid__icontains=search_query)
            | Q(first_name__icontains=search_query)
            | Q(surname__icontains=search_query)
            | Q(user__email__icontains=search_query)
        )

    paginator = Paginator(members, MEMBERS_PER_PAGE)

    page_number = request.GET.get("page", 1)

    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages or 1)

    start_index = page_obj.start_index() if page_obj.object_list else 0
    end_index = page_obj.end_index() if page_obj.object_list else 0

    clear_selection = request.session.pop(
        CLEAR_SELECTION_SESSION_KEY,
        False,
    )

    return render(
        request,
        "members/admin/members/member_invitations.html",
        {
            "members": page_obj.object_list,
            "page_obj": page_obj,
            "paginator": paginator,
            "search_query": search_query,
            "start_index": start_index,
            "end_index": end_index,
            "clear_selection": clear_selection,
            "members_per_page": MEMBERS_PER_PAGE,
        },
    )
