from datetime import timedelta

from django.utils import timezone

from .models import AuthenticationEvent

#This file records authentication activity and temporarily blocks repeated failed login attempts.
#

# A user is temporarily blocked after five failed login attempts.
MAX_FAILED_ATTEMPTS = 5

# Only failed attempts from the last 15 minutes are counted.
FAILURE_WINDOW_MINUTES = 15


def normalise_email(value: str) -> str:
    """
    Convert an email address into a consistent format.

    Removing spaces and using lowercase prevents the same email
    being treated differently during security checks.
    """

    return value.strip().lower()


def get_client_ip(request) -> str | None:
    """
    Return the IP address of the device making the request.

    REMOTE_ADDR is used because the project is not currently running
    behind a configured trusted proxy.
    """

    return request.META.get("REMOTE_ADDR") or None


def get_user_agent(request) -> str:
    """
    Return basic information about the user's browser or device.

    The value is limited to 500 characters to match the database field.
    """

    return request.META.get(
        "HTTP_USER_AGENT",
        "",
    )[:500]


def record_authentication_event(
    *,
    request,
    event_type: str,
    email: str = "",
    user=None,
) -> AuthenticationEvent:
    """
    Create a security audit record for a login-related event.

    This records information such as the event type, email address,
    IP address and browser. Passwords are never stored.
    """

    authenticated_user = None

    # Only link the event to a user when a valid authenticated user
    # object has been supplied.
    if user is not None and getattr(
        user,
        "is_authenticated",
        False,
    ):
        authenticated_user = user

    # Save the authentication event in the database.
    return AuthenticationEvent.objects.create(
        event_type=event_type,
        user=authenticated_user,
        email=normalise_email(email),
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )


def failed_attempt_count(
    *,
    email: str,
    ip_address: str | None,
) -> int:
    """
    Count recent failed login attempts for one email and IP address.

    Failures before the most recent successful login are ignored.
    """

    email = normalise_email(email)

    # An empty email address cannot be checked.
    if not email:
        return 0

    # Calculate the earliest time that should be included.
    window_start = timezone.now() - timedelta(
        minutes=FAILURE_WINDOW_MINUTES
    )

    # Find recent authentication events for the same email and IP.
    events = AuthenticationEvent.objects.filter(
        email=email,
        ip_address=ip_address,
        created_at__gte=window_start,
    )

    # Find the most recent successful login during the time window.
    most_recent_success = (
        events.filter(
            event_type=(
                AuthenticationEvent.EventType.LOGIN_SUCCESS
            )
        )
        .order_by("-created_at")
        .first()
    )

    # Start with all failed login attempts in the time window.
    failures = events.filter(
        event_type=(
            AuthenticationEvent.EventType.LOGIN_FAILURE
        )
    )

    # When a successful login exists, only count failures that happened
    # after that successful login.
    if most_recent_success is not None:
        failures = failures.filter(
            created_at__gt=most_recent_success.created_at
        )

    return failures.count()


def is_login_blocked(
    *,
    email: str,
    ip_address: str | None,
) -> bool:
    """
    Return True when the number of failed attempts has reached
    the allowed limit.
    """

    return (
        failed_attempt_count(
            email=email,
            ip_address=ip_address,
        )
        >= MAX_FAILED_ATTEMPTS
    )