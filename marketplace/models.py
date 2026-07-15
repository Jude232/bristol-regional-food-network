from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from accounts.models import ProducerProfile

#This file stores product categories and producer products, including price, stock, allergens, organic status and seasonal availability.
#Model validation and database constraints prevent invalid prices, negative stock and incorrect date ranges.

class Category(models.Model):
    """
    Represents a product category in the marketplace.

    Examples include vegetables, dairy products and bakery items.
    """

    # Each category name must be unique.
    name = models.CharField(
        max_length=100,
        unique=True,
    )

    # The slug is used in readable URLs and filters.
    slug = models.SlugField(
        max_length=100,
        unique=True,
    )

    description = models.TextField(
        blank=True,
    )

    # Inactive categories can be hidden without deleting them.
    is_active = models.BooleanField(
        default=True,
    )

    class Meta:
        # Categories are displayed alphabetically.
        ordering = ["name"]

        # Corrects Django's default plural name.
        verbose_name_plural = "categories"

    def __str__(self) -> str:
        """Display the category name in Django Admin."""
        return self.name


class Product(models.Model):
    """
    Represents a food product listed by a producer.

    Each product is linked to one producer and one category.
    """

    # The unit choices describe how the product is sold.
    class Unit(models.TextChoices):
        ITEM = "item", "Item"
        KILOGRAM = "kg", "Kilogram"
        GRAM = "g", "Gram"
        LITRE = "litre", "Litre"
        MILLILITRE = "ml", "Millilitre"
        DOZEN = "dozen", "Dozen"
        BUNCH = "bunch", "Bunch"
        LOAF = "loaf", "Loaf"
        JAR = "jar", "Jar"
        PACK = "pack", "Pack"

    # These choices describe whether a product can currently be sold.
    class Availability(models.TextChoices):
        IN_SEASON = "in_season", "In Season"
        YEAR_ROUND = "year_round", "Available Year-Round"
        OUT_OF_SEASON = "out_of_season", "Out of Season"
        UNAVAILABLE = "unavailable", "Unavailable"

    # Links the product to the producer who owns it.
    #
    # If the producer profile is deleted, their products are also deleted.
    producer = models.ForeignKey(
        ProducerProfile,
        on_delete=models.CASCADE,
        related_name="products",
    )

    # Links the product to a category.
    #
    # PROTECT prevents a category being deleted while products still use it.
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
    )

    name = models.CharField(
        max_length=200,
    )

    description = models.TextField()

    # DecimalField is used for money to avoid floating-point errors.
    #
    # The validator prevents zero or negative prices.
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.01")),
        ],
        help_text="Price per selected unit.",
    )

    unit = models.CharField(
        max_length=20,
        choices=Unit.choices,
        default=Unit.ITEM,
    )

    # Stores the amount of stock currently available.
    stock_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
        ],
    )

    # A notification can be created when stock falls to this level.
    low_stock_threshold = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("10.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
        ],
    )

    availability_status = models.CharField(
        max_length=20,
        choices=Availability.choices,
        default=Availability.IN_SEASON,
    )

    # Optional dates allow producers to define a selling period.
    available_from = models.DateField(
        blank=True,
        null=True,
    )

    available_until = models.DateField(
        blank=True,
        null=True,
    )

    # Optional food dates provide extra information to customers.
    harvest_date = models.DateField(
        blank=True,
        null=True,
    )

    best_before_date = models.DateField(
        blank=True,
        null=True,
    )

    # All products must include allergen information.
    allergen_information = models.TextField(
        help_text=(
            "List all allergens, or enter "
            "'No common allergens'."
        ),
    )

    organic_certified = models.BooleanField(
        default=False,
    )

    # Stores details such as the certification body or reference.
    organic_certification_details = models.CharField(
        max_length=255,
        blank=True,
    )

    # Products can be disabled without deleting their database record.
    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        # Products are displayed alphabetically.
        ordering = ["name"]

        constraints = [
            # A producer cannot create two products with the same name.
            models.UniqueConstraint(
                fields=["producer", "name"],
                name="unique_product_name_per_producer",
            ),

            # These database constraints provide an extra layer of
            # protection in addition to the form validators.
            models.CheckConstraint(
                condition=models.Q(price__gt=0),
                name="product_price_greater_than_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(stock_quantity__gte=0),
                name="product_stock_not_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(low_stock_threshold__gte=0),
                name="product_threshold_not_negative",
            ),
        ]

    def __str__(self) -> str:
        """
        Display the product name and producer in Django Admin.
        """
        return f"{self.name} — {self.producer.business_name}"

    def clean(self) -> None:
        """
        Perform validation involving more than one field.

        This checks that date ranges are entered in a logical order.
        """

        super().clean()

        errors = {}

        # The end of the selling period cannot be before the start.
        if (
            self.available_from
            and self.available_until
            and self.available_from > self.available_until
        ):
            errors["available_until"] = (
                "The availability end date must be on or after "
                "the start date."
            )

        # A best-before date cannot be earlier than the harvest date.
        if (
            self.harvest_date
            and self.best_before_date
            and self.harvest_date > self.best_before_date
        ):
            errors["best_before_date"] = (
                "The best-before date cannot be before "
                "the harvest date."
            )

        if errors:
            raise ValidationError(errors)

    @property
    def is_available_now(self) -> bool:
        """
        Return True when customers are currently allowed to buy
        the product.
        """

        today = timezone.localdate()

        # Inactive products are hidden from customers.
        if not self.is_active:
            return False

        # Products with no stock cannot be purchased.
        if self.stock_quantity <= 0:
            return False

        # Products marked as unavailable or out of season are blocked.
        if self.availability_status in {
            self.Availability.OUT_OF_SEASON,
            self.Availability.UNAVAILABLE,
        }:
            return False

        # Products cannot be sold before their start date.
        if (
            self.available_from
            and today < self.available_from
        ):
            return False

        # Products cannot be sold after their end date.
        if (
            self.available_until
            and today > self.available_until
        ):
            return False

        return True

    @property
    def is_low_stock(self) -> bool:
        """
        Return True when the current stock is at or below the
        producer's chosen warning level.
        """

        return (
            self.stock_quantity > 0
            and self.stock_quantity <= self.low_stock_threshold
        )

    @property
    def farm_origin(self) -> str:
        """
        Return a readable producer name and postcode for customers.
        """

        return (
            f"{self.producer.business_name}, "
            f"{self.producer.postcode}"
        )