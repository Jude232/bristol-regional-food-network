from datetime import timedelta

from django.utils import timezone

from .models import AuthenticationEvent


MAX_FAILED_ATTEMPTS = 5
FAILURE_WINDOW_MINUTES = 15


def normalise_email(value: str) -> str:
    """Return a consistent value for security comparisons."""

    return value.strip().lower()


def get_client_ip(request) -> str | None:
    """
    Return the direct client address.

    Forwarded headers are intentionally not trusted because the
    application is not currently behind a configured trusted proxy.
    """

    return request.META.get("REMOTE_ADDR") or None


def get_user_agent(request) -> str:
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
    """Create a security audit event without storing credentials."""

    authenticated_user = None

    if user is not None and getattr(
        user,
        "is_authenticated",
        False,
    ):
        authenticated_user = user

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
    """Count recent failures since the latest successful login."""

    email = normalise_email(email)

    if not email:
        return 0

    window_start = timezone.now() - timedelta(
        minutes=FAILURE_WINDOW_MINUTES
    )

    events = AuthenticationEvent.objects.filter(
        email=email,
        ip_address=ip_address,
        created_at__gte=window_start,
    )

    most_recent_success = (
        events.filter(
            event_type=(
                AuthenticationEvent.EventType.LOGIN_SUCCESS
            )
        )
        .order_by("-created_at")
        .first()
    )

    failures = events.filter(
        event_type=(
            AuthenticationEvent.EventType.LOGIN_FAILURE
        )
    )

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
    return (
        failed_attempt_count(
            email=email,
            ip_address=ip_address,
        )
        >= MAX_FAILED_ATTEMPTS
    )
