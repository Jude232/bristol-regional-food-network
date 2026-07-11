from django.contrib import admin

from .models import Category, Product


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "is_active",
    )

    list_filter = (
        "is_active",
    )

    search_fields = (
        "name",
        "description",
    )

    prepopulated_fields = {
        "slug": ("name",),
    }


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "producer",
        "category",
        "price",
        "unit",
        "stock_quantity",
        "availability_status",
        "organic_certified",
        "is_active",
    )

    list_filter = (
        "category",
        "availability_status",
        "organic_certified",
        "is_active",
    )

    search_fields = (
        "name",
        "description",
        "producer__business_name",
        "allergen_information",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Product details",
            {
                "fields": (
                    "producer",
                    "category",
                    "name",
                    "description",
                    "price",
                    "unit",
                ),
            },
        ),
        (
            "Inventory and availability",
            {
                "fields": (
                    "stock_quantity",
                    "low_stock_threshold",
                    "availability_status",
                    "available_from",
                    "available_until",
                    "is_active",
                ),
            },
        ),
        (
            "Food information",
            {
                "fields": (
                    "harvest_date",
                    "best_before_date",
                    "allergen_information",
                    "organic_certified",
                    "organic_certification_details",
                ),
            },
        ),
        (
            "System information",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )
