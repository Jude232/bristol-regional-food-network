import uuid
from decimal import Decimal

from django.db import transaction
from django.urls import reverse

from marketplace.models import Product

from .notification_services import sync_low_stock_notification

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

#This service performs the full checkout process across several related models.
#It uses an atomic transaction and row locking, so a failure rolls everything back and two customers cannot purchase the same final stock.

class CheckoutError(Exception):
    """
    Custom error used when checkout cannot be completed safely.

    This allows the checkout view to show a suitable message to the
    customer without exposing technical database errors.
    """


class PaymentDeclined(CheckoutError):
    """
    Specific checkout error used when the mock payment is declined.
    """


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
    Create an order from the customer's current shopping cart.

    The transaction.atomic decorator means that all checkout database
    changes are treated as one transaction. If any stage fails, the
    complete transaction is rolled back so that partial orders and
    incorrect stock changes are not saved.

    Product and cart records are locked during checkout to reduce the
    chance of two customers buying the same final stock.
    """

    # Lock the customer's cart while checkout is taking place.
    #
    # This prevents another checkout process from changing the same
    # cart at the same time.
    try:
        cart = Cart.objects.select_for_update().get(
            customer=customer
        )
    except Cart.DoesNotExist as error:
        raise CheckoutError(
            "Your shopping cart does not exist."
        ) from error

    # Retrieve and lock all items in the customer's cart.
    #
    # select_related loads the connected product, producer and category
    # in the same database query where possible.
    cart_items = list(
        CartItem.objects.select_for_update()
        .select_related(
            "product",
            "product__producer",
            "product__category",
        )
        .filter(cart=cart)
    )

    # Checkout cannot continue when the cart contains no items.
    if not cart_items:
        raise CheckoutError(
            "Your shopping cart is empty."
        )

    # Create a list containing the IDs of all products in the cart.
    product_ids = [
        item.product_id
        for item in cart_items
    ]

    # Retrieve the latest product records directly from the database
    # and lock them until checkout finishes.
    #
    # This makes sure stock is checked using the most recent values.
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

    # Products will be grouped by producer so that one main customer
    # order can be divided into separate producer orders.
    grouped_items = {}

    # The order subtotal starts at zero and increases for each item.
    order_subtotal = Decimal("0.00")

    # Validate every item and group it by its producer.
    for cart_item in cart_items:
        product = locked_products.get(
            cart_item.product_id
        )

        # Stop checkout if the product was removed after being added
        # to the cart.
        if product is None:
            raise CheckoutError(
                f"{cart_item.product.name} no longer exists."
            )

        # Check that the product is active, in stock and currently
        # within its availability dates.
        if not product.is_available_now:
            raise CheckoutError(
                f"{product.name} is no longer available."
            )

        # Stop checkout if the customer requests more stock than is
        # currently available.
        if cart_item.quantity > product.stock_quantity:
            raise CheckoutError(
                (
                    f"Only {product.stock_quantity:g} "
                    f"{product.get_unit_display().lower()} "
                    f"of {product.name} remains available."
                )
            )

        # Calculate the total price for this cart item.
        line_total = money(
            product.price * cart_item.quantity
        )

        # Add the item's value to the complete order subtotal.
        order_subtotal += line_total

        producer_id = product.producer_id

        # Create a group the first time a producer appears in the cart.
        if producer_id not in grouped_items:
            grouped_items[producer_id] = {
                "producer": product.producer,
                "subtotal": Decimal("0.00"),
                "items": [],
            }

        # Add the item value to this producer's subtotal.
        grouped_items[producer_id]["subtotal"] += (
            line_total
        )

        # Store the cart item and locked product in the producer group.
        grouped_items[producer_id]["items"].append(
            {
                "cart_item": cart_item,
                "product": product,
            }
        )

    # The mock payment system uses test tokens to simulate payment
    # success and failure without processing real card payments.
    if payment_token == "tok_declined":
        raise PaymentDeclined(
            "MockPay declined the test payment. "
            "No order was created and no stock was changed."
        )

    # Only the known success token is accepted.
    if payment_token != "tok_success":
        raise CheckoutError(
            "The selected mock payment token is invalid."
        )

    # Create the main customer order.
    #
    # The address and postcode are copied onto the order so the
    # historical delivery information remains unchanged if the
    # customer edits their account later.
    order = Order(
        customer=customer,
        delivery_address=delivery_address.strip(),
        delivery_postcode=delivery_postcode.strip().upper(),
        special_instructions=special_instructions.strip(),
        status=Order.Status.PENDING,
        payment_status=Order.PaymentStatus.PAID,
    )

    # Calculate the customer total, platform commission and combined
    # producer payment allocation.
    order.set_financial_totals(
        order_subtotal
    )

    # Run model validation before saving the order.
    order.full_clean()
    order.save()

    # Create one ProducerOrder for each producer represented in the cart.
    for group in grouped_items.values():
        producer_order = ProducerOrder(
            order=order,
            producer=group["producer"],
            delivery_at=delivery_at,
            status=ProducerOrder.Status.PENDING,
        )

        # Calculate this producer's subtotal, 5% commission and
        # 95% producer payment.
        producer_order.set_financial_totals(
            group["subtotal"]
        )

        producer_order.full_clean()
        producer_order.save()

        # Notify the producer that a new order requires preparation.
        UserNotification.objects.create(
            recipient=producer_order.producer.user,
            notification_type=(
                UserNotification.NotificationType.NEW_ORDER
            ),
            title=f"New order {order.order_number}",
            message=(
                "A new marketplace order requires preparation "
                f"for {delivery_at:%d %B %Y at %H:%M}."
            ),

            # Store a link that opens the producer's order details page.
            link=reverse(
                "orders:producer_order_detail",
                args=[producer_order.id],
            ),
        )

        # Process each product belonging to this producer.
        for grouped_item in group["items"]:
            cart_item = grouped_item["cart_item"]
            product = grouped_item["product"]

            # Create a permanent order-item record.
            order_item = OrderItem(
                producer_order=producer_order,
                product=product,
                quantity=cart_item.quantity,
            )

            # Copy the product name, price, unit and allergen information
            # into the order item.
            #
            # This keeps old orders accurate if the producer changes the
            # original product later.
            order_item.capture_product_snapshot()

            order_item.full_clean()
            order_item.save()

            # Reduce the product's stock by the purchased quantity.
            product.stock_quantity -= (
                cart_item.quantity
            )

            # Update only the fields that have changed.
            product.save(
                update_fields=[
                    "stock_quantity",
                    "updated_at",
                ]
            )

            # Create, update or resolve a low-stock notification
            # depending on the product's new stock quantity.
            sync_low_stock_notification(
                product
            )

    # Store a safe record of the successful simulated payment.
    #
    # A unique mock reference and the last four test digits are stored.
    # Full card details are not saved.
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

    # Remove all items after checkout has completed successfully.
    cart.items.all().delete()

    # Return the newly created order to the calling view.
    return order