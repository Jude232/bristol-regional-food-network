from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist

from .models import UserNotification


def cart_summary(request):
    """Provide cart and notification counts to all templates."""

    if not request.user.is_authenticated:
        return {
            "cart_item_count": Decimal("0.00"),
            "unread_notification_count": 0,
        }

    try:
        item_count = request.user.cart.item_count
    except ObjectDoesNotExist:
        item_count = Decimal("0.00")

    unread_notification_count = (
        UserNotification.objects.filter(
            recipient=request.user,
            is_read=False,
        ).count()
    )

    return {
        "cart_item_count": item_count,
        "unread_notification_count": (
            unread_notification_count
        ),
    }
