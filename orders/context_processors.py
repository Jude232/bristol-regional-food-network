from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist


def cart_summary(request):
    """Provide the cart item count to all templates."""

    if not request.user.is_authenticated:
        return {
            "cart_item_count": Decimal("0.00"),
        }

    try:
        item_count = request.user.cart.item_count
    except ObjectDoesNotExist:
        item_count = Decimal("0.00")

    return {
        "cart_item_count": item_count,
    }
