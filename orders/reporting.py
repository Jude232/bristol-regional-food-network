from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from accounts.models import ProducerProfile

from .models import Order, ProducerOrder, money


def previous_week_range(
    reference_date: date | None = None,
) -> tuple[date, date]:
    """Return Monday to Sunday for the previous completed week."""

    reference_date = reference_date or timezone.localdate()

    current_week_start = (
        reference_date
        - timedelta(days=reference_date.weekday())
    )

    period_start = (
        current_week_start
        - timedelta(days=7)
    )

    period_end = (
        current_week_start
        - timedelta(days=1)
    )

    return period_start, period_end


def parse_report_date(
    value: str | None,
    fallback: date,
) -> date:
    """Safely parse an ISO date supplied in a query string."""

    if not value:
        return fallback

    try:
        return date.fromisoformat(value)
    except ValueError:
        return fallback


def normalise_date_range(
    start_date: date,
    end_date: date,
) -> tuple[date, date]:
    """Ensure that report dates are in chronological order."""

    if start_date <= end_date:
        return start_date, end_date

    return end_date, start_date


def uk_tax_year_start(
    reference_date: date | None = None,
) -> date:
    """Return 6 April at the beginning of the current UK tax year."""

    reference_date = reference_date or timezone.localdate()

    current_year_start = date(
        reference_date.year,
        4,
        6,
    )

    if reference_date >= current_year_start:
        return current_year_start

    return date(
        reference_date.year - 1,
        4,
        6,
    )


def producer_settlement_report(
    *,
    producer: ProducerProfile,
    start_date: date,
    end_date: date,
) -> dict:
    """Build a settlement report for one producer."""

    start_date, end_date = normalise_date_range(
        start_date,
        end_date,
    )

    producer_orders = list(
        ProducerOrder.objects.filter(
            producer=producer,
            status=ProducerOrder.Status.DELIVERED,
            delivery_at__date__gte=start_date,
            delivery_at__date__lte=end_date,
        )
        .select_related(
            "order",
            "order__customer",
            "order__payment",
        )
        .prefetch_related(
            "items",
        )
        .order_by(
            "delivery_at",
            "order__order_number",
        )
    )

    total_gross = money(
        sum(
            (
                producer_order.subtotal
                for producer_order in producer_orders
            ),
            Decimal("0.00"),
        )
    )

    total_commission = money(
        sum(
            (
                producer_order.commission_amount
                for producer_order in producer_orders
            ),
            Decimal("0.00"),
        )
    )

    total_payment = money(
        sum(
            (
                producer_order.producer_payment
                for producer_order in producer_orders
            ),
            Decimal("0.00"),
        )
    )

    today = timezone.localdate()
    tax_year_start = uk_tax_year_start(today)

    tax_year_payment = money(
        sum(
            ProducerOrder.objects.filter(
                producer=producer,
                status=ProducerOrder.Status.DELIVERED,
                delivery_at__date__gte=tax_year_start,
                delivery_at__date__lte=today,
            ).values_list(
                "producer_payment",
                flat=True,
            ),
            Decimal("0.00"),
        )
    )

    settlement_reference = (
        f"SET-{producer.id}-"
        f"{start_date:%Y%m%d}-"
        f"{end_date:%Y%m%d}"
    )

    return {
        "producer": producer,
        "start_date": start_date,
        "end_date": end_date,
        "producer_orders": producer_orders,
        "order_count": len(producer_orders),
        "total_gross": total_gross,
        "total_commission": total_commission,
        "total_payment": total_payment,
        "tax_year_start": tax_year_start,
        "tax_year_payment": tax_year_payment,
        "settlement_reference": settlement_reference,
        "settlement_status": "Pending Bank Transfer",
    }


def administrator_commission_report(
    *,
    start_date: date,
    end_date: date,
    producer_id: str = "",
    order_status: str = "",
) -> dict:
    """Build the administrator network commission report."""

    start_date, end_date = normalise_date_range(
        start_date,
        end_date,
    )

    orders = (
        Order.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            payment_status=Order.PaymentStatus.PAID,
        )
        .exclude(
            status=Order.Status.CANCELLED,
        )
        .select_related(
            "customer",
            "payment",
        )
        .prefetch_related(
            "producer_orders__producer",
            "producer_orders__items",
        )
    )

    if producer_id:
        orders = orders.filter(
            producer_orders__producer_id=producer_id
        )

    valid_statuses = {
        value
        for value, _label in Order.Status.choices
    }

    if order_status in valid_statuses:
        orders = orders.filter(
            status=order_status
        )

    order_list = list(
        orders.distinct().order_by("-created_at")
    )

    total_order_value = money(
        sum(
            (
                order.total_amount
                for order in order_list
            ),
            Decimal("0.00"),
        )
    )

    total_commission = money(
        sum(
            (
                order.commission_amount
                for order in order_list
            ),
            Decimal("0.00"),
        )
    )

    total_producer_payments = money(
        sum(
            (
                order.producer_payment_total
                for order in order_list
            ),
            Decimal("0.00"),
        )
    )

    today = timezone.localdate()
    calendar_year_start = date(today.year, 1, 1)

    year_to_date_commission = money(
        sum(
            Order.objects.filter(
                created_at__date__gte=calendar_year_start,
                created_at__date__lte=today,
                payment_status=Order.PaymentStatus.PAID,
            )
            .exclude(
                status=Order.Status.CANCELLED,
            )
            .values_list(
                "commission_amount",
                flat=True,
            ),
            Decimal("0.00"),
        )
    )

    return {
        "start_date": start_date,
        "end_date": end_date,
        "orders": order_list,
        "order_count": len(order_list),
        "total_order_value": total_order_value,
        "total_commission": total_commission,
        "total_producer_payments": (
            total_producer_payments
        ),
        "year_to_date_commission": (
            year_to_date_commission
        ),
        "selected_producer": producer_id,
        "selected_status": order_status,
    }
