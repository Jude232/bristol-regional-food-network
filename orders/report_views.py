import csv
from datetime import timedelta
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from accounts.models import ProducerProfile, User

from .models import Order
from .reporting import (
    administrator_commission_report,
    normalise_date_range,
    parse_report_date,
    previous_week_range,
    producer_settlement_report,
)


def producer_report_required(view_function):
    """Restrict financial information to producer accounts."""

    @login_required
    @wraps(view_function)
    def wrapped_view(
        request: HttpRequest,
        *args,
        **kwargs,
    ) -> HttpResponse:
        if request.user.role != User.Role.PRODUCER:
            raise PermissionDenied(
                "Only producer accounts can view settlements."
            )

        producer = getattr(
            request.user,
            "producer_profile",
            None,
        )

        if producer is None:
            raise PermissionDenied(
                "This account has no producer profile."
            )

        request.producer_profile = producer

        return view_function(
            request,
            *args,
            **kwargs,
        )

    return wrapped_view


def administrator_required(view_function):
    """Restrict network financial reports to administrators."""

    @login_required
    @wraps(view_function)
    def wrapped_view(
        request: HttpRequest,
        *args,
        **kwargs,
    ) -> HttpResponse:
        is_administrator = (
            request.user.is_staff
            or request.user.is_superuser
            or request.user.role == User.Role.ADMIN
        )

        if not is_administrator:
            raise PermissionDenied(
                "Administrator access is required."
            )

        return view_function(
            request,
            *args,
            **kwargs,
        )

    return wrapped_view


def producer_report_dates(request):
    """Resolve producer report dates from query parameters."""

    default_start, default_end = previous_week_range()

    start_date = parse_report_date(
        request.GET.get("start"),
        default_start,
    )

    end_date = parse_report_date(
        request.GET.get("end"),
        default_end,
    )

    return normalise_date_range(
        start_date,
        end_date,
    )


def admin_report_dates(request):
    """Resolve administrator report dates from query parameters."""

    today = timezone.localdate()

    default_start = (
        today - timedelta(days=13)
    )

    start_date = parse_report_date(
        request.GET.get("start"),
        default_start,
    )

    end_date = parse_report_date(
        request.GET.get("end"),
        today,
    )

    return normalise_date_range(
        start_date,
        end_date,
    )


@producer_report_required
def producer_settlement_view(request):
    """Display a producer's weekly settlement report."""

    start_date, end_date = producer_report_dates(
        request
    )

    report = producer_settlement_report(
        producer=request.producer_profile,
        start_date=start_date,
        end_date=end_date,
    )

    return render(
        request,
        "orders/reports/producer_settlement.html",
        {
            "report": report,
        },
    )


@producer_report_required
def producer_settlement_csv(request):
    """Download a producer settlement as a CSV file."""

    start_date, end_date = producer_report_dates(
        request
    )

    report = producer_settlement_report(
        producer=request.producer_profile,
        start_date=start_date,
        end_date=end_date,
    )

    response = HttpResponse(
        content_type="text/csv",
    )

    filename = (
        f"producer-settlement-"
        f"{start_date:%Y-%m-%d}-"
        f"{end_date:%Y-%m-%d}.csv"
    )

    response["Content-Disposition"] = (
        f'attachment; filename="{filename}"'
    )

    writer = csv.writer(response)

    writer.writerow(
        [
            "Settlement Reference",
            report["settlement_reference"],
        ]
    )

    writer.writerow(
        [
            "Producer",
            request.producer_profile.business_name,
        ]
    )

    writer.writerow(
        [
            "Period",
            f"{start_date} to {end_date}",
        ]
    )

    writer.writerow(
        [
            "Status",
            report["settlement_status"],
        ]
    )

    writer.writerow([])

    writer.writerow(
        [
            "Order Number",
            "Delivery Date",
            "Customer",
            "Products",
            "Gross Amount",
            "Commission",
            "Producer Payment",
            "Payment Reference",
        ]
    )

    for producer_order in report["producer_orders"]:
        customer_name = (
            producer_order.order.customer.get_full_name()
            or producer_order.order.customer.email
        )

        products = "; ".join(
            (
                f"{item.quantity:g} x {item.product_name}"
                for item in producer_order.items.all()
            )
        )

        payment = getattr(
            producer_order.order,
            "payment",
            None,
        )

        payment_reference = (
            payment.transaction_reference
            if payment
            else ""
        )

        writer.writerow(
            [
                producer_order.order.order_number,
                producer_order.delivery_at.date(),
                customer_name,
                products,
                producer_order.subtotal,
                producer_order.commission_amount,
                producer_order.producer_payment,
                payment_reference,
            ]
        )

    writer.writerow([])

    writer.writerow(
        [
            "Total Gross",
            report["total_gross"],
        ]
    )

    writer.writerow(
        [
            "Total Commission",
            report["total_commission"],
        ]
    )

    writer.writerow(
        [
            "Total Producer Payment",
            report["total_payment"],
        ]
    )

    writer.writerow(
        [
            "Tax Year Payment Total",
            report["tax_year_payment"],
        ]
    )

    return response


@administrator_required
def commission_report_view(request):
    """Display the administrator network commission report."""

    start_date, end_date = admin_report_dates(
        request
    )

    producer_id = request.GET.get(
        "producer",
        "",
    ).strip()

    order_status = request.GET.get(
        "status",
        "",
    ).strip()

    report = administrator_commission_report(
        start_date=start_date,
        end_date=end_date,
        producer_id=producer_id,
        order_status=order_status,
    )

    producers = ProducerProfile.objects.order_by(
        "business_name"
    )

    return render(
        request,
        "orders/reports/admin_commission.html",
        {
            "report": report,
            "producers": producers,
            "order_status_choices": Order.Status.choices,
        },
    )


@administrator_required
def commission_report_csv(request):
    """Download the administrator commission report as CSV."""

    start_date, end_date = admin_report_dates(
        request
    )

    producer_id = request.GET.get(
        "producer",
        "",
    ).strip()

    order_status = request.GET.get(
        "status",
        "",
    ).strip()

    report = administrator_commission_report(
        start_date=start_date,
        end_date=end_date,
        producer_id=producer_id,
        order_status=order_status,
    )

    response = HttpResponse(
        content_type="text/csv",
    )

    filename = (
        f"network-commission-"
        f"{start_date:%Y-%m-%d}-"
        f"{end_date:%Y-%m-%d}.csv"
    )

    response["Content-Disposition"] = (
        f'attachment; filename="{filename}"'
    )

    writer = csv.writer(response)

    writer.writerow(
        [
            "Network Commission Report",
            f"{start_date} to {end_date}",
        ]
    )

    writer.writerow([])

    writer.writerow(
        [
            "Order Number",
            "Order Date",
            "Order Status",
            "Payment Status",
            "Customer Total",
            "Network Commission",
            "Producer Payments",
            "Producer Breakdown",
        ]
    )

    for order in report["orders"]:
        producer_breakdown = "; ".join(
            (
                f"{producer_order.producer.business_name}: "
                f"gross £{producer_order.subtotal}, "
                f"commission £{producer_order.commission_amount}, "
                f"net £{producer_order.producer_payment}"
                for producer_order
                in order.producer_orders.all()
            )
        )

        writer.writerow(
            [
                order.order_number,
                order.created_at.date(),
                order.get_status_display(),
                order.get_payment_status_display(),
                order.total_amount,
                order.commission_amount,
                order.producer_payment_total,
                producer_breakdown,
            ]
        )

    writer.writerow([])

    writer.writerow(
        [
            "Number of Orders",
            report["order_count"],
        ]
    )

    writer.writerow(
        [
            "Total Order Value",
            report["total_order_value"],
        ]
    )

    writer.writerow(
        [
            "Total Commission",
            report["total_commission"],
        ]
    )

    writer.writerow(
        [
            "Total Producer Payments",
            report["total_producer_payments"],
        ]
    )

    writer.writerow(
        [
            "Year-to-Date Commission",
            report["year_to_date_commission"],
        ]
    )

    return response
