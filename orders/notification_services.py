from django.db import transaction
from django.urls import reverse

from marketplace.models import Product

from .models import UserNotification


@transaction.atomic
def sync_low_stock_notification(
    product: Product,
) -> UserNotification | None:
    """
    Create, update or resolve the low-stock notification for a product.

    Only one unresolved low-stock notification may exist for each
    product at a time.
    """

    active_notification = (
        UserNotification.objects.select_for_update()
        .filter(
            recipient=product.producer.user,
            product=product,
            notification_type=(
                UserNotification.NotificationType.LOW_STOCK
            ),
            is_resolved=False,
        )
        .first()
    )

    is_low_stock = (
        product.stock_quantity
        <= product.low_stock_threshold
    )

    if not is_low_stock:
        if active_notification:
            active_notification.is_resolved = True
            active_notification.is_read = True

            active_notification.save(
                update_fields=[
                    "is_resolved",
                    "is_read",
                ]
            )

        return None

    quantity_text = format(
        product.stock_quantity.normalize(),
        "f",
    )

    unit_text = (
        product.get_unit_display().lower()
    )

    message = (
        f"Low Stock Alert: {product.name} - "
        f"Only {quantity_text} {unit_text} remaining"
    )

    if active_notification:
        active_notification.title = (
            f"Low Stock Alert: {product.name}"
        )

        active_notification.message = message
        active_notification.is_read = False

        active_notification.save(
            update_fields=[
                "title",
                "message",
                "is_read",
            ]
        )

        return active_notification

    return UserNotification.objects.create(
        recipient=product.producer.user,
        notification_type=(
            UserNotification.NotificationType.LOW_STOCK
        ),
        product=product,
        title=f"Low Stock Alert: {product.name}",
        message=message,
        link=reverse(
            "marketplace:product_update",
            args=[product.id],
        ),
    )
