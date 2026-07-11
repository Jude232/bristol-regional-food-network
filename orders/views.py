from decimal import Decimal
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import User
from marketplace.models import Product
from marketplace.views import customer_visible_products

from .forms import CartQuantityForm
from .models import Cart, CartItem


CUSTOMER_ROLES = {
    User.Role.CUSTOMER,
    User.Role.COMMUNITY_GROUP,
    User.Role.RESTAURANT,
}


def customer_required(view_function):
    """Restrict a view to authenticated customer account types."""

    @login_required
    @wraps(view_function)
    def wrapped_view(
        request: HttpRequest,
        *args,
        **kwargs,
    ) -> HttpResponse:
        if request.user.role not in CUSTOMER_ROLES:
            raise PermissionDenied(
                "Only customer accounts can use the shopping cart."
            )

        return view_function(
            request,
            *args,
            **kwargs,
        )

    return wrapped_view


def build_producer_groups(items):
    """Group cart items by producer for multi-vendor awareness."""

    grouped_items = {}

    for item in items:
        producer = item.product.producer

        if producer.id not in grouped_items:
            grouped_items[producer.id] = {
                "producer": producer,
                "items": [],
                "subtotal": Decimal("0.00"),
            }

        grouped_items[producer.id]["items"].append(item)

        grouped_items[producer.id]["subtotal"] += (
            item.line_total
        )

    return list(grouped_items.values())


@customer_required
def cart_detail(request):
    """Display all items in the logged-in customer's cart."""

    cart, _ = Cart.objects.get_or_create(
        customer=request.user
    )

    cart = (
        Cart.objects.prefetch_related(
            Prefetch(
                "items",
                queryset=CartItem.objects.select_related(
                    "product",
                    "product__category",
                    "product__producer",
                ),
            )
        )
        .get(pk=cart.pk)
    )

    items = list(cart.items.all())
    producer_groups = build_producer_groups(items)

    return render(
        request,
        "orders/cart_detail.html",
        {
            "cart": cart,
            "producer_groups": producer_groups,
        },
    )


@customer_required
def add_to_cart(request, product_id):
    """Add an available product to the customer's persistent cart."""

    if request.method != "POST":
        raise PermissionDenied(
            "Products can only be added using a form submission."
        )

    product = get_object_or_404(
        customer_visible_products(),
        pk=product_id,
    )

    cart, _ = Cart.objects.get_or_create(
        customer=request.user
    )

    cart_item = CartItem.objects.filter(
        cart=cart,
        product=product,
    ).first()

    existing_quantity = (
        cart_item.quantity
        if cart_item
        else Decimal("0.00")
    )

    form = CartQuantityForm(
        request.POST,
        product=product,
        existing_quantity=existing_quantity,
        add_to_existing=True,
    )

    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(
                    request,
                    error,
                )

        return redirect(
            "marketplace:product_detail",
            product_id=product.id,
        )

    quantity = form.cleaned_data["quantity"]

    if cart_item:
        cart_item.quantity += quantity
    else:
        cart_item = CartItem(
            cart=cart,
            product=product,
            quantity=quantity,
        )

    cart_item.full_clean()
    cart_item.save()

    messages.success(
        request,
        f"{product.name} was added to your cart.",
    )

    return redirect(
        "orders:cart_detail"
    )


@customer_required
def update_cart_item(request, item_id):
    """Replace an existing cart item's quantity."""

    if request.method != "POST":
        raise PermissionDenied(
            "Cart quantities can only be changed using POST."
        )

    cart_item = get_object_or_404(
        CartItem.objects.select_related("product"),
        pk=item_id,
        cart__customer=request.user,
    )

    form = CartQuantityForm(
        request.POST,
        product=cart_item.product,
    )

    if form.is_valid():
        cart_item.quantity = form.cleaned_data["quantity"]
        cart_item.full_clean()
        cart_item.save(
            update_fields=[
                "quantity",
                "updated_at",
            ]
        )

        messages.success(
            request,
            f"{cart_item.product.name} quantity was updated.",
        )
    else:
        for errors in form.errors.values():
            for error in errors:
                messages.error(
                    request,
                    error,
                )

    return redirect(
        "orders:cart_detail"
    )


@customer_required
def remove_cart_item(request, item_id):
    """Remove one product from the customer's cart."""

    if request.method != "POST":
        raise PermissionDenied(
            "Cart items can only be removed using POST."
        )

    cart_item = get_object_or_404(
        CartItem.objects.select_related("product"),
        pk=item_id,
        cart__customer=request.user,
    )

    product_name = cart_item.product.name
    cart_item.delete()

    messages.success(
        request,
        f"{product_name} was removed from your cart.",
    )

    return redirect(
        "orders:cart_detail"
    )


@customer_required
def clear_cart(request):
    """Remove every product from the customer's cart."""

    if request.method != "POST":
        raise PermissionDenied(
            "The cart can only be cleared using POST."
        )

    cart, _ = Cart.objects.get_or_create(
        customer=request.user
    )

    cart.items.all().delete()

    messages.success(
        request,
        "Your cart was cleared.",
    )

    return redirect(
        "orders:cart_detail"
    )
