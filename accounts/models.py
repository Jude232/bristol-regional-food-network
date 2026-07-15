from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import UserManager

#This file stores the custom email-based user model, account roles, user profiles and authentication audit events.
#Authentication identifies the user, while their role controls what they are authorised to access.

class User(AbstractUser):
    """
    Custom user model for the marketplace.

    Django's standard username field is removed so that users log in
    with their email address instead.
    """

    # The available account roles in the marketplace.
    class Role(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        PRODUCER = "producer", "Producer"
        COMMUNITY_GROUP = "community_group", "Community Group"
        RESTAURANT = "restaurant", "Restaurant"
        ADMIN = "admin", "Administrator"

    # The standard Django username is not needed because email is used.
    username = None

    # Each account must have a unique email address.
    email = models.EmailField(
        unique=True,
        help_text="The email address used to log in.",
    )

    # The role controls which areas of the website the user can access.
    role = models.CharField(
        max_length=30,
        choices=Role.choices,
        default=Role.CUSTOMER,
    )

    # The custom manager creates users using an email instead of a username.
    objects = UserManager()

    # Tells Django that email is the main login field.
    USERNAME_FIELD = "email"

    # No extra fields are required when creating a superuser.
    REQUIRED_FIELDS: list[str] = []

    def __str__(self) -> str:
        """Display the user's email in Django Admin."""
        return self.email


class ProducerProfile(models.Model):
    """
    Stores additional business information for producer accounts.

    Login details remain in the User model, while business details
    are stored separately in this profile.
    """

    # Each producer user can have one producer profile.
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

    # An administrator can use this field to approve a producer.
    is_verified = models.BooleanField(
        default=False,
        help_text="Whether the producer has been verified by an administrator.",
    )

    # Automatically records when the profile was first created.
    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    # Automatically updates whenever the profile is changed.
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        # Producer profiles are shown alphabetically by business name.
        ordering = ["business_name"]

    def __str__(self) -> str:
        """Display the business name in Django Admin."""
        return self.business_name


class CustomerProfile(models.Model):
    """
    Stores contact and delivery information for customer-type users.

    This profile can also be used by restaurant and community-group
    accounts because they require delivery details.
    """

    # Each customer user can have one customer profile.
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

    # Records whether the user accepted the marketplace terms.
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
        """
        Display the customer's full name when available.

        The email address is used as a fallback when no name has
        been entered.
        """
        full_name = self.user.get_full_name().strip()

        if full_name:
            return full_name

        return self.user.email


from django.conf import settings as authentication_settings
from django.db import models as authentication_models


class AuthenticationEvent(authentication_models.Model):
    """
    Stores a security audit record for login and logout activity.

    These records allow an administrator to review successful,
    failed and blocked login attempts.
    """

    # The types of authentication activity that can be recorded.
    class EventType(authentication_models.TextChoices):
        LOGIN_SUCCESS = "login_success", "Login Success"
        LOGIN_FAILURE = "login_failure", "Login Failure"
        LOGIN_BLOCKED = "login_blocked", "Login Blocked"
        LOGOUT = "logout", "Logout"

    event_type = authentication_models.CharField(
        max_length=30,
        choices=EventType.choices,
    )

    # Links the event to a user when the account can be identified.
    #
    # SET_NULL keeps the audit record if the user account is deleted.
    user = authentication_models.ForeignKey(
        authentication_settings.AUTH_USER_MODEL,
        on_delete=authentication_models.SET_NULL,
        related_name="authentication_events",
        blank=True,
        null=True,
    )

    # The email is stored separately so failed attempts for unknown
    # accounts can still be recorded.
    email = authentication_models.EmailField(
        blank=True,
    )

    # Stores the address that made the request.
    ip_address = authentication_models.GenericIPAddressField(
        blank=True,
        null=True,
    )

    # Stores basic information about the browser or device.
    user_agent = authentication_models.CharField(
        max_length=500,
        blank=True,
    )

    created_at = authentication_models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        # The newest authentication events appear first.
        ordering = ["-created_at"]

        # This index improves searches used by the login-throttling system.
        indexes = [
            authentication_models.Index(
                fields=[
                    "email",
                    "ip_address",
                    "event_type",
                    "created_at",
                ],
                name="auth_event_lookup_idx",
            ),
        ]

    def __str__(self) -> str:
        """Create a readable description for Django Admin."""
        identity = self.email or "unknown user"

        return (
            f"{self.get_event_type_display()} — "
            f"{identity} — {self.created_at}"
        )