from django.shortcuts import render
from django.utils import timezone
from django.db.models import Count, Q, F, Case, When, Value, CharField

from backend.members.models import PaymentRequest


def filtered_payment_requests(request, status):
    now = timezone.now()

    queryset = PaymentRequest.objects.annotate(

        total_required=Count("selected_members", distinct=True),

        total_paid=Count(
            "payments__member",
            filter=Q(payments__status="completed"),
            distinct=True
        ),

    ).annotate(

        lifecycle_status=Case(

            When(
                total_required__gt=0,
                total_paid=F("total_required"),
                then=Value("completed_full")
            ),

            When(
                due_date__lt=now,
                then=Value("completed_partial")
            ),

            When(
                total_paid__gt=0,
                then=Value("in_progress")
            ),

            default=Value("pending"),
            output_field=CharField()
        )
    )

    filtered = queryset.filter(lifecycle_status=status)

    return render(request, "members/admin/payment_request_list.html", {
        "payment_requests": filtered,
        "filter_status": status
    })