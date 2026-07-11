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


COMMISSION_RATE = Decimal("0.05")
MONEY_PLACES = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    """Round financial values consistently to two decimal places."""

    return Decimal(value).quantize(
        MONEY_PLACES,
        rounding=ROUND_HALF_UP,
    )


def generate_order_number() -> str:
    """Generate a readable unique customer order number."""

    reference = uuid.uuid4().hex[:10].upper()

    return f"BRFN-{reference}"


class Cart(models.Model):
    """Persistent shopping cart belonging to one customer."""

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
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"Cart for {self.customer.email}"

    @property
    def total(self) -> Decimal:
        return sum(
            (
                item.line_total
                for item in self.items.select_related("product")
            ),
            Decimal("0.00"),
        )

    @property
    def item_count(self) -> Decimal:
        return sum(
            (
                item.quantity
                for item in self.items.all()
            ),
            Decimal("0.00"),
        )


class CartItem(models.Model):
    """A product and quantity stored in a customer's cart."""

    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items",
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="cart_items",
    )

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
            models.UniqueConstraint(
                fields=["cart", "product"],
                name="unique_product_per_cart",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="cart_item_quantity_greater_than_zero",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.quantity} × {self.product.name} "
            f"for {self.cart.customer.email}"
        )

    def clean(self) -> None:
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
        return money(
            self.product.price * self.quantity
        )


class Order(models.Model):
    """One customer transaction containing one or more producers."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        DECLINED = "declined", "Declined"
        REFUNDED = "refunded", "Refunded"

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orders",
    )

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

    delivery_address = models.TextField()

    delivery_postcode = models.CharField(
        max_length=10,
    )

    special_instructions = models.TextField(
        blank=True,
    )

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

    producer_payment_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

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
        ordering = ["-created_at"]

        constraints = [
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
        return self.order_number

    def set_financial_totals(
        self,
        subtotal: Decimal,
    ) -> None:
        """Store the customer total and network commission snapshot."""

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
    """The portion of a customer order belonging to one producer."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        READY = "ready", "Ready for Collection/Delivery"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="producer_orders",
    )

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
        ordering = [
            "delivery_at",
            "order__order_number",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["order", "producer"],
                name="one_producer_section_per_order",
            ),
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
        return (
            f"{self.order.order_number} — "
            f"{self.producer.business_name}"
        )

    def clean(self) -> None:
        super().clean()

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
        """Calculate the producer's 95% payment allocation."""

        self.subtotal = money(subtotal)

        self.commission_amount = money(
            self.subtotal * COMMISSION_RATE
        )

        self.producer_payment = money(
            self.subtotal - self.commission_amount
        )


class OrderItem(models.Model):
    """A permanent snapshot of one purchased product."""

    producer_order = models.ForeignKey(
        ProducerOrder,
        on_delete=models.CASCADE,
        related_name="items",
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="order_items",
    )

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
        return (
            f"{self.quantity} × {self.product_name} "
            f"({self.producer_order.order.order_number})"
        )

    def capture_product_snapshot(self) -> None:
        """Copy values that must remain unchanged after purchase."""

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
    """Safe record of a simulated test payment."""

    class Status(models.TextChoices):
        SUCCEEDED = "succeeded", "Succeeded"
        DECLINED = "declined", "Declined"
        REFUNDED = "refunded", "Refunded"

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

    card_last_four = models.CharField(
        max_length=4,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    def __str__(self) -> str:
        return self.transaction_reference


class ProducerOrderStatusHistory(models.Model):
    """Permanent audit record of a producer-order status change."""

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

    note = models.TextField(
        blank=True,
    )

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="producer_order_status_changes",
    )

    changed_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["changed_at"]
        verbose_name_plural = "producer order status histories"

    def __str__(self) -> str:
        return (
            f"{self.producer_order} — "
            f"{self.previous_status} to {self.new_status}"
        )


class UserNotification(models.Model):
    """A notification displayed inside a user's account."""

    class NotificationType(models.TextChoices):
        GENERAL = "general", "General"
        NEW_ORDER = "new_order", "New Order"
        ORDER_STATUS = "order_status", "Order Status"
        LOW_STOCK = "low_stock", "Low Stock"

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

    link = models.CharField(
        max_length=255,
        blank=True,
    )

    is_read = models.BooleanField(
        default=False,
    )

    is_resolved = models.BooleanField(
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} — {self.recipient.email}"

