from django.core.management.base import BaseCommand
from django.utils import timezone

from backend.members.models import Member
from backend.members.models import PaymentRequest
from backend.members.models import Notification


class Command(BaseCommand):
    """
    Retire members who have not paid
    annual subscription by June 1st.
    """

    help = (
        "Retire unpaid members after "
        "annual subscription deadline."
    )

    def handle(self, *args, **kwargs):

        now = timezone.now()

        current_year = now.year

        # =====================================
        # ONLY RUN JUNE 1ST+
        # =====================================

        if now.month < 6:

            self.stdout.write(
                self.style.WARNING(
                    "Retirement period not reached."
                )
            )

            return

        # =====================================
        # ACTIVE MEMBERS ONLY
        # =====================================

        members = Member.objects.filter(
            status=Member.STATUS_ACTIVE
        )

        retired_count = 0

        for member in members:

            # =================================
            # CHECK SUBSCRIPTION REQUEST
            # =================================

            subscription_request = PaymentRequest.objects.filter(
                member=member,
                request_type="subscription",
                due_date__year=current_year,
            ).first()

            # =================================
            # NO REQUEST FOUND
            # =================================

            if not subscription_request:

                member.status = Member.STATUS_RETIRED

                member.retired_reason = (
                    "No annual subscription request found."
                )

                member.retired_at = timezone.now()

                member.save()

                retired_count += 1

                continue

            # =================================
            # MEMBER NOT PAID
            # =================================

            payment_status = (
                subscription_request.member_payment_status(
                    member
                )
            )

            if payment_status != "paid":

            # =====================================
            # RETIRE MEMBER SAFELY
            # =====================================

                member.retire(
                    reason=(
                        f"Subscription unpaid "
                        f"for {current_year}"
                    )
                )

                member.retired_at = timezone.now()

                member.save()

                # =============================
                # NOTIFICATION
                # =============================

                Notification.objects.create(
                    user=member.user,
                    title="Membership Retired",
                    message=(
                        "Your membership has been retired "
                        "because annual subscription "
                        "was not paid before June 1st."
                    ),
                    notification_type="alert"
                )

                retired_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{retired_count} members retired."
            )
        )
