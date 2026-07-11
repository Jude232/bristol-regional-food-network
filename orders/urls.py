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
    path(
        "producer/orders/",
        views.producer_order_list,
        name="producer_order_list",
    ),
    path(
        "producer/orders/<int:producer_order_id>/",
        views.producer_order_detail,
        name="producer_order_detail",
    ),
    path(
        "producer/orders/<int:producer_order_id>/status/",
        views.producer_order_status_update,
        name="producer_order_status_update",
    ),
    path(
        "notifications/",
        views.notification_list,
        name="notification_list",
    ),
    path(
        "notifications/<int:notification_id>/read/",
        views.notification_mark_read,
        name="notification_mark_read",
    ),
]
