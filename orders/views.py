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

#This file processes requests, checks user ownership, calls forms and services, and sends data to the HTML templates.
#Queries include the current customer or producer, preventing users from accessing records belonging to someone else.

# These account types can use customer ordering features.
#
# Community groups and restaurants use the same cart and checkout
# process as normal customer accounts.
CUSTOMER_ROLES = {
    User.Role.CUSTOMER,
    User.Role.COMMUNITY_GROUP,
    User.Role.RESTAURANT,
}


def customer_required(view_function):
    """
    Restrict a view to logged-in customer account types.

    This custom decorator first checks that the user is authenticated
    and then checks that their role is allowed to use customer
    marketplace features.
    """

    @login_required
    @wraps(view_function)
    def wrapped_view(
        request: HttpRequest,
        *args,
        **kwargs,
    ) -> HttpResponse:
        # Refuse access when the account is not a customer-type role.
        if request.user.role not in CUSTOMER_ROLES:
            raise PermissionDenied(
                "Only customer accounts can use this feature."
            )

        # Run the original view after the permission check succeeds.
        return view_function(
            request,
            *args,
            **kwargs,
        )

    return wrapped_view


def build_producer_groups(items):
    """
    Group cart items according to their producer.

    This allows the cart and checkout pages to clearly show that one
    customer order may contain products from several producers.
    """

    grouped_items = {}

    for item in items:
        producer = item.product.producer

        # Create a new group when this producer has not been seen yet.
        if producer.id not in grouped_items:
            grouped_items[producer.id] = {
                "producer": producer,
                "items": [],
                "subtotal": Decimal("0.00"),
            }

        # Add the item to its producer's group.
        grouped_items[producer.id]["items"].append(item)

        # Add the item's line total to the producer subtotal.
        grouped_items[producer.id]["subtotal"] += (
            item.line_total
        )

    return list(grouped_items.values())


def get_customer_cart(customer):
    """
    Return the customer's persistent shopping cart.

    A cart is created automatically if the customer does not already
    have one. Related product, category and producer information is
    loaded efficiently for displaying the cart.
    """

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
    """
    Display all items in the logged-in customer's cart.
    """

    cart = get_customer_cart(
        request.user
    )

    items = list(cart.items.all())

    # Group the items by producer before sending them to the template.
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
    """
    Add an available product to the customer's persistent cart.
    """

    # Cart changes must use POST so that simply opening a URL cannot
    # accidentally add an item.
    if request.method != "POST":
        raise PermissionDenied(
            "Products can only be added using a form submission."
        )

    # Only products that customers are allowed to see can be added.
    product = get_object_or_404(
        customer_visible_products(),
        pk=product_id,
    )

    # Create the user's cart if it does not already exist.
    cart, _ = Cart.objects.get_or_create(
        customer=request.user
    )

    # Check whether this product is already in the cart.
    cart_item = CartItem.objects.filter(
        cart=cart,
        product=product,
    ).first()

    existing_quantity = (
        cart_item.quantity
        if cart_item
        else Decimal("0.00")
    )

    # Validate the requested quantity against product stock.
    form = CartQuantityForm(
        request.POST,
        product=product,
        existing_quantity=existing_quantity,
        add_to_existing=True,
    )

    # Display each form error to the customer.
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

    # Increase the quantity when the product is already in the cart.
    if cart_item:
        cart_item.quantity += quantity

    # Otherwise, create a new cart item.
    else:
        cart_item = CartItem(
            cart=cart,
            product=product,
            quantity=quantity,
        )

    # Run model validation before saving.
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
    """
    Replace the quantity of an existing cart item.
    """

    if request.method != "POST":
        raise PermissionDenied(
            "Cart quantities can only be changed using POST."
        )

    # The customer can only update an item belonging to their own cart.
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

        # Validate the new quantity before saving it.
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
        # Display validation errors such as exceeding available stock.
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
    """
    Remove one product from the customer's cart.
    """

    if request.method != "POST":
        raise PermissionDenied(
            "Cart items can only be removed using POST."
        )

    # Customers can only remove items from their own cart.
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
    """
    Remove every item from the customer's cart.
    """

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
    """
    Display and process the single or multi-producer checkout page.

    GET requests display the form, while POST requests validate the
    details and call the checkout service to create the order.
    """

    cart = get_customer_cart(
        request.user
    )

    items = list(cart.items.all())

    # Customers cannot access checkout with an empty cart.
    if not items:
        messages.error(
            request,
            "Add at least one product before checking out.",
        )

        return redirect(
            "orders:cart_detail"
        )

    # Group items so the customer can see which producer supplies
    # each part of the order.
    producer_groups = build_producer_groups(items)

    # Try to retrieve saved delivery information from the user's profile.
    profile = getattr(
        request.user,
        "customer_profile",
        None,
    )

    initial = {}

    # Pre-fill the checkout form when profile details are available.
    if profile:
        initial = {
            "delivery_address": profile.delivery_address,
            "delivery_postcode": profile.postcode,
        }

    # Process the submitted checkout form.
    if request.method == "POST":
        form = CheckoutForm(
            request.POST
        )

        if form.is_valid():
            try:
                # The service safely creates the order, producer orders,
                # payment record, notifications and stock changes.
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

            # Show a payment-specific error when MockPay declines.
            except PaymentDeclined as error:
                form.add_error(
                    "payment_token",
                    str(error),
                )

            # Show other checkout problems as general form errors.
            except CheckoutError as error:
                form.add_error(
                    None,
                    str(error),
                )

            # Redirect to the new order when checkout succeeds.
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

    # Display a blank form for a normal GET request.
    else:
        form = CheckoutForm(
            initial=initial
        )

    # Calculate a preview of the marketplace's 5% commission.
    commission_preview = money(
        cart.total * COMMISSION_RATE
    )

    # Calculate a preview of the amount allocated to producers.
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
    """
    Display all orders belonging to the logged-in customer.
    """

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
    """
    Display one order belonging to the logged-in customer.

    Filtering by customer prevents another user from viewing the order
    by manually changing the order ID in the URL.
    """

    order = get_object_or_404(
        Order.objects.prefetch_related(
            "producer_orders__producer",
            "producer_orders__items",
        ),
        pk=order_id,
        customer=request.user,
    )

    # Retrieve the simulated payment record linked to the order.
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


# These imports support the producer order-management section below.
#
# In a future refactor they could be moved to the top of the file,
# but keeping them here does not change how the code works.
from django.db import transaction
from django.urls import reverse

from .forms import ProducerOrderStatusForm
from .models import (
    ProducerOrder,
    ProducerOrderStatusHistory,
    UserNotification,
)


def get_producer_profile(request):
    """
    Return the producer profile belonging to the current user.

    The function also prevents non-producer accounts or incomplete
    producer accounts from accessing producer order pages.
    """

    # The logged-in account must have the producer role.
    if request.user.role != User.Role.PRODUCER:
        raise PermissionDenied(
            "Only producer accounts can access incoming orders."
        )

    profile = getattr(
        request.user,
        "producer_profile",
        None,
    )

    # The account must also have an associated producer profile.
    if profile is None:
        raise PermissionDenied(
            "This producer account does not have a producer profile."
        )

    return profile


@login_required
def producer_order_list(request):
    """
    Display only the incoming orders belonging to the current producer.
    """

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

    # Read the optional status filter from the page URL.
    selected_status = request.GET.get(
        "status",
        "",
    ).strip()

    # Build a set of valid producer-order status values.
    valid_statuses = {
        choice.value
        for choice in ProducerOrder.Status
    }

    # Only apply the filter when the supplied status is valid.
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
    """
    Display one producer-owned section of a customer order.

    The query includes the current producer so producers cannot view
    another producer's part of an order by changing the URL.
    """

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

    # Retrieve the customer's contact and delivery profile where present.
    customer_profile = getattr(
        producer_order.order.customer,
        "customer_profile",
        None,
    )

    # The form only presents valid next statuses for this order.
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
    """
    Update the status of a producer-owned order section.

    The status update, history record, customer notification and main
    order update are handled inside one database transaction.
    """

    # Status changes must be submitted using a form.
    if request.method != "POST":
        raise PermissionDenied(
            "Order statuses can only be changed using POST."
        )

    producer = get_producer_profile(request)

    # Lock the producer-order row while its status is being updated.
    #
    # This prevents two simultaneous updates from overwriting each other.
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

    # Display form validation errors and return to the order page.
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

    # Save the previous status before changing it for the audit history.
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

    # Create a permanent audit record of the status change.
    ProducerOrderStatusHistory.objects.create(
        producer_order=producer_order,
        previous_status=previous_status,
        new_status=new_status,
        note=note,
        changed_by=request.user,
    )

    # Notify the customer that one producer has updated their order.
    UserNotification.objects.create(
        recipient=producer_order.order.customer,
        notification_type=(
            UserNotification.NotificationType.ORDER_STATUS
        ),
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

    # Retrieve the status of every producer section within the
    # main customer order.
    producer_statuses = list(
        order.producer_orders.values_list(
            "status",
            flat=True,
        )
    )

    # The whole customer order is complete only when all producers
    # have marked their sections as delivered.
    if (
        producer_statuses
        and all(
            status == ProducerOrder.Status.DELIVERED
            for status in producer_statuses
        )
    ):
        order.status = Order.Status.COMPLETED

    # The whole order is cancelled when every producer section
    # has been cancelled.
    elif (
        producer_statuses
        and all(
            status == ProducerOrder.Status.CANCELLED
            for status in producer_statuses
        )
    ):
        order.status = Order.Status.CANCELLED

    # If at least one producer has started processing the order,
    # the main order is marked as processing.
    elif any(
        status in {
            ProducerOrder.Status.CONFIRMED,
            ProducerOrder.Status.READY,
            ProducerOrder.Status.DELIVERED,
        }
        for status in producer_statuses
    ):
        order.status = Order.Status.PROCESSING

    # Otherwise, the main order remains pending.
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
    """
    Display notifications belonging to the logged-in user.
    """

    # The related_name ensures users only retrieve their own records.
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
    """
    Mark one notification belonging to the current user as read.
    """

    if request.method != "POST":
        raise PermissionDenied(
            "Notifications can only be changed using POST."
        )

    # Including recipient=request.user prevents users from changing
    # another account's notification.
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

    # Open the related order or product when the notification has a link.
    if notification.link:
        return redirect(
            notification.link
        )

    return redirect(
        "orders:notification_list"
    )