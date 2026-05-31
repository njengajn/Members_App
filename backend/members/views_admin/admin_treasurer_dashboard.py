from datetime import date, datetime, timedelta, time
from io import BytesIO

from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.timezone import now

from openpyxl import Workbook
from openpyxl.styles import Font

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet

from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from backend.members.decorators import admin_required
from backend.members.models import (
    ClaimSettlement,
    Member,
    Payment,
    PaymentRequest,
)

# ======================================================
# TREASURER REPORT DATA
# ======================================================

def get_treasurer_report_data(request):

    today = now().date()

    # ==================================================
    # DEFAULT PERIOD
    # ==================================================

    period = request.GET.get(
        "period",
        "this_year"
    )

    # ==================================================
    # THIS MONTH
    # ==================================================

    if period == "this_month":

        start_date = today.replace(day=1)

        end_date = today

    # ==================================================
    # LAST MONTH
    # ==================================================

    elif period == "last_month":

        first_this_month = today.replace(day=1)

        end_date = (
            first_this_month - timedelta(days=1)
        )

        start_date = end_date.replace(day=1)

    # ==================================================
    # LAST 90 DAYS
    # ==================================================

    elif period == "90_days":

        start_date = today - timedelta(days=90)

        end_date = today

    # ==================================================
    # LAST 6 MONTHS
    # ==================================================

    elif period == "6_months":

        start_date = today - timedelta(days=180)

        end_date = today

    # ==================================================
    # CURRENT FINANCIAL YEAR
    #
    # FY:
    # 1 June -> 31 May
    # ==================================================

    elif period == "this_year":

        if today.month >= 6:

            fy_start_year = today.year

        else:

            fy_start_year = today.year - 1

        start_date = date(
            fy_start_year,
            6,
            1
        )

        end_date = today

    # ==================================================
    # PREVIOUS FINANCIAL YEAR
    # ==================================================

    elif period == "last_year":

        if today.month >= 6:

            fy_start_year = today.year - 1

        else:

            fy_start_year = today.year - 2

        start_date = date(
            fy_start_year,
            6,
            1
        )

        end_date = date(
            fy_start_year + 1,
            5,
            31
        )

    # ==================================================
    # CUSTOM RANGE
    # ==================================================

    elif period == "custom":

        start_date_value = request.GET.get(
            "start_date"
        )

        end_date_value = request.GET.get(
            "end_date"
        )

        # =============================================
        # SAFETY CHECK
        # =============================================

        if start_date_value and end_date_value:

            start_date = datetime.strptime(
                start_date_value,
                "%Y-%m-%d"
            ).date()

            end_date = datetime.strptime(
                end_date_value,
                "%Y-%m-%d"
            ).date()

        else:

            # Fallback to current month

            start_date = today.replace(day=1)

            end_date = today

    # ==================================================
    # DEFAULT FALLBACK
    # ==================================================

    else:

        start_date = today.replace(day=1)

        end_date = today

    # ==================================================
    # DATETIME RANGE
    # ==================================================

    start_datetime = timezone.make_aware(
        datetime.combine(
            start_date,
            datetime.min.time()
        )
    )

    end_datetime = timezone.make_aware(
        datetime.combine(
            end_date,
            datetime.max.time()
        )
    )

    # ==================================================
    # PAYMENTS
    # ==================================================

    payments = Payment.objects.filter(

        status=Payment.STATUS_COMPLETED,

        paid_at__gte=start_datetime,

        paid_at__lte=end_datetime,
    )

    # ==================================================
    # FUNDS COLLECTED
    # ==================================================

    collected_total = payments.filter(
        payment_type__in=[
            "membership",
            "subscription",
            "other",
        ]
    ).aggregate(
        total=Sum("amount")
    )["total"] or 0

    # ==================================================
    # CLAIM SETTLEMENTS
    # ==================================================

    claim_settlements = ClaimSettlement.objects.filter(
        settlement_date__gte=start_date,
        settlement_date__lte=end_date,
    )

    # ==================================================
    # TOTAL DEDUCTIONS
    # ==================================================

    deductions_total = sum(
        settlement.total_deductions
        for settlement in claim_settlements
    )

    # ==================================================
    # CLAIMS PAID
    # ==================================================

    claims_paid_total = sum(
        settlement.amount_paid
        for settlement in claim_settlements
    )

    # ==================================================
    # ACTIVE MEMBERS
    # ==================================================

    active_members = Member.objects.filter(
        status="active"
    )

    total_members = active_members.count()

    # ==================================================
    # COMPLIANCE
    # ==================================================
    # Compliance should measure:
    #
    # Members who paid requests
    # issued during the selected period.
    # ==================================================

    requests = PaymentRequest.objects.filter(

        request_type__in=[
            "membership",
            "subscription",
        ],

        created_at__date__gte=start_date,

        created_at__date__lte=end_date,
    )

    # --------------------------------------------------
    # EXPECTED MEMBERS
    # --------------------------------------------------

    expected_member_ids = set()

    for req in requests:

        expected_member_ids.update(

            req.selected_members.values_list(
                "id",
                flat=True
            )
        )

    # --------------------------------------------------
    # PAID MEMBERS
    # --------------------------------------------------
    # IMPORTANT:
    # ONLY members who paid
    # THESE SAME REQUESTS
    # --------------------------------------------------

    paid_member_ids = set()

    for req in requests:

        paid_member_ids.update(

            req.paid_members.values_list(
                "id",
                flat=True
            )
        )

    # --------------------------------------------------
    # COUNTS
    # --------------------------------------------------

    expected_count = len(
        expected_member_ids
    )

    paid_count = len(
        paid_member_ids
    )

    # --------------------------------------------------
    # COMPLIANCE RATE
    # --------------------------------------------------

    compliance_rate = 0

    if expected_count > 0:

        compliance_rate = round(
            (
                paid_count
                / expected_count
            ) * 100,
            1
        )
    
    # ==================================================
    # PERIOD LABEL
    # ==================================================

    period_labels = {

        "this_month": "This Month",

        "last_month": "Last Month",

        "90_days": "Last 90 Days",

        "6_months": "Last 6 Months",

        "this_year": "Current Financial Year",

        "last_year": "Previous Financial Year",

        "custom": "Custom Period",
    }

    period_label = period_labels.get(
        period,
        "Current Financial Year"
    )

    return {

        "period": period,

        "start_date": start_date,

        "end_date": end_date,

        "collected_total": collected_total,

        "deductions_total": deductions_total,

        "claims_paid_total": claims_paid_total,

        "compliance_rate": compliance_rate,
        
        "period_label": period_label,
    }

# ======================================================
# TREASURER PDF EXPORT
# ======================================================

@admin_required
def treasurer_dashboard_pdf(request):

    # ==================================================
    # GET REPORT DATA
    # ==================================================

    context = get_treasurer_report_data(request)

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4
    )

    styles = getSampleStyleSheet()

    elements = []

    # ==================================================
    # TITLE
    # ==================================================

    title = Paragraph(
        """
        <font size="20">
        <b>Treasurer Financial Report</b>
        </font>
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
        {context["start_date"].strftime("%d/%m/%Y")}
        to
        {context["end_date"].strftime("%d/%m/%Y")}
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

        [
            "Funds Collected",
            f"£{context['collected_total']:,.2f}"
        ],

        [
            "Claims Paid",
            f"£{context['claims_paid_total']:,.2f}"
        ],

        [
            "Total Deductions",
            f"£{context['deductions_total']:,.2f}"
        ],

        [
            "Compliance",
            f"{context['compliance_rate']}%"
        ],
    ]

    # ==================================================
    # TABLE
    # ==================================================

    table = Table(
        data,
        colWidths=[300, 180]
    )

    table.setStyle(TableStyle([

        ("BACKGROUND",
         (0, 0),
         (-1, 0),
         colors.HexColor("#1f2937")),

        ("TEXTCOLOR",
         (0, 0),
         (-1, 0),
         colors.white),

        ("GRID",
         (0, 0),
         (-1, -1),
         1,
         colors.grey),

        ("FONTNAME",
         (0, 0),
         (-1, 0),
         "Helvetica-Bold"),

        ("BOTTOMPADDING",
         (0, 0),
         (-1, 0),
         12),

    ]))

    elements.append(table)

    # ==================================================
    # BUILD PDF
    # ==================================================

    doc.build(elements)

    pdf = buffer.getvalue()

    buffer.close()

    # ==================================================
    # RESPONSE
    # ==================================================

    response = HttpResponse(
        content_type="application/pdf"
    )

    response[
        "Content-Disposition"
    ] = (
        'attachment; filename="treasurer_report.pdf"'
    )

    response.write(pdf)

    return response

# ======================================================
# TREASURER EXCEL EXPORT
# ======================================================

@admin_required
def treasurer_dashboard_excel(request):

    # ==================================================
    # GET REPORT DATA
    # ==================================================

    context = get_treasurer_report_data(request)

    workbook = Workbook()

    sheet = workbook.active

    sheet.title = "Treasurer Report"

    # ==================================================
    # TITLE
    # ==================================================

    sheet["A1"] = "Treasurer Financial Report"

    sheet["A1"].font = Font(
        bold=True,
        size=16
    )

    # ==================================================
    # REPORT PERIOD
    # ==================================================

    sheet["A3"] = "Reporting Period"

    sheet["B3"] = (
        f"{context['start_date'].strftime('%d/%m/%Y')} "
        f"to "
        f"{context['end_date'].strftime('%d/%m/%Y')}"
    )

    # ==================================================
    # HEADERS
    # ==================================================

    sheet["A5"] = "Metric"

    sheet["B5"] = "Value"

    sheet["A5"].font = Font(bold=True)

    sheet["B5"].font = Font(bold=True)

    # ==================================================
    # DATA
    # ==================================================

    rows = [

        [
            "Funds Collected",
            float(context["collected_total"])
        ],

        [
            "Claims Paid",
            float(context["claims_paid_total"])
        ],

        [
            "Total Deductions",
            float(context["deductions_total"])
        ],

        [
            "Compliance",
            context["compliance_rate"]
        ],
    ]

    row_number = 6

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

    sheet.column_dimensions["A"].width = 35

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
        'attachment; filename="treasurer_report.xlsx"'
    )

    workbook.save(response)

    return response

# ======================================================
# TREASURER DASHBOARD
# ======================================================

@admin_required
def treasurer_dashboard(request):

    today = now().date()

    # ==================================================
    # DEFAULT PERIOD:
    # CURRENT FINANCIAL YEAR
    #
    # Financial Year:
    # 1 June -> 31 May
    # ==================================================

    period = request.GET.get(
        "period",
        "this_year"
    )

    # ==================================================
    # THIS MONTH
    # ==================================================

    if period == "this_month":

        start_date = today.replace(day=1)

        end_date = today

    # ==================================================
    # LAST MONTH
    # ==================================================

    elif period == "last_month":

        first_this_month = today.replace(day=1)

        end_date = (
            first_this_month - timedelta(days=1)
        )

        start_date = end_date.replace(day=1)

    # ==================================================
    # LAST 90 DAYS
    # ==================================================

    elif period == "90_days":

        start_date = today - timedelta(days=90)

        end_date = today

    # ==================================================
    # LAST 6 MONTHS
    # ==================================================

    elif period == "6_months":

        start_date = today - timedelta(days=180)

        end_date = today

    # ==================================================
    # CURRENT FINANCIAL YEAR
    # ==================================================
    # Financial Year:
    # 1 June -> 31 May
    # ==================================================

    elif period == "this_year":

        # ----------------------------------------------
        # Example:
        #
        # Today = 24 May 2026
        #
        # Current FY:
        # 01/06/2025 -> 24/05/2026
        # ----------------------------------------------

        if today.month >= 6:

            fy_start = today.year

        else:

            fy_start = today.year - 1

        start_date = date(
            fy_start,
            6,
            1
        )

        end_date = today

    # ==================================================
    # PREVIOUS FINANCIAL YEAR
    # ==================================================

    elif period == "last_year":

        # ----------------------------------------------
        # Example:
        #
        # Today = 24 May 2026
        #
        # Previous FY:
        # 01/06/2024 -> 31/05/2025
        # ----------------------------------------------

        if today.month >= 6:

            previous_fy_start = today.year - 1

        else:

            previous_fy_start = today.year - 2

        start_date = date(
            previous_fy_start,
            6,
            1
        )

        end_date = date(
            previous_fy_start + 1,
            5,
            31
        )

    # ==================================================
    # CUSTOM RANGE
    # ==================================================

    elif period == "custom":

        start_date = request.GET.get(
            "start_date"
        )

        end_date = request.GET.get(
            "end_date"
        )

    # ==================================================
    # DEFAULT FALLBACK
    # ==================================================

    else:

        start_date = today.replace(day=1)

        end_date = today

    # ==================================================
    # PAYMENTS
    #
    # Incoming funds only
    # ==================================================

    payments = Payment.objects.filter(
        paid_at__date__range=[
            start_date,
            end_date
        ]
    )

    # ==================================================
    # TOTAL FUNDS COLLECTED
    #
    # Excludes claim payouts
    # ==================================================

    collected_total = payments.filter(
        payment_type__in=[
            "membership",
            "subscription",
            "other",
        ]
    ).aggregate(
        total=Sum("amount")
    )["total"] or 0

    # ==================================================
    # CLAIM SETTLEMENTS
    # ==================================================

    claim_settlements = ClaimSettlement.objects.filter(
        settlement_date__range=[
            start_date,
            end_date
        ]
    )

    # ==================================================
    # TOTAL DEDUCTIONS
    # ==================================================

    deductions_total = sum(
        settlement.total_deductions
        for settlement in claim_settlements
    )

    # ==================================================
    # NET CLAIMS PAID
    #
    # amount_paid is a PROPERTY
    # not a database field.
    # Must be calculated in Python.
    # ==================================================

    claims_paid_total = sum(
        settlement.amount_paid
        for settlement in claim_settlements
    )

    # ==================================================
    # COMPLIANCE
    # ==================================================
    # Members who made membership/subscription
    # payments during the selected period.
    # ==================================================

    active_members = Member.objects.filter(
        is_active=True
    )

    total_members = active_members.count()

    compliant_members = active_members.filter(
        payment__payment_type__in=[
            "membership",
            "subscription",
        ],
        payment__paid_at__date__range=[
            start_date,
            end_date
        ]
    ).distinct().count()

    compliance_rate = 0

    if total_members > 0:

        compliance_rate = round(
            (compliant_members / total_members) * 100,
            1
        )

    # ==================================================
    # CONTEXT
    # ==================================================

    context = {

        "period": period,

        "start_date": start_date,

        "end_date": end_date,

        "collected_total": collected_total,

        "deductions_total": deductions_total,

        "claims_paid_total": claims_paid_total,

        "compliance_rate": compliance_rate,
    }

    return render(
        request,
        "members/admin/finance/admin_treasurer_dashboard.html",
        context
    )