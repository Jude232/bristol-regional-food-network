import uuid
from decimal import Decimal

from django.db import transaction
from django.urls import reverse

from marketplace.models import Product

from .models import (
    Cart,
    CartItem,
    Order,
    OrderItem,
    PaymentTransaction,
    ProducerOrder,
    UserNotification,
    money,
)


class CheckoutError(Exception):
    """Raised when checkout cannot be safely completed."""


class PaymentDeclined(CheckoutError):
    """Raised when the simulated payment is declined."""


@transaction.atomic
def create_order_from_cart(
    *,
    customer,
    delivery_address: str,
    delivery_postcode: str,
    delivery_at,
    special_instructions: str,
    payment_token: str,
    card_last_four: str,
) -> Order:
    """
    Create an order safely from the customer's current cart.

    Product rows are locked during stock validation and reduction so
    simultaneous checkouts cannot purchase the same final stock.
    """

    try:
        cart = Cart.objects.select_for_update().get(
            customer=customer
        )
    except Cart.DoesNotExist as error:
        raise CheckoutError(
            "Your shopping cart does not exist."
        ) from error

    cart_items = list(
        CartItem.objects.select_for_update()
        .select_related(
            "product",
            "product__producer",
            "product__category",
        )
        .filter(cart=cart)
    )

    if not cart_items:
        raise CheckoutError(
            "Your shopping cart is empty."
        )

    product_ids = [
        item.product_id
        for item in cart_items
    ]

    locked_products = {
        product.id: product
        for product in (
            Product.objects.select_for_update()
            .select_related(
                "producer",
                "category",
            )
            .filter(id__in=product_ids)
        )
    }

    grouped_items = {}
    order_subtotal = Decimal("0.00")

    for cart_item in cart_items:
        product = locked_products.get(
            cart_item.product_id
        )

        if product is None:
            raise CheckoutError(
                f"{cart_item.product.name} no longer exists."
            )

        if not product.is_available_now:
            raise CheckoutError(
                f"{product.name} is no longer available."
            )

        if cart_item.quantity > product.stock_quantity:
            raise CheckoutError(
                (
                    f"Only {product.stock_quantity:g} "
                    f"{product.get_unit_display().lower()} "
                    f"of {product.name} remains available."
                )
            )

        line_total = money(
            product.price * cart_item.quantity
        )

        order_subtotal += line_total

        producer_id = product.producer_id

        if producer_id not in grouped_items:
            grouped_items[producer_id] = {
                "producer": product.producer,
                "subtotal": Decimal("0.00"),
                "items": [],
            }

        grouped_items[producer_id]["subtotal"] += (
            line_total
        )

        grouped_items[producer_id]["items"].append(
            {
                "cart_item": cart_item,
                "product": product,
            }
        )

    if payment_token == "tok_declined":
        raise PaymentDeclined(
            "MockPay declined the test payment. "
            "No order was created and no stock was changed."
        )

    if payment_token != "tok_success":
        raise CheckoutError(
            "The selected mock payment token is invalid."
        )

    order = Order(
        customer=customer,
        delivery_address=delivery_address.strip(),
        delivery_postcode=delivery_postcode.strip().upper(),
        special_instructions=special_instructions.strip(),
        status=Order.Status.PENDING,
        payment_status=Order.PaymentStatus.PAID,
    )

    order.set_financial_totals(
        order_subtotal
    )

    order.full_clean()
    order.save()

    for group in grouped_items.values():
        producer_order = ProducerOrder(
            order=order,
            producer=group["producer"],
            delivery_at=delivery_at,
            status=ProducerOrder.Status.PENDING,
        )

        producer_order.set_financial_totals(
            group["subtotal"]
        )

        producer_order.full_clean()
        producer_order.save()

        UserNotification.objects.create(
            recipient=producer_order.producer.user,
            title=f"New order {order.order_number}",
            message=(
                "A new marketplace order requires preparation "
                f"for {delivery_at:%d %B %Y at %H:%M}."
            ),
            link=reverse(
                "orders:producer_order_detail",
                args=[producer_order.id],
            ),
        )

        for grouped_item in group["items"]:
            cart_item = grouped_item["cart_item"]
            product = grouped_item["product"]

            order_item = OrderItem(
                producer_order=producer_order,
                product=product,
                quantity=cart_item.quantity,
            )

            order_item.capture_product_snapshot()
            order_item.full_clean()
            order_item.save()

            product.stock_quantity -= (
                cart_item.quantity
            )

            product.save(
                update_fields=[
                    "stock_quantity",
                    "updated_at",
                ]
            )

    PaymentTransaction.objects.create(
        order=order,
        provider="MockPay",
        transaction_reference=(
            f"MOCK-{uuid.uuid4().hex.upper()}"
        ),
        status=PaymentTransaction.Status.SUCCEEDED,
        amount=order.total_amount,
        card_last_four=card_last_four,
    )

    cart.items.all().delete()

    return order
