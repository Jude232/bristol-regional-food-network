from django.urls import path

from . import views


app_name = "marketplace"


urlpatterns = [
    path(
        "",
        views.product_list,
        name="product_list",
    ),
    path(
        "products/<int:product_id>/",
        views.product_detail,
        name="product_detail",
    ),
    path(
        "producer/products/",
        views.producer_product_list,
        name="producer_product_list",
    ),
    path(
        "producer/products/add/",
        views.product_create,
        name="product_create",
    ),
    path(
        "producer/products/<int:product_id>/edit/",
        views.product_update,
        name="product_update",
    ),
    path(
        "producer/products/<int:product_id>/toggle/",
        views.product_toggle_active,
        name="product_toggle_active",
    ),
]
