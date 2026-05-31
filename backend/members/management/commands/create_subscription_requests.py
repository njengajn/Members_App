from decimal import Decimal
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from backend.members.models import Member
from backend.members.models import PaymentRequest
from backend.members.models import Notification


class Command(BaseCommand):
    """
    Automatically create annual subscription
    payment requests for active members.

    Runs yearly from:
    May 24th → May 31st

    Renewal deadline:
    June 1st midnight
    """

    help = (
        "Create annual subscription payment requests "
        "for unpaid active members."
    )

    # =========================================
    # CONFIG
    # =========================================

    SUBSCRIPTION_AMOUNT = Decimal("50.00")

    REQUEST_TITLE = "Annual Membership Subscription"

    DESCRIPTION = (
        "Annual membership subscription renewal."
    )

    DAYS_TO_DUE = 7

    # =========================================
    # COMMAND
    # =========================================

    def handle(self, *args, **kwargs):

        now = timezone.now()

        current_year = now.year

        # =====================================
        # ONLY RUN DURING RENEWAL WINDOW
        # =====================================

        if not (
            now.month == 5 and
            24 <= now.day <= 31
        ):

            self.stdout.write(
                self.style.WARNING(
                    "Not subscription request period."
                )
            )

            return

        # =====================================
        # DUE DATE = JUNE 1ST MIDNIGHT
        # =====================================

        due_date = timezone.make_aware(
            datetime(current_year, 6, 1, 0, 0, 0)
        )

        # =====================================
        # TARGET MEMBERS
        # =====================================

        members = Member.objects.filter(
            status=Member.STATUS_ACTIVE
        )

        created_count = 0

        for member in members:

            # =================================
            # MEMBER ALREADY PAID CURRENT YEAR
            # =================================

            if member.subscription_year == current_year:
                continue

            # =================================
            # PREVENT DUPLICATE REQUESTS
            # =================================

            existing_request = PaymentRequest.objects.filter(
                member=member,
                request_type="subscription",
                title=self.REQUEST_TITLE,
                due_date__year=current_year,
                status=PaymentRequest.STATUS_ACTIVE
            ).exists()

            if existing_request:
                continue

            # =================================
            # CREATE PAYMENT REQUEST
            # =================================

            payment_request = PaymentRequest.objects.create(
                member=member,
                amount=self.SUBSCRIPTION_AMOUNT,
                due_date=due_date,
                description=self.DESCRIPTION,
                request_type="subscription",
                title=self.REQUEST_TITLE,
                status=PaymentRequest.STATUS_ACTIVE,
                days=self.DAYS_TO_DUE,
                payment_method=PaymentRequest.METHOD_BOTH,
                viewable_by_all=False,
            )

            # =================================
            # LIMIT REQUEST TO MEMBER ONLY
            # =================================

            payment_request.selected_members.add(member)

            # =================================
            # NOTIFICATION
            # =================================

            Notification.objects.create(
                user=member.user,
                title="Annual Subscription Due",
                message=(
                    f"Your annual subscription payment "
                    f"request for {current_year} "
                    f"has been created. "
                    f"Please complete payment before "
                    f"1st June."
                ),
                notification_type="payment"
            )

            created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{created_count} subscription requests created."
            )
        )
    