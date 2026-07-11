from django.contrib import admin

from .models import (
    Cart,
    CartItem,
    Order,
    OrderItem,
    PaymentTransaction,
    ProducerOrder,
)


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0

    readonly_fields = (
        "added_at",
        "updated_at",
    )


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = (
        "customer",
        "item_count",
        "total",
        "updated_at",
    )

    search_fields = (
        "customer__email",
        "customer__first_name",
        "customer__last_name",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    inlines = [
        CartItemInline,
    ]


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "cart",
        "quantity",
        "line_total",
        "updated_at",
    )

    search_fields = (
        "product__name",
        "cart__customer__email",
    )

    readonly_fields = (
        "added_at",
        "updated_at",
    )


class ProducerOrderInline(admin.TabularInline):
    model = ProducerOrder
    extra = 0

    readonly_fields = (
        "subtotal",
        "commission_amount",
        "producer_payment",
        "created_at",
        "updated_at",
    )


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "customer",
        "status",
        "payment_status",
        "total_amount",
        "commission_amount",
        "created_at",
    )

    list_filter = (
        "status",
        "payment_status",
        "created_at",
    )

    search_fields = (
        "order_number",
        "customer__email",
        "delivery_postcode",
    )

    readonly_fields = (
        "order_number",
        "subtotal",
        "commission_amount",
        "producer_payment_total",
        "total_amount",
        "created_at",
        "updated_at",
    )

    inlines = [
        ProducerOrderInline,
    ]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0

    readonly_fields = (
        "product_name",
        "unit_name",
        "quantity",
        "unit_price",
        "line_total",
        "allergen_information",
        "created_at",
    )


@admin.register(ProducerOrder)
class ProducerOrderAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "producer",
        "delivery_at",
        "status",
        "subtotal",
        "producer_payment",
    )

    list_filter = (
        "status",
        "delivery_at",
        "producer",
    )

    search_fields = (
        "order__order_number",
        "producer__business_name",
    )

    readonly_fields = (
        "subtotal",
        "commission_amount",
        "producer_payment",
        "created_at",
        "updated_at",
    )

    inlines = [
        OrderItemInline,
    ]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        "product_name",
        "producer_order",
        "quantity",
        "unit_price",
        "line_total",
    )

    search_fields = (
        "product_name",
        "producer_order__order__order_number",
    )


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "transaction_reference",
        "order",
        "provider",
        "status",
        "amount",
        "card_last_four",
        "created_at",
    )

    list_filter = (
        "status",
        "provider",
        "created_at",
    )

    search_fields = (
        "transaction_reference",
        "order__order_number",
    )

    readonly_fields = (
        "transaction_reference",
        "created_at",
    )
