from decimal import Decimal
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import User
from marketplace.views import customer_visible_products

from .forms import CartQuantityForm, CheckoutForm
from .models import (
    COMMISSION_RATE,
    Cart,
    CartItem,
    Order,
    PaymentTransaction,
    money,
)
from .services import (
    CheckoutError,
    PaymentDeclined,
    create_order_from_cart,
)


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
                "Only customer accounts can use this feature."
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


def get_customer_cart(customer):
    """Return a cart with all product and producer data loaded."""

    cart, _ = Cart.objects.get_or_create(
        customer=customer
    )

    return (
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


@customer_required
def cart_detail(request):
    """Display all items in the logged-in customer's cart."""

    cart = get_customer_cart(
        request.user
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


@customer_required
def checkout(request):
    """Display and process the single/multi-producer checkout."""

    cart = get_customer_cart(
        request.user
    )

    items = list(cart.items.all())

    if not items:
        messages.error(
            request,
            "Add at least one product before checking out.",
        )

        return redirect(
            "orders:cart_detail"
        )

    producer_groups = build_producer_groups(items)

    profile = getattr(
        request.user,
        "customer_profile",
        None,
    )

    initial = {}

    if profile:
        initial = {
            "delivery_address": profile.delivery_address,
            "delivery_postcode": profile.postcode,
        }

    if request.method == "POST":
        form = CheckoutForm(
            request.POST
        )

        if form.is_valid():
            try:
                order = create_order_from_cart(
                    customer=request.user,
                    delivery_address=(
                        form.cleaned_data[
                            "delivery_address"
                        ]
                    ),
                    delivery_postcode=(
                        form.cleaned_data[
                            "delivery_postcode"
                        ]
                    ),
                    delivery_at=(
                        form.cleaned_data[
                            "delivery_at"
                        ]
                    ),
                    special_instructions=(
                        form.cleaned_data[
                            "special_instructions"
                        ]
                    ),
                    payment_token=(
                        form.cleaned_data[
                            "payment_token"
                        ]
                    ),
                    card_last_four=(
                        form.cleaned_data[
                            "card_last_four"
                        ]
                    ),
                )
            except PaymentDeclined as error:
                form.add_error(
                    "payment_token",
                    str(error),
                )
            except CheckoutError as error:
                form.add_error(
                    None,
                    str(error),
                )
            else:
                messages.success(
                    request,
                    (
                        "Your order was placed successfully. "
                        f"Order number: {order.order_number}"
                    ),
                )

                return redirect(
                    "orders:order_detail",
                    order_id=order.id,
                )
    else:
        form = CheckoutForm(
            initial=initial
        )

    commission_preview = money(
        cart.total * COMMISSION_RATE
    )

    producer_payment_preview = money(
        cart.total - commission_preview
    )

    return render(
        request,
        "orders/checkout.html",
        {
            "cart": cart,
            "producer_groups": producer_groups,
            "form": form,
            "commission_preview": commission_preview,
            "producer_payment_preview": (
                producer_payment_preview
            ),
        },
    )


@customer_required
def order_list(request):
    """Display orders belonging to the logged-in customer."""

    orders = (
        Order.objects.filter(
            customer=request.user
        )
        .prefetch_related(
            "producer_orders__producer"
        )
        .order_by("-created_at")
    )

    return render(
        request,
        "orders/order_list.html",
        {
            "orders": orders,
        },
    )


@customer_required
def order_detail(request, order_id):
    """Display one order owned by the logged-in customer."""

    order = get_object_or_404(
        Order.objects.prefetch_related(
            "producer_orders__producer",
            "producer_orders__items",
        ),
        pk=order_id,
        customer=request.user,
    )

    payment = PaymentTransaction.objects.filter(
        order=order
    ).first()

    return render(
        request,
        "orders/order_detail.html",
        {
            "order": order,
            "payment": payment,
        },
    )
