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


from django.db import transaction
from django.urls import reverse

from .forms import ProducerOrderStatusForm
from .models import (
    ProducerOrder,
    ProducerOrderStatusHistory,
    UserNotification,
)


def get_producer_profile(request):
    """Return the producer profile belonging to the current user."""

    if request.user.role != User.Role.PRODUCER:
        raise PermissionDenied(
            "Only producer accounts can access incoming orders."
        )

    profile = getattr(
        request.user,
        "producer_profile",
        None,
    )

    if profile is None:
        raise PermissionDenied(
            "This producer account does not have a producer profile."
        )

    return profile


@login_required
def producer_order_list(request):
    """Display only the incoming orders belonging to this producer."""

    producer = get_producer_profile(request)

    producer_orders = (
        ProducerOrder.objects.filter(
            producer=producer
        )
        .select_related(
            "order",
            "order__customer",
        )
        .prefetch_related(
            "items",
        )
        .order_by(
            "delivery_at",
            "order__order_number",
        )
    )

    selected_status = request.GET.get(
        "status",
        "",
    ).strip()

    valid_statuses = {
        choice.value
        for choice in ProducerOrder.Status
    }

    if selected_status in valid_statuses:
        producer_orders = producer_orders.filter(
            status=selected_status
        )

    return render(
        request,
        "orders/producer_order_list.html",
        {
            "producer_orders": producer_orders,
            "selected_status": selected_status,
            "status_choices": ProducerOrder.Status.choices,
        },
    )


@login_required
def producer_order_detail(
    request,
    producer_order_id,
):
    """Display one producer-owned portion of an order."""

    producer = get_producer_profile(request)

    producer_order = get_object_or_404(
        ProducerOrder.objects.select_related(
            "order",
            "order__customer",
            "producer",
        ).prefetch_related(
            "items",
            "status_history__changed_by",
        ),
        pk=producer_order_id,
        producer=producer,
    )

    customer_profile = getattr(
        producer_order.order.customer,
        "customer_profile",
        None,
    )

    status_form = ProducerOrderStatusForm(
        producer_order=producer_order
    )

    return render(
        request,
        "orders/producer_order_detail.html",
        {
            "producer_order": producer_order,
            "customer_profile": customer_profile,
            "status_form": status_form,
        },
    )


@login_required
@transaction.atomic
def producer_order_status_update(
    request,
    producer_order_id,
):
    """Advance an owned producer order through its lifecycle."""

    if request.method != "POST":
        raise PermissionDenied(
            "Order statuses can only be changed using POST."
        )

    producer = get_producer_profile(request)

    producer_order = get_object_or_404(
        ProducerOrder.objects.select_for_update()
        .select_related(
            "order",
            "order__customer",
            "producer",
        ),
        pk=producer_order_id,
        producer=producer,
    )

    form = ProducerOrderStatusForm(
        request.POST,
        producer_order=producer_order,
    )

    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(
                    request,
                    error,
                )

        return redirect(
            "orders:producer_order_detail",
            producer_order_id=producer_order.id,
        )

    previous_status = producer_order.status
    new_status = form.cleaned_data["next_status"]
    note = form.cleaned_data["note"].strip()

    producer_order.status = new_status
    producer_order.producer_note = note

    producer_order.save(
        update_fields=[
            "status",
            "producer_note",
            "updated_at",
        ]
    )

    ProducerOrderStatusHistory.objects.create(
        producer_order=producer_order,
        previous_status=previous_status,
        new_status=new_status,
        note=note,
        changed_by=request.user,
    )

    UserNotification.objects.create(
        recipient=producer_order.order.customer,
        title=(
            f"Order {producer_order.order.order_number} "
            "status updated"
        ),
        message=(
            f"{producer.business_name} changed your order "
            f"status to {producer_order.get_status_display()}."
        ),
        link=reverse(
            "orders:order_detail",
            args=[producer_order.order.id],
        ),
    )

    order = producer_order.order

    producer_statuses = list(
        order.producer_orders.values_list(
            "status",
            flat=True,
        )
    )

    if (
        producer_statuses
        and all(
            status == ProducerOrder.Status.DELIVERED
            for status in producer_statuses
        )
    ):
        order.status = Order.Status.COMPLETED

    elif (
        producer_statuses
        and all(
            status == ProducerOrder.Status.CANCELLED
            for status in producer_statuses
        )
    ):
        order.status = Order.Status.CANCELLED

    elif any(
        status in {
            ProducerOrder.Status.CONFIRMED,
            ProducerOrder.Status.READY,
            ProducerOrder.Status.DELIVERED,
        }
        for status in producer_statuses
    ):
        order.status = Order.Status.PROCESSING

    else:
        order.status = Order.Status.PENDING

    order.save(
        update_fields=[
            "status",
            "updated_at",
        ]
    )

    messages.success(
        request,
        (
            f"Order status changed to "
            f"{producer_order.get_status_display()}."
        ),
    )

    return redirect(
        "orders:producer_order_detail",
        producer_order_id=producer_order.id,
    )


@login_required
def notification_list(request):
    """Display notifications belonging to the logged-in user."""

    notifications = request.user.notifications.all()

    return render(
        request,
        "orders/notification_list.html",
        {
            "notifications": notifications,
        },
    )


@login_required
def notification_mark_read(
    request,
    notification_id,
):
    """Mark one owned notification as read."""

    if request.method != "POST":
        raise PermissionDenied(
            "Notifications can only be changed using POST."
        )

    notification = get_object_or_404(
        UserNotification,
        pk=notification_id,
        recipient=request.user,
    )

    notification.is_read = True
    notification.save(
        update_fields=[
            "is_read",
        ]
    )

    if notification.link:
        return redirect(
            notification.link
        )

    return redirect(
        "orders:notification_list"
    )
