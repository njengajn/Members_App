from django.http import HttpResponse
from django.shortcuts import render
from django.db.models import Sum, Count
from .admin_auth import admin_required
from django.utils import timezone
from datetime import datetime
from backend.members.models import Payment, Claim, Member, PaymentRequest, ClaimSettlement
from django.db.models.functions import TruncMonth
from backend.members.views_admin.admin_auth import admin_required  
from datetime import timedelta, datetime, time, date
from decimal import Decimal
import json
from io import BytesIO
from django.utils.timezone import now
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
)
from reportlab.lib.styles import getSampleStyleSheet
from openpyxl import Workbook
from openpyxl.styles import Font
from calendar import monthrange

@admin_required
def treasurer_control_panel(request):
    """
    Treasurer financial dashboard.
    """

    now = timezone.now()

    # ======================================================
    # TOTAL FUNDS COLLECTED
    # ======================================================
    total_collected = (
        Payment.objects
        .filter(status="completed")
        .aggregate(total=Sum("amount"))["total"] or 0
    )

    # ======================================================
    # OUTSTANDING LIABILITIES
    # ======================================================
    outstanding_requests = PaymentRequest.objects.filter(
        claim__status="approved"
    )

    outstanding_liabilities = sum(
        pr.amount for pr in outstanding_requests
    )

    # ======================================================
    # COMPLIANCE RATE
    # ======================================================
    active_members = Member.objects.filter(
        status="active"
    ).count()

    members_who_paid = (
        Payment.objects
        .filter(status="completed")
        .values("member")
        .distinct()
        .count()
    )

    compliance_rate = 0

    if active_members > 0:
        compliance_rate = int(
            (members_who_paid / active_members) * 100
        )

    # ======================================================
    # PERIOD FILTER
    # ======================================================
    period = request.GET.get("period", "this_month")

    start_date = None
    end_date = None

    # ======================================================
    # THIS MONTH
    # ======================================================
    if period == "this_month":

        start_date = now.replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )

        end_date = now

    # ======================================================
    # LAST MONTH
    # ======================================================
    elif period == "last_month":

        first_day_this_month = now.replace(day=1)

        last_month_end = first_day_this_month - timedelta(days=1)

        start_date = last_month_end.replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )

        end_date = last_month_end.replace(
            hour=23,
            minute=59,
            second=59
        )

    # ======================================================
    # LAST 90 DAYS
    # ======================================================
    elif period == "90_days":

        start_date = now - timedelta(days=90)
        end_date = now

    # ======================================================
    # LAST 6 MONTHS
    # ======================================================
    elif period == "6_months":

        start_date = now - timedelta(days=180)
        end_date = now

    # ======================================================
    # FINANCIAL YEAR
    # STARTS JUNE 1
    # ======================================================
    elif period == "this_year":

        if now.month >= 6:
            fy_year = now.year
        else:
            fy_year = now.year - 1

        start_date = now.replace(
            year=fy_year,
            month=6,
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )

        end_date = now

    # ======================================================
    # CUSTOM RANGE
    # ======================================================
    elif period == "custom":

        custom_start = request.GET.get("start_date")
        custom_end = request.GET.get("end_date")

        if custom_start:

            parsed_start = datetime.strptime(
                custom_start,
                "%Y-%m-%d"
            )

            start_date = timezone.make_aware(
                datetime.combine(
                    parsed_start.date(),
                    time.min
                )
            )

        if custom_end:

            parsed_end = datetime.strptime(
                custom_end,
                "%Y-%m-%d"
            )

            end_date = timezone.make_aware(
                datetime.combine(
                    parsed_end.date(),
                    time.max
                )
            )

    # ======================================================
    # CLAIM SETTLEMENTS
    # ======================================================
    claims_paid_queryset = ClaimSettlement.objects.filter(
        settlement_date__isnull=False
    )

    # ======================================================
    # APPLY DATE FILTERS
    # ======================================================
    if start_date:
        claims_paid_queryset = claims_paid_queryset.filter(
            settlement_date__gte=start_date
        )

    if end_date:
        claims_paid_queryset = claims_paid_queryset.filter(
            settlement_date__lte=end_date
        )

    # ======================================================
    # TOTALS
    # ======================================================
    claims_paid_total = Decimal("0.00")
    deductions_total = Decimal("0.00")
    collected_total = Decimal("0.00")

    for settlement in claims_paid_queryset:

        claims_paid_total += settlement.amount_paid
        deductions_total += settlement.total_deductions
        collected_total += settlement.total_collected

    # ======================================================
    # CONTEXT
    # ======================================================
    context = {

        # Existing
        "total_collected": total_collected,
        "outstanding_liabilities": outstanding_liabilities,
        "compliance_rate": compliance_rate,

        # New claims dashboard
        "claims_paid_total": claims_paid_total,
        "deductions_total": deductions_total,
        "collected_total": collected_total,

        # Filter UI
        "period": period,
        "start_date": request.GET.get("start_date", ""),
        "end_date": request.GET.get("end_date", ""),
    }

    return render(
        request,
        "members/admin/finance/admin_treasurer_dashboard.html",
        context,
    )

@admin_required
def treasurer_control_panelOnHold16_05_26(request):
    """
    Financial overview for treasurer.
    """

    today = timezone.now()

    # ======================================================
    # TOTAL FUNDS COLLECTED (REAL CASH FLOW)
    # ======================================================
    total_collected = (
        Payment.objects
        .filter(status="completed")
        .aggregate(total=Sum("amount"))["total"] or 0
    )

    # ======================================================
    # CLAIMS PAID THIS MONTH
    # ======================================================
    start_of_month = datetime(today.year, today.month, 1, tzinfo=timezone.get_current_timezone())

    claims_paid_this_month = (
        Claim.objects
        .filter(status="settled", created_at__gte=start_of_month)
        .count()
    )

    # ======================================================
    # OUTSTANDING LIABILITIES (CORRECTED)
    # ======================================================
    # Instead of Claim.amount (which does not exist),
    # we sum the related PaymentRequest amounts

    outstanding_requests = PaymentRequest.objects.filter(
        claim__status="approved"
    )

    outstanding_liabilities = sum(
        pr.amount for pr in outstanding_requests
    )

    # ======================================================
    # TOTAL COLLECTED PER REQUEST (ADVANCED - OPTIONAL USE)
    # ======================================================
    # This is more accurate if you want REAL collected vs expected

    total_expected = (
        PaymentRequest.objects
        .filter(status="active")
        .aggregate(total=Sum("amount"))["total"] or 0
    )

    total_actual_collected = (
        Payment.objects
        .filter(status="completed")
        .aggregate(total=Sum("amount"))["total"] or 0
    )

    # ======================================================
    # PAYMENT COMPLIANCE RATE
    # ======================================================
    active_members = Member.objects.filter(status="active").count()

    members_who_paid = (
        Payment.objects
        .filter(status="completed")
        .values("member")
        .distinct()
        .count()
    )

    compliance_rate = 0

    if active_members > 0:
        compliance_rate = int((members_who_paid / active_members) * 100)

    # ======================================================
    # CONTEXT
    # ======================================================
    context = {
        "total_collected": total_collected,
        "claims_paid_this_month": claims_paid_this_month,
        "outstanding_liabilities": outstanding_liabilities,
        "compliance_rate": compliance_rate,
        "total_expected": total_expected,
        "total_actual_collected": total_actual_collected,
    }

    return render(
        request,
        "members/admin/finance/admin_treasurer_dashboard.html",
        context,
    )

@admin_required
def treasurer_analytics_dashboard(request):
    """
    Treasurer analytics dashboard.

    Produces:
    - Monthly income trend
    - Claims paid trend
    - Payment request trend

    All datasets are serialized safely for Chart.js.
    """

    # ======================================================
    # MONTHLY INCOME TREND
    # ======================================================
    # IMPORTANT:
    # Use paid_at because approved_at may be NULL
    # for some valid completed payments.
    # ======================================================

    income_queryset = (
        Payment.objects
        .filter(status="completed")
        .annotate(month=TruncMonth("paid_at"))
        .values("month")
        .annotate(total=Sum("amount"))
        .order_by("month")
    )

    income_trend = []

    for item in income_queryset:

        income_trend.append({
            "month": item["month"].strftime("%Y-%m-%d")
            if item["month"] else "",

            "total": float(item["total"] or 0)
        })

    # ======================================================
    # CLAIMS PAID TREND
    # ======================================================
    # Source of truth:
    # ClaimSettlement.settlement_date
    # ======================================================

    claims_queryset = (
        ClaimSettlement.objects
        .filter(settlement_date__isnull=False)
        .annotate(month=TruncMonth("settlement_date"))
        .values("month")
        .annotate(total=Count("id"))
        .order_by("month")
    )

    claims_trend = []

    for item in claims_queryset:

        claims_trend.append({
            "month": item["month"].strftime("%Y-%m-%d")
            if item["month"] else "",

            "total": item["total"]
        })

    # ======================================================
    # PAYMENT REQUEST TREND
    # ======================================================

    requests_queryset = (
        PaymentRequest.objects
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(total=Count("id"))
        .order_by("month")
    )

    request_trend = []

    for item in requests_queryset:

        request_trend.append({
            "month": item["month"].strftime("%Y-%m-%d")
            if item["month"] else "",

            "total": item["total"]
        })

    # ======================================================
    # CONTEXT
    # ======================================================

    context = {

        # JSON SAFE
        "income_trend": json.dumps(income_trend),

        "claims_trend": json.dumps(claims_trend),

        "request_trend": json.dumps(request_trend),
    }

    return render(
        request,
        "members/admin/finance/admin_treasurer_analytics.html",
        context
    )


# ======================================================
# HELPER:
# DETERMINE REPORT PERIOD
# ======================================================

def get_report_dates(request):

    today = now().date()

    period = request.GET.get(
        "period",
        "this_month"
    )

    # TODAY
    if period == "today":

        start_date = today
        end_date = today

    # THIS MONTH
    elif period == "this_month":

        start_date = today.replace(day=1)
        end_date = today

    # LAST MONTH
    elif period == "last_month":

        first_this_month = today.replace(day=1)

        last_month_end = (
            first_this_month - timedelta(days=1)
        )

        start_date = last_month_end.replace(day=1)

        end_date = last_month_end

    # THIS YEAR
    elif period == "this_year":

        # ----------------------------------------------
        # Financial Year:
        # 1 June -> 31 May
        # ----------------------------------------------

        if today.month >= 6:

            # Current FY started this year

            start_date = date(
                today.year,
                6,
                1
            )

            end_date = today

        else:

            # Current FY started last year

            start_date = date(
                today.year - 1,
                6,
                1
            )

            end_date = today

    # LAST YEAR
    elif period == "last_year":
        # ----------------------------------------------
        # Previous Financial Year
        # ----------------------------------------------
        if today.month >= 6:

            # Previous FY:
            # 1 Jun last year -> 31 May this year

            start_date = date(
                today.year - 1,
                6,
                1
            )

            end_date = date(
                today.year,
                5,
                31
            )

        else:

            # Previous FY:
            # 1 Jun two years ago -> 31 May last year

            start_date = date(
                today.year - 2,
                6,
                1
            )

            end_date = date(
                today.year - 1,
                5,
                31
            )

    # CUSTOM RANGE
    elif period == "custom":

        start_date = request.GET.get(
            "start_date"
        )

        end_date = request.GET.get(
            "end_date"
        )

    # DEFAULT
    else:

        start_date = today.replace(day=1)
        end_date = today

    return (
        start_date,
        end_date,
        period
    )


# ======================================================
# MAIN FINANCE SUMMARY
# ======================================================

@admin_required
def finance_summary(request):

    (
        start_date,
        end_date,
        selected_period
    ) = get_report_dates(request)

    # ==================================================
    # FILTERED PAYMENTS
    # ==================================================

    payments = Payment.objects.filter(
        paid_at__date__range=[
            start_date,
            end_date
        ]
    )

    # ==================================================
    # TOTALS
    # ==================================================

    total_received = payments.aggregate(
        total=Sum("amount")
    )["total"] or 0

    total_claims = payments.filter(
        payment_type="claim"
    ).aggregate(
        total=Sum("amount")
    )["total"] or 0

    total_membership = payments.filter(
        payment_type="membership"
    ).aggregate(
        total=Sum("amount")
    )["total"] or 0

    total_subscription = payments.filter(
        payment_type="subscription"
    ).aggregate(
        total=Sum("amount")
    )["total"] or 0

    total_other = payments.filter(
        payment_type="other"
    ).aggregate(
        total=Sum("amount")
    )["total"] or 0

    # ==================================================
    # OUTSTANDING REQUESTS
    # ==================================================

    outstanding_requests = PaymentRequest.objects.filter(
        status="active"
    ).aggregate(
        total=Sum("amount")
    )["total"] or 0

    # ==================================================
    # TOTAL PAID OUT
    # ==================================================

    total_paid_out = payments.filter(
        payment_type="claim"
    ).aggregate(
        total=Sum("amount")
    )["total"] or 0

    completed_payments = payments.count()

    # ==================================================
    # EXPORTS
    # ==================================================

    export_type = request.GET.get("export")

    if export_type == "pdf":

        return finance_summary_pdf(
        request,
        start_date,
        end_date,
        total_received,
        total_claims,
        total_membership,
        total_subscription,
        total_other,
        outstanding_requests,
        total_paid_out,
        completed_payments,
    )

    if export_type == "excel":

        return finance_summary_excel(
            request,
            start_date,
            end_date,
            total_received,
            total_claims,
            total_membership,
            total_subscription,
            total_other,
            outstanding_requests,
            total_paid_out,
            completed_payments,
        )

    # ==================================================
    # QUERY PARAMS
    # ==================================================

    query_params = request.GET.copy()

    if "export" in query_params:
        query_params.pop("export")

    context = {

        "report_start": start_date,
        "report_end": end_date,

        "selected_period": selected_period,

        "query_params": query_params.urlencode(),

        "total_received": total_received,

        "total_claims": total_claims,

        "total_membership": total_membership,

        "total_subscription": total_subscription,

        "total_other": total_other,

        "outstanding_requests": outstanding_requests,

        "total_paid_out": total_paid_out,

        "completed_payments": completed_payments,
    }

    return render(
        request,
        "members/admin/admin_finance_summary.html",
        context
    )

# ======================================================
# PDF EXPORT
# ======================================================

@admin_required
def finance_summary_pdf(
    request,
    start_date,
    end_date,
    total_received,
    total_claims,
    total_membership,
    total_subscription,
    total_other,
    outstanding_requests,
    total_paid_out,
    completed_payments,
):

    # ==================================================
    # CREATE PDF BUFFER
    # ==================================================

    buffer = BytesIO()

    # ==================================================
    # PDF DOCUMENT SETUP
    # ==================================================

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=30,
    )

    styles = getSampleStyleSheet()

    elements = []

    # ==================================================
    # REPORT TITLE
    # ==================================================

    title = Paragraph(
        """
        <font size="20">
        <b>KRO Welfare Management</b>
        </font>
        <br/>
        Financial Summary Report
        """,
        styles["Title"],
    )

    elements.append(title)

    elements.append(Spacer(1, 20))

    # ==================================================
    # REPORTING PERIOD
    # ==================================================

    report_period = Paragraph(
        f"""
        <b>Reporting Period:</b>
        {start_date.strftime("%d/%m/%Y")}
        to
        {end_date.strftime("%d/%m/%Y")}
        """,
        styles["Normal"],
    )

    elements.append(report_period)

    elements.append(Spacer(1, 20))

    # ==================================================
    # TABLE DATA
    # ==================================================

    data = [

        ["Metric", "Value"],

        ["Total Received",
         f"£{total_received:,.2f}"],

        ["Total Received - Claims",
         f"£{total_claims:,.2f}"],

        ["Total Received - Membership",
         f"£{total_membership:,.2f}"],

        ["Total Received - Subscription",
         f"£{total_subscription:,.2f}"],

        ["Total Received - Other",
         f"£{total_other:,.2f}"],

        ["Outstanding Requests",
         f"£{outstanding_requests:,.2f}"],

        ["Total Paid Out",
         f"£{total_paid_out:,.2f}"],

        ["Payments Completed",
         f"{completed_payments:,}"],
    ]

    # ==================================================
    # CREATE TABLE
    # ==================================================

    table = Table(
        data,
        colWidths=[320, 160]
    )

    # ==================================================
    # TABLE STYLING
    # ==================================================

    table.setStyle(
        TableStyle([

            # HEADER
            ("BACKGROUND",
             (0, 0),
             (-1, 0),
             colors.HexColor("#1f2937")),

            ("TEXTCOLOR",
             (0, 0),
             (-1, 0),
             colors.white),

            ("FONTNAME",
             (0, 0),
             (-1, 0),
             "Helvetica-Bold"),

            ("FONTSIZE",
             (0, 0),
             (-1, 0),
             12),

            ("BOTTOMPADDING",
             (0, 0),
             (-1, 0),
             12),

            # BODY
            ("BACKGROUND",
             (0, 1),
             (-1, -1),
             colors.whitesmoke),

            ("FONTNAME",
             (0, 1),
             (-1, -1),
             "Helvetica"),

            ("FONTSIZE",
             (0, 1),
             (-1, -1),
             11),

            ("GRID",
             (0, 0),
             (-1, -1),
             1,
             colors.grey),

            ("ALIGN",
             (1, 1),
             (-1, -1),
             "RIGHT"),

            ("BOTTOMPADDING",
             (0, 1),
             (-1, -1),
             8),
        ])
    )

    elements.append(table)

    elements.append(Spacer(1, 30))

    # ==================================================
    # FOOTER
    # ==================================================

    footer = Paragraph(
        """
        Generated automatically by
        KRO Welfare Management System
        """,
        styles["Italic"],
    )

    elements.append(footer)

    # ==================================================
    # BUILD PDF
    # ==================================================

    doc.build(elements)

    pdf = buffer.getvalue()

    buffer.close()

    # ==================================================
    # HTTP RESPONSE
    # ==================================================

    response = HttpResponse(
        content_type="application/pdf"
    )

    response[
        "Content-Disposition"
    ] = (
        'attachment; filename="finance_summary.pdf"'
    )

    response.write(pdf)

    return response

# ======================================================
# EXCEL EXPORT
# ======================================================

@admin_required
def finance_summary_excel(
    request,
    start_date,
    end_date,
    total_received,
    total_claims,
    total_membership,
    total_subscription,
    total_other,
    outstanding_requests,
    total_paid_out,
    completed_payments,
):

    # ==================================================
    # CREATE WORKBOOK
    # ==================================================

    workbook = Workbook()

    sheet = workbook.active

    sheet.title = "Finance Summary"

    # ==================================================
    # REPORT TITLE
    # ==================================================

    sheet["A1"] = "KRO Welfare Management"

    sheet["A1"].font = Font(
        bold=True,
        size=16
    )

    sheet["A3"] = "Financial Summary Report"

    sheet["A3"].font = Font(
        bold=True,
        size=13
    )

    # ==================================================
    # REPORT PERIOD
    # ==================================================

    sheet["A5"] = "Reporting Period"

    sheet["A5"].font = Font(bold=True)

    sheet["B5"] = (
        f"{start_date.strftime('%d/%m/%Y')} "
        f"to "
        f"{end_date.strftime('%d/%m/%Y')}"
    )

    # ==================================================
    # TABLE HEADERS
    # ==================================================

    sheet["A7"] = "Metric"

    sheet["B7"] = "Value"

    sheet["A7"].font = Font(bold=True)
    sheet["B7"].font = Font(bold=True)

    # ==================================================
    # TABLE DATA
    # ==================================================

    rows = [

        ["Total Received",
         float(total_received)],

        ["Total Received - Claims",
         float(total_claims)],

        ["Total Received - Membership",
         float(total_membership)],

        ["Total Received - Subscription",
         float(total_subscription)],

        ["Total Received - Other",
         float(total_other)],

        ["Outstanding Requests",
         float(outstanding_requests)],

        ["Total Paid Out",
         float(total_paid_out)],

        ["Payments Completed",
         completed_payments],
    ]

    # ==================================================
    # WRITE DATA TO SHEET
    # ==================================================

    row_number = 8

    for row in rows:

        sheet.cell(
            row=row_number,
            column=1,
            value=row[0]
        )

        sheet.cell(
            row=row_number,
            column=2,
            value=row[1]
        )

        row_number += 1

    # ==================================================
    # COLUMN WIDTHS
    # ==================================================

    sheet.column_dimensions["A"].width = 40

    sheet.column_dimensions["B"].width = 25

    # ==================================================
    # RESPONSE
    # ==================================================

    response = HttpResponse(
        content_type=(
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        )
    )

    response[
        "Content-Disposition"
    ] = (
        'attachment; filename="finance_summary.xlsx"'
    )

    workbook.save(response)

    return response
