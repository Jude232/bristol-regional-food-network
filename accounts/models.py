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