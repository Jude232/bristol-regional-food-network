from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny

from marketplace.models import Category, Product
from marketplace.views import customer_visible_products
from orders.models import Order, ProducerOrder

from .permissions import (
    IsCustomerAccount,
    IsProducer,
)
from .serializers import (
    CategorySerializer,
    CustomerOrderSerializer,
    ProducerOrderSerializer,
    ProducerProductSerializer,
    PublicProductSerializer,
)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """Public active-category API."""

    permission_classes = [
        AllowAny,
    ]

    serializer_class = CategorySerializer

    queryset = Category.objects.filter(
        is_active=True
    ).order_by("name")


class PublicProductViewSet(
    viewsets.ReadOnlyModelViewSet
):
    """Public API containing currently purchasable products."""

    permission_classes = [
        AllowAny,
    ]

    serializer_class = PublicProductSerializer

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    filterset_fields = {
        "category__slug": [
            "exact",
        ],
        "organic_certified": [
            "exact",
        ],
        "availability_status": [
            "exact",
        ],
    }

    search_fields = (
        "name",
        "description",
        "category__name",
        "producer__business_name",
        "allergen_information",
    )

    ordering_fields = (
        "name",
        "price",
        "created_at",
    )

    ordering = (
        "name",
    )

    def get_queryset(self):
        return customer_visible_products().order_by(
            "name"
        )


class ProducerProductViewSet(
    viewsets.ModelViewSet
):
    """Producer-owned product-management API."""

    permission_classes = [
        IsProducer,
    ]

    serializer_class = ProducerProductSerializer

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    filterset_fields = {
        "category__slug": [
            "exact",
        ],
        "is_active": [
            "exact",
        ],
        "organic_certified": [
            "exact",
        ],
        "availability_status": [
            "exact",
        ],
    }

    search_fields = (
        "name",
        "description",
        "category__name",
    )

    ordering_fields = (
        "name",
        "price",
        "stock_quantity",
        "updated_at",
    )

    ordering = (
        "name",
    )

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Product.objects.none()

        producer = getattr(
            self.request.user,
            "producer_profile",
            None,
        )

        if producer is None:
            return Product.objects.none()

        return (
            Product.objects.filter(
                producer=producer
            )
            .select_related(
                "producer",
                "category",
            )
            .order_by("name")
        )

    def perform_create(self, serializer):
        producer = getattr(
            self.request.user,
            "producer_profile",
            None,
        )

        if producer is None:
            raise PermissionDenied(
                "This account has no producer profile."
            )

        serializer.save(
            producer=producer
        )


class CustomerOrderViewSet(
    viewsets.ReadOnlyModelViewSet
):
    """Customer API containing only the user's own orders."""

    permission_classes = [
        IsCustomerAccount,
    ]

    serializer_class = CustomerOrderSerializer

    filter_backends = [
        DjangoFilterBackend,
        filters.OrderingFilter,
    ]

    filterset_fields = {
        "status": [
            "exact",
        ],
        "payment_status": [
            "exact",
        ],
    }

    ordering_fields = (
        "created_at",
        "total_amount",
    )

    ordering = (
        "-created_at",
    )

    def get_queryset(self):
        return (
            Order.objects.filter(
                customer=self.request.user
            )
            .prefetch_related(
                "producer_orders__producer",
                "producer_orders__items",
            )
            .order_by("-created_at")
        )


class ProducerOrderViewSet(
    viewsets.ReadOnlyModelViewSet
):
    """Producer API containing only that producer's order portions."""

    permission_classes = [
        IsProducer,
    ]

    serializer_class = ProducerOrderSerializer

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    filterset_fields = {
        "status": [
            "exact",
        ],
    }

    search_fields = (
        "order__order_number",
        "order__customer__email",
        "items__product_name",
    )

    ordering_fields = (
        "delivery_at",
        "created_at",
        "subtotal",
    )

    ordering = (
        "delivery_at",
    )

    def get_queryset(self):
        producer = getattr(
            self.request.user,
            "producer_profile",
            None,
        )

        if producer is None:
            return ProducerOrder.objects.none()

        return (
            ProducerOrder.objects.filter(
                producer=producer
            )
            .select_related(
                "producer",
                "order",
                "order__customer",
                "order__customer__customer_profile",
            )
            .prefetch_related(
                "items",
            )
            .order_by(
                "delivery_at",
                "order__order_number",
            )
        )
