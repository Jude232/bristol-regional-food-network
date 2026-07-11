from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CategoryViewSet,
    CustomerOrderViewSet,
    ProducerOrderViewSet,
    ProducerProductViewSet,
    PublicProductViewSet,
)


app_name = "api"


router = DefaultRouter()

router.register(
    "categories",
    CategoryViewSet,
    basename="category",
)

router.register(
    "products",
    PublicProductViewSet,
    basename="public-product",
)

router.register(
    "producer/products",
    ProducerProductViewSet,
    basename="producer-product",
)

router.register(
    "customer/orders",
    CustomerOrderViewSet,
    basename="customer-order",
)

router.register(
    "producer/orders",
    ProducerOrderViewSet,
    basename="producer-order",
)


urlpatterns = [
    path(
        "",
        include(router.urls),
    ),
]
