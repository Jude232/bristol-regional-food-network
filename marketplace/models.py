from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from accounts.models import ProducerProfile


class Category(models.Model):
    """A marketplace product category."""

    name = models.CharField(
        max_length=100,
        unique=True,
    )

    slug = models.SlugField(
        max_length=100,
        unique=True,
    )

    description = models.TextField(
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    """A food product listed by a marketplace producer."""

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

    class Availability(models.TextChoices):
        IN_SEASON = "in_season", "In Season"
        YEAR_ROUND = "year_round", "Available Year-Round"
        OUT_OF_SEASON = "out_of_season", "Out of Season"
        UNAVAILABLE = "unavailable", "Unavailable"

    producer = models.ForeignKey(
        ProducerProfile,
        on_delete=models.CASCADE,
        related_name="products",
    )

    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
    )

    name = models.CharField(
        max_length=200,
    )

    description = models.TextField()

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

    stock_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
        ],
    )

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

    available_from = models.DateField(
        blank=True,
        null=True,
    )

    available_until = models.DateField(
        blank=True,
        null=True,
    )

    harvest_date = models.DateField(
        blank=True,
        null=True,
    )

    best_before_date = models.DateField(
        blank=True,
        null=True,
    )

    allergen_information = models.TextField(
        help_text=(
            "List all allergens, or enter "
            "'No common allergens'."
        ),
    )

    organic_certified = models.BooleanField(
        default=False,
    )

    organic_certification_details = models.CharField(
        max_length=255,
        blank=True,
    )

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
        ordering = ["name"]

        constraints = [
            models.UniqueConstraint(
                fields=["producer", "name"],
                name="unique_product_name_per_producer",
            ),
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
        return f"{self.name} — {self.producer.business_name}"

    def clean(self) -> None:
        """Validate seasonal and food-date information."""

        super().clean()

        errors = {}

        if (
            self.available_from
            and self.available_until
            and self.available_from > self.available_until
        ):
            errors["available_until"] = (
                "The availability end date must be on or after "
                "the start date."
            )

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
        """Return whether customers may currently purchase the product."""

        today = timezone.localdate()

        if not self.is_active:
            return False

        if self.stock_quantity <= 0:
            return False

        if self.availability_status in {
            self.Availability.OUT_OF_SEASON,
            self.Availability.UNAVAILABLE,
        }:
            return False

        if (
            self.available_from
            and today < self.available_from
        ):
            return False

        if (
            self.available_until
            and today > self.available_until
        ):
            return False

        return True

    @property
    def is_low_stock(self) -> bool:
        """Return whether stock is at or below the producer's threshold."""

        return (
            self.stock_quantity > 0
            and self.stock_quantity <= self.low_stock_threshold
        )

    @property
    def farm_origin(self) -> str:
        """Return a readable farm origin for customer displays."""

        return (
            f"{self.producer.business_name}, "
            f"{self.producer.postcode}"
        )
