from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from accounts.models import ProducerProfile

from .models import Order, ProducerOrder, money

#This file reads completed order data and calculates producer settlements and administrator commission totals.
#The reporting logic is separated from the views so it is reusable and easier to test.

def previous_week_range(
    reference_date: date | None = None,
) -> tuple[date, date]:
    """
    Return the Monday and Sunday dates for the previous full week.

    This is used as the default date range for weekly producer
    settlement reports.
    """

    # Use today's local date when no date is provided.
    reference_date = reference_date or timezone.localdate()

    # Find the Monday at the start of the current week.
    current_week_start = (
        reference_date
        - timedelta(days=reference_date.weekday())
    )

    # The previous week starts seven days before the current Monday.
    period_start = (
        current_week_start
        - timedelta(days=7)
    )

    # The previous week ends on the Sunday before the current Monday.
    period_end = (
        current_week_start
        - timedelta(days=1)
    )

    return period_start, period_end


def parse_report_date(
    value: str | None,
    fallback: date,
) -> date:
    """
    Convert a date from a URL query string into a Python date.

    If the value is missing or invalid, the fallback date is used.
    """

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
    """
    Make sure the start date comes before the end date.

    If the user enters the dates in the wrong order, they are swapped.
    """

    if start_date <= end_date:
        return start_date, end_date

    return end_date, start_date


def uk_tax_year_start(
    reference_date: date | None = None,
) -> date:
    """
    Return the start of the current UK tax year.

    The UK tax year begins on 6 April.
    """

    reference_date = reference_date or timezone.localdate()

    current_year_start = date(
        reference_date.year,
        4,
        6,
    )

    # If the current date is on or after 6 April, the tax year
    # started in the current calendar year.
    if reference_date >= current_year_start:
        return current_year_start

    # Otherwise, the tax year started on 6 April of the previous year.
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
    """
    Build a financial settlement report for one producer.

    Only delivered producer orders within the selected date range
    are included.
    """

    # Correct the date range if the dates were entered backwards.
    start_date, end_date = normalise_date_range(
        start_date,
        end_date,
    )

    # Retrieve delivered orders belonging to the selected producer.
    producer_orders = list(
        ProducerOrder.objects.filter(
            producer=producer,
            status=ProducerOrder.Status.DELIVERED,
            delivery_at__date__gte=start_date,
            delivery_at__date__lte=end_date,
        )
        # Load related objects efficiently to reduce database queries.
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

    # Calculate the total value of the producer's delivered orders.
    total_gross = money(
        sum(
            (
                producer_order.subtotal
                for producer_order in producer_orders
            ),
            Decimal("0.00"),
        )
    )

    # Calculate the total 5% platform commission.
    total_commission = money(
        sum(
            (
                producer_order.commission_amount
                for producer_order in producer_orders
            ),
            Decimal("0.00"),
        )
    )

    # Calculate the total amount owed to the producer.
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

    # Find the beginning of the current UK tax year.
    tax_year_start = uk_tax_year_start(today)

    # Calculate how much the producer has earned during the
    # current UK tax year.
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

    # Create a readable reference for the settlement period.
    settlement_reference = (
        f"SET-{producer.id}-"
        f"{start_date:%Y%m%d}-"
        f"{end_date:%Y%m%d}"
    )

    # Return the information needed by the report template.
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
    """
    Build a commission report for an administrator.

    The report includes paid customer orders and can be filtered by
    producer and order status.
    """

    # Correct the date range if the dates were entered backwards.
    start_date, end_date = normalise_date_range(
        start_date,
        end_date,
    )

    # Start with paid, non-cancelled orders in the selected date range.
    orders = (
        Order.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            payment_status=Order.PaymentStatus.PAID,
        )
        .exclude(
            status=Order.Status.CANCELLED,
        )
        # Load related customer, payment and producer data efficiently.
        .select_related(
            "customer",
            "payment",
        )
        .prefetch_related(
            "producer_orders__producer",
            "producer_orders__items",
        )
    )

    # Apply an optional producer filter.
    if producer_id:
        orders = orders.filter(
            producer_orders__producer_id=producer_id
        )

    # Create a set containing all valid order status values.
    valid_statuses = {
        value
        for value, _label in Order.Status.choices
    }

    # Apply the status filter only when the supplied value is valid.
    if order_status in valid_statuses:
        orders = orders.filter(
            status=order_status
        )

    # Remove duplicates and display the newest orders first.
    order_list = list(
        orders.distinct().order_by("-created_at")
    )

    # Calculate the total amount paid by customers.
    total_order_value = money(
        sum(
            (
                order.total_amount
                for order in order_list
            ),
            Decimal("0.00"),
        )
    )

    # Calculate the total commission received by the network.
    total_commission = money(
        sum(
            (
                order.commission_amount
                for order in order_list
            ),
            Decimal("0.00"),
        )
    )

    # Calculate the total amount allocated to producers.
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

    # The year-to-date figure starts on 1 January.
    calendar_year_start = date(today.year, 1, 1)

    # Calculate all commission earned during the current calendar year.
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

    # Return the information needed by the administrator report page.
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