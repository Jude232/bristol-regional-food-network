from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import UserManager


class User(AbstractUser):
    """Marketplace user authenticated using an email address."""

    class Role(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        PRODUCER = "producer", "Producer"
        COMMUNITY_GROUP = "community_group", "Community Group"
        RESTAURANT = "restaurant", "Restaurant"
        ADMIN = "admin", "Administrator"

    username = None

    email = models.EmailField(
        unique=True,
        help_text="The email address used to log in.",
    )

    role = models.CharField(
        max_length=30,
        choices=Role.choices,
        default=Role.CUSTOMER,
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    def __str__(self) -> str:
        return self.email


class ProducerProfile(models.Model):
    """Business information belonging to a producer account."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="producer_profile",
    )

    business_name = models.CharField(
        max_length=200,
        unique=True,
    )

    phone = models.CharField(
        max_length=30,
    )

    business_address = models.TextField()

    postcode = models.CharField(
        max_length=10,
    )

    is_verified = models.BooleanField(
        default=False,
        help_text="Whether the producer has been verified by an administrator.",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["business_name"]

    def __str__(self) -> str:
        return self.business_name


class CustomerProfile(models.Model):
    """Contact and delivery information belonging to a customer."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="customer_profile",
    )

    phone = models.CharField(
        max_length=30,
    )

    delivery_address = models.TextField()

    postcode = models.CharField(
        max_length=10,
    )

    accepted_terms = models.BooleanField(
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self) -> str:
        full_name = self.user.get_full_name().strip()

        if full_name:
            return full_name

        return self.user.email