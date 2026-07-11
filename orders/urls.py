from django.urls import path

from . import views


app_name = "orders"


urlpatterns = [
    path(
        "",
        views.cart_detail,
        name="cart_detail",
    ),
    path(
        "add/<int:product_id>/",
        views.add_to_cart,
        name="add_to_cart",
    ),
    path(
        "items/<int:item_id>/update/",
        views.update_cart_item,
        name="update_cart_item",
    ),
    path(
        "items/<int:item_id>/remove/",
        views.remove_cart_item,
        name="remove_cart_item",
    ),
    path(
        "clear/",
        views.clear_cart,
        name="clear_cart",
    ),
    path(
        "checkout/",
        views.checkout,
        name="checkout",
    ),
    path(
        "orders/",
        views.order_list,
        name="order_list",
    ),
    path(
        "orders/<int:order_id>/",
        views.order_detail,
        name="order_detail",
    ),
]
