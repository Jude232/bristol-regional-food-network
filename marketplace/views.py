from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import ProducerProfile, User

from .forms import ProductForm
from .models import Category, Product


def customer_visible_products():
    """
    Return products that customers are currently allowed to purchase.
    """

    today = timezone.localdate()

    return (
        Product.objects.select_related(
            "producer",
            "producer__user",
            "category",
        )
        .filter(
            is_active=True,
            stock_quantity__gt=0,
            availability_status__in=[
                Product.Availability.IN_SEASON,
                Product.Availability.YEAR_ROUND,
            ],
        )
        .filter(
            Q(available_from__isnull=True)
            | Q(available_from__lte=today)
        )
        .filter(
            Q(available_until__isnull=True)
            | Q(available_until__gte=today)
        )
    )


def producer_required(view_function):
    """
    Restrict a view to authenticated users with a producer profile.
    """

    @login_required
    @wraps(view_function)
    def wrapped_view(request, *args, **kwargs):
        if request.user.role != User.Role.PRODUCER:
            raise PermissionDenied(
                "Only producer accounts can access this page."
            )

        try:
            request.producer_profile = request.user.producer_profile
        except ProducerProfile.DoesNotExist as error:
            raise PermissionDenied(
                "This producer account does not have a profile."
            ) from error

        return view_function(request, *args, **kwargs)

    return wrapped_view


def product_list(request):
    """
    Display customer-visible products with search and filtering.
    """

    products = customer_visible_products()

    search_query = request.GET.get(
        "q",
        "",
    ).strip()

    category_slug = request.GET.get(
        "category",
        "",
    ).strip()

    organic_filter = request.GET.get(
        "organic",
        "",
    ).strip().lower()

    if search_query:
        products = products.filter(
            Q(name__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(producer__business_name__icontains=search_query)
            | Q(category__name__icontains=search_query)
            | Q(allergen_information__icontains=search_query)
        )

    if category_slug:
        products = products.filter(
            category__slug=category_slug
        )

    if organic_filter == "true":
        products = products.filter(
            organic_certified=True
        )

    categories = Category.objects.filter(
        is_active=True
    )

    return render(
        request,
        "marketplace/product_list.html",
        {
            "products": products,
            "categories": categories,
            "search_query": search_query,
            "selected_category": category_slug,
            "organic_filter": organic_filter,
        },
    )


def product_detail(request, product_id):
    """
    Display the customer-facing details of one available product.
    """

    product = get_object_or_404(
        customer_visible_products(),
        pk=product_id,
    )

    return render(
        request,
        "marketplace/product_detail.html",
        {
            "product": product,
        },
    )


@producer_required
def producer_product_list(request):
    """
    Display products belonging only to the logged-in producer.
    """

    products = (
        Product.objects.select_related("category")
        .filter(producer=request.producer_profile)
        .order_by("name")
    )

    return render(
        request,
        "marketplace/producer_product_list.html",
        {
            "products": products,
        },
    )


@producer_required
def product_create(request):
    """
    Allow a producer to create a product linked to their profile.
    """

    if request.method == "POST":
        form = ProductForm(request.POST)

        if form.is_valid():
            product = form.save(commit=False)
            product.producer = request.producer_profile
            product.save()

            messages.success(
                request,
                f"{product.name} was added successfully.",
            )

            return redirect(
                "marketplace:producer_product_list"
            )
    else:
        form = ProductForm()

    return render(
        request,
        "marketplace/product_form.html",
        {
            "form": form,
            "page_title": "Add a new product",
            "submit_text": "Create product",
        },
    )


@producer_required
def product_update(request, product_id):
    """
    Allow producers to update only products that they own.
    """

    product = get_object_or_404(
        Product,
        pk=product_id,
        producer=request.producer_profile,
    )

    if request.method == "POST":
        form = ProductForm(
            request.POST,
            instance=product,
        )

        if form.is_valid():
            product = form.save()

            messages.success(
                request,
                f"{product.name} was updated successfully.",
            )

            return redirect(
                "marketplace:producer_product_list"
            )
    else:
        form = ProductForm(
            instance=product,
        )

    return render(
        request,
        "marketplace/product_form.html",
        {
            "form": form,
            "product": product,
            "page_title": f"Edit {product.name}",
            "submit_text": "Save changes",
        },
    )


@producer_required
def product_toggle_active(request, product_id):
    """
    Activate or deactivate a producer-owned product.
    """

    if request.method != "POST":
        raise PermissionDenied(
            "Product availability can only be changed using POST."
        )

    product = get_object_or_404(
        Product,
        pk=product_id,
        producer=request.producer_profile,
    )

    product.is_active = not product.is_active
    product.save(
        update_fields=[
            "is_active",
            "updated_at",
        ]
    )

    state = (
        "activated"
        if product.is_active
        else "deactivated"
    )

    messages.success(
        request,
        f"{product.name} was {state}.",
    )

    return redirect(
        "marketplace:producer_product_list"
    )
