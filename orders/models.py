from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from marketplace.models import Product


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
        """Return the current monetary total of all cart items."""

        return sum(
            (
                item.line_total
                for item in self.items.select_related("product")
            ),
            Decimal("0.00"),
        )

    @property
    def item_count(self) -> Decimal:
        """Return the total quantity of products in the cart."""

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
        """Ensure the requested quantity can currently be purchased."""

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
        """Return price multiplied by quantity to two decimal places."""

        return (
            self.product.price * self.quantity
        ).quantize(Decimal("0.01"))
