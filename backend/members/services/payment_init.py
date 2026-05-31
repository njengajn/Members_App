"""
Initialize payment tracking.
"""
from members.models import Member, MemberPaymentStatus


def initialize_member_statuses(payment_request):
    """
    When a request is created,
    mark all target members as UNPAID.
    """

    if payment_request.viewable_by_all:
        members = Member.objects.filter(status=Member.STATUS_ACTIVE)
    else:
        members = payment_request.selected_members.all()

    for m in members:
        MemberPaymentStatus.objects.get_or_create(
            member=m,
            payment_request=payment_request,
            defaults={"status": MemberPaymentStatus.STATUS_UNPAID},
        )
        
