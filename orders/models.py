import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from accounts.models import ProducerProfile
from marketplace.models import Product

#This file stores carts, customer orders, producer-specific orders, purchased-item snapshots, payments, status history and notifications.
#Order items store a snapshot of the purchased product so historical orders remain accurate after product changes.

# The marketplace keeps 5% of each completed sale.
COMMISSION_RATE = Decimal("0.05")

# Financial values are rounded to two decimal places.
MONEY_PLACES = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    """
    Round a financial value to two decimal places.

    ROUND_HALF_UP gives predictable currency rounding rather than
    relying on normal floating-point calculations.
    """

    return Decimal(value).quantize(
        MONEY_PLACES,
        rounding=ROUND_HALF_UP,
    )


def generate_order_number() -> str:
    """
    Generate a short, readable and unique order number.

    UUID is used to reduce the chance of two orders receiving the
    same reference.
    """

    reference = uuid.uuid4().hex[:10].upper()

    return f"BRFN-{reference}"


class Cart(models.Model):
    """
    Represents a persistent shopping cart belonging to one customer.

    The cart is stored in the database, so it remains available when
    the customer changes pages or signs in again.
    """

    # Each user can have one cart.
    customer = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cart",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        # Recently updated carts appear first in Django Admin.
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        """Display the cart owner's email in Django Admin."""
        return f"Cart for {self.customer.email}"

    @property
    def total(self) -> Decimal:
        """
        Calculate the total cost of every item in the cart.
        """

        return sum(
            (
                item.line_total
                for item in self.items.select_related("product")
            ),
            Decimal("0.00"),
        )

    @property
    def item_count(self) -> Decimal:
        """
        Calculate the total quantity of products in the cart.
        """

        return sum(
            (
                item.quantity
                for item in self.items.all()
            ),
            Decimal("0.00"),
        )


class CartItem(models.Model):
    """
    Represents one product and quantity inside a customer's cart.
    """

    # A cart can contain several cart items.
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items",
    )

    # Links the cart item to a marketplace product.
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="cart_items",
    )

    # Quantity must be greater than zero.
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("1.00"),
        validators=[
            MinValueValidator(Decimal("0.01")),
        ],
    )

    added_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["added_at"]

        constraints = [
            # The same product can appear only once in a cart.
            # Its quantity should be updated instead of creating
            # a duplicate row.
            models.UniqueConstraint(
                fields=["cart", "product"],
                name="unique_product_per_cart",
            ),

            # Provides database-level protection against invalid
            # quantities.
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="cart_item_quantity_greater_than_zero",
            ),
        ]

    def __str__(self) -> str:
        """Display the quantity, product and customer."""
        return (
            f"{self.quantity} × {self.product.name} "
            f"for {self.cart.customer.email}"
        )

    def clean(self) -> None:
        """
        Check that the chosen product can be purchased.

        This prevents unavailable products or quantities greater
        than the available stock from being added to the cart.
        """

        super().clean()

        if not self.product.is_available_now:
            raise ValidationError(
                {
                    "product": (
                        "This product is not currently available."
                    )
                }
            )

        if self.quantity > self.product.stock_quantity:
            raise ValidationError(
                {
                    "quantity": (
                        "The requested quantity exceeds "
                        "the available stock."
                    )
                }
            )

    @property
    def line_total(self) -> Decimal:
        """
        Calculate the product price multiplied by its quantity.
        """

        return money(
            self.product.price * self.quantity
        )


class Order(models.Model):
    """
    Represents the customer's complete transaction.

    One order may contain products from several producers. It is
    therefore divided into separate ProducerOrder records.
    """

    # The overall customer order status.
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    # The payment result is stored separately from the order status.
    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        DECLINED = "declined", "Declined"
        REFUNDED = "refunded", "Refunded"

    # PROTECT prevents an account being deleted when it has
    # historical orders.
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orders",
    )

    # The order number is generated automatically and cannot be edited.
    order_number = models.CharField(
        max_length=20,
        unique=True,
        default=generate_order_number,
        editable=False,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )

    # Delivery details are copied onto the order so they remain
    # unchanged if the customer later edits their profile.
    delivery_address = models.TextField()

    delivery_postcode = models.CharField(
        max_length=10,
    )

    special_instructions = models.TextField(
        blank=True,
    )

    # Stores the value of all purchased items before commission.
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    # Stores the Bristol Regional Food Network's 5% commission.
    commission_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    # Stores the total amount allocated to all producers.
    producer_payment_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    # The customer pays the normal subtotal. Commission is deducted
    # from the producer allocation rather than added to the price.
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        # Newest customer orders appear first.
        ordering = ["-created_at"]

        constraints = [
            # Financial values should never be negative.
            models.CheckConstraint(
                condition=models.Q(subtotal__gte=0),
                name="order_subtotal_not_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(commission_amount__gte=0),
                name="order_commission_not_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(producer_payment_total__gte=0),
                name="order_producer_total_not_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(total_amount__gte=0),
                name="order_total_not_negative",
            ),
        ]

    def __str__(self) -> str:
        """Display the generated order number."""
        return self.order_number

    def set_financial_totals(
        self,
        subtotal: Decimal,
    ) -> None:
        """
        Calculate and store the overall order totals.

        The platform keeps 5% and the producers receive the
        remaining 95%.
        """

        self.subtotal = money(subtotal)

        self.commission_amount = money(
            self.subtotal * COMMISSION_RATE
        )

        self.producer_payment_total = money(
            self.subtotal - self.commission_amount
        )

        # Commission is deducted from producer payments rather than
        # added to the customer's purchase price.
        self.total_amount = self.subtotal


class ProducerOrder(models.Model):
    """
    Represents one producer's part of a customer order.

    For example, an order containing products from two farms creates
    one main Order and two ProducerOrder records.
    """

    # Producers update their order section through these stages.
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        READY = "ready", "Ready for Collection/Delivery"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    # Several producer orders can belong to one customer order.
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="producer_orders",
    )

    # PROTECT keeps historical order information if a producer
    # profile is no longer active.
    producer = models.ForeignKey(
        ProducerProfile,
        on_delete=models.PROTECT,
        related_name="incoming_orders",
    )

    delivery_at = models.DateTimeField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    producer_note = models.TextField(
        blank=True,
    )

    # Financial totals for this producer's items only.
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    commission_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    producer_payment = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        # Orders are displayed by delivery date and order number.
        ordering = [
            "delivery_at",
            "order__order_number",
        ]

        constraints = [
            # A producer should have only one section within each
            # customer order.
            models.UniqueConstraint(
                fields=["order", "producer"],
                name="one_producer_section_per_order",
            ),

            # Financial totals cannot be negative.
            models.CheckConstraint(
                condition=models.Q(subtotal__gte=0),
                name="producer_order_subtotal_not_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(commission_amount__gte=0),
                name="producer_order_commission_not_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(producer_payment__gte=0),
                name="producer_payment_not_negative",
            ),
        ]

    def __str__(self) -> str:
        """Display the main order number and producer name."""
        return (
            f"{self.order.order_number} — "
            f"{self.producer.business_name}"
        )

    def clean(self) -> None:
        """
        Enforce the minimum 48-hour delivery rule.

        The validation is applied when a producer-order record is
        first created.
        """

        super().clean()

        # During checkout, created_at may not yet be available, so
        # the current time is used as a fallback.
        reference_time = getattr(
            self.order,
            "created_at",
            None,
        ) or timezone.now()

        minimum_delivery_at = (
            reference_time + timedelta(hours=48)
        )

        if (
            self._state.adding
            and self.delivery_at
            and self.delivery_at < minimum_delivery_at
        ):
            raise ValidationError(
                {
                    "delivery_at": (
                        "Delivery must be scheduled at least "
                        "48 hours after checkout."
                    )
                }
            )

    def set_financial_totals(
        self,
        subtotal: Decimal,
    ) -> None:
        """
        Calculate the financial totals for one producer.

        The producer receives 95% of their section subtotal.
        """

        self.subtotal = money(subtotal)

        self.commission_amount = money(
            self.subtotal * COMMISSION_RATE
        )

        self.producer_payment = money(
            self.subtotal - self.commission_amount
        )


class OrderItem(models.Model):
    """
    Stores a permanent snapshot of a purchased product.

    Product names, prices and allergen information are copied when
    the order is created so historical orders do not change when the
    producer later edits the original product.
    """

    # Each purchased item belongs to a producer-specific order.
    producer_order = models.ForeignKey(
        ProducerOrder,
        on_delete=models.CASCADE,
        related_name="items",
    )

    # PROTECT prevents a purchased product from being deleted from
    # the database.
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="order_items",
    )

    # These fields store the product details at the time of purchase.
    product_name = models.CharField(
        max_length=200,
    )

    unit_name = models.CharField(
        max_length=50,
    )

    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.01")),
        ],
    )

    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.01")),
        ],
    )

    line_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    allergen_information = models.TextField()

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["product_name"]

        constraints = [
            # Purchased quantities and prices must always be positive.
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="order_item_quantity_greater_than_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price__gt=0),
                name="order_item_price_greater_than_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(line_total__gt=0),
                name="order_item_total_greater_than_zero",
            ),
        ]

    def __str__(self) -> str:
        """Display the quantity, product and order number."""
        return (
            f"{self.quantity} × {self.product_name} "
            f"({self.producer_order.order.order_number})"
        )

    def capture_product_snapshot(self) -> None:
        """
        Copy the product details that must remain unchanged.

        This is called during checkout before the order item is saved.
        """

        self.product_name = self.product.name
        self.unit_name = self.product.get_unit_display()
        self.unit_price = money(self.product.price)

        self.line_total = money(
            self.unit_price * self.quantity
        )

        self.allergen_information = (
            self.product.allergen_information
        )


class PaymentTransaction(models.Model):
    """
    Stores the result of the simulated MockPay transaction.

    Full card details are not stored. Only the final four test digits
    are kept for demonstration purposes.
    """

    class Status(models.TextChoices):
        SUCCEEDED = "succeeded", "Succeeded"
        DECLINED = "declined", "Declined"
        REFUNDED = "refunded", "Refunded"

    # Each order has one payment transaction.
    order = models.OneToOneField(
        Order,
        on_delete=models.PROTECT,
        related_name="payment",
    )

    provider = models.CharField(
        max_length=50,
        default="MockPay",
    )

    transaction_reference = models.CharField(
        max_length=100,
        unique=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.01")),
        ],
    )

    # Only the last four digits are stored, not a complete card number.
    card_last_four = models.CharField(
        max_length=4,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    def __str__(self) -> str:
        """Display the mock payment reference."""
        return self.transaction_reference


class ProducerOrderStatusHistory(models.Model):
    """
    Records every change made to a producer-order status.

    This creates an audit history showing what changed, who changed
    it and when the change was made.
    """

    producer_order = models.ForeignKey(
        ProducerOrder,
        on_delete=models.CASCADE,
        related_name="status_history",
    )

    previous_status = models.CharField(
        max_length=20,
        choices=ProducerOrder.Status.choices,
    )

    new_status = models.CharField(
        max_length=20,
        choices=ProducerOrder.Status.choices,
    )

    # Producers can optionally explain the reason for a status change.
    note = models.TextField(
        blank=True,
    )

    # PROTECT preserves the user responsible for the audit record.
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="producer_order_status_changes",
    )

    changed_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        # Status changes are displayed in chronological order.
        ordering = ["changed_at"]

        verbose_name_plural = "producer order status histories"

    def __str__(self) -> str:
        """Display the order and status change."""
        return (
            f"{self.producer_order} — "
            f"{self.previous_status} to {self.new_status}"
        )


class UserNotification(models.Model):
    """
    Represents a notification shown inside a user's account.

    Notifications are used for new orders, status updates and
    low-stock warnings.
    """

    class NotificationType(models.TextChoices):
        GENERAL = "general", "General"
        NEW_ORDER = "new_order", "New Order"
        ORDER_STATUS = "order_status", "Order Status"
        LOW_STOCK = "low_stock", "Low Stock"

    # The user who should receive the notification.
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )

    notification_type = models.CharField(
        max_length=30,
        choices=NotificationType.choices,
        default=NotificationType.GENERAL,
    )

    # Product is optional because not every notification relates to
    # a product.
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="notifications",
        blank=True,
        null=True,
    )

    title = models.CharField(
        max_length=200,
    )

    message = models.TextField()

    # An optional internal website link can take the user to the
    # related product or order.
    link = models.CharField(
        max_length=255,
        blank=True,
    )

    # Tracks whether the user has opened the notification.
    is_read = models.BooleanField(
        default=False,
    )

    # Used mainly for alerts such as low stock. The alert can be
    # marked as resolved after the product is restocked.
    is_resolved = models.BooleanField(
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        # The newest notifications appear first.
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """Display the title and recipient in Django Admin."""
        return f"{self.title} — {self.recipient.email}"