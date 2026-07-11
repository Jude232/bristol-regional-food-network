from django.contrib import admin

from .models import Cart, CartItem


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
