from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from marketplace.models import Category, Product
from orders.models import Order, OrderItem, ProducerOrder


class CategorySerializer(serializers.ModelSerializer):
    """Public category representation."""

    class Meta:
        model = Category

        fields = (
            "id",
            "name",
            "slug",
            "description",
        )


class PublicProductSerializer(serializers.ModelSerializer):
    """Customer-safe public product representation."""

    category = CategorySerializer(
        read_only=True,
    )

    producer_name = serializers.CharField(
        source="producer.business_name",
        read_only=True,
    )

    producer_postcode = serializers.CharField(
        source="producer.postcode",
        read_only=True,
    )

    farm_origin = serializers.CharField(
        read_only=True,
    )

    availability_display = serializers.CharField(
        source="get_availability_status_display",
        read_only=True,
    )

    unit_display = serializers.CharField(
        source="get_unit_display",
        read_only=True,
    )

    is_available_now = serializers.BooleanField(
        read_only=True,
    )

    class Meta:
        model = Product

        fields = (
            "id",
            "name",
            "description",
            "category",
            "producer_name",
            "producer_postcode",
            "farm_origin",
            "price",
            "unit",
            "unit_display",
            "stock_quantity",
            "availability_status",
            "availability_display",
            "available_from",
            "available_until",
            "harvest_date",
            "best_before_date",
            "allergen_information",
            "organic_certified",
            "organic_certification_details",
            "is_available_now",
            "created_at",
            "updated_at",
        )


class ProducerProductSerializer(serializers.ModelSerializer):
    """Create and update products belonging to a producer."""

    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(
            is_active=True
        )
    )

    category_name = serializers.CharField(
        source="category.name",
        read_only=True,
    )

    producer_name = serializers.CharField(
        source="producer.business_name",
        read_only=True,
    )

    unit_display = serializers.CharField(
        source="get_unit_display",
        read_only=True,
    )

    availability_display = serializers.CharField(
        source="get_availability_status_display",
        read_only=True,
    )

    is_available_now = serializers.BooleanField(
        read_only=True,
    )

    is_low_stock = serializers.BooleanField(
        read_only=True,
    )

    class Meta:
        model = Product

        fields = (
            "id",
            "producer_name",
            "category",
            "category_name",
            "name",
            "description",
            "price",
            "unit",
            "unit_display",
            "stock_quantity",
            "low_stock_threshold",
            "availability_status",
            "availability_display",
            "available_from",
            "available_until",
            "harvest_date",
            "best_before_date",
            "allergen_information",
            "organic_certified",
            "organic_certification_details",
            "is_active",
            "is_available_now",
            "is_low_stock",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "created_at",
            "updated_at",
        )

    def validate(self, attributes):
        instance = self.instance

        organic_certified = attributes.get(
            "organic_certified",
            getattr(
                instance,
                "organic_certified",
                False,
            ),
        )

        certification_details = attributes.get(
            "organic_certification_details",
            getattr(
                instance,
                "organic_certification_details",
                "",
            ),
        )

        if (
            organic_certified
            and not certification_details.strip()
        ):
            raise serializers.ValidationError(
                {
                    "organic_certification_details": (
                        "Certification details are required "
                        "for an organic product."
                    )
                }
            )

        available_from = attributes.get(
            "available_from",
            getattr(
                instance,
                "available_from",
                None,
            ),
        )

        available_until = attributes.get(
            "available_until",
            getattr(
                instance,
                "available_until",
                None,
            ),
        )

        if (
            available_from
            and available_until
            and available_until < available_from
        ):
            raise serializers.ValidationError(
                {
                    "available_until": (
                        "The availability end date cannot be "
                        "before the start date."
                    )
                }
            )

        harvest_date = attributes.get(
            "harvest_date",
            getattr(
                instance,
                "harvest_date",
                None,
            ),
        )

        best_before_date = attributes.get(
            "best_before_date",
            getattr(
                instance,
                "best_before_date",
                None,
            ),
        )

        if (
            harvest_date
            and best_before_date
            and best_before_date < harvest_date
        ):
            raise serializers.ValidationError(
                {
                    "best_before_date": (
                        "The best-before date cannot be "
                        "before the harvest date."
                    )
                }
            )

        return attributes

    @staticmethod
    def validate_model(instance):
        try:
            instance.full_clean()
        except DjangoValidationError as error:
            if hasattr(error, "message_dict"):
                raise serializers.ValidationError(
                    error.message_dict
                ) from error

            raise serializers.ValidationError(
                error.messages
            ) from error

    def create(self, validated_data):
        product = Product(
            **validated_data
        )

        self.validate_model(product)
        product.save()

        return product

    def update(self, instance, validated_data):
        for field_name, value in validated_data.items():
            setattr(
                instance,
                field_name,
                value,
            )

        self.validate_model(instance)
        instance.save()

        return instance


class OrderItemSerializer(serializers.ModelSerializer):
    """Permanent purchased-product snapshot."""

    class Meta:
        model = OrderItem

        fields = (
            "id",
            "product_name",
            "unit_name",
            "quantity",
            "unit_price",
            "line_total",
            "allergen_information",
        )


class CustomerProducerOrderSerializer(
    serializers.ModelSerializer
):
    """One producer section shown inside a customer order."""

    producer_name = serializers.CharField(
        source="producer.business_name",
        read_only=True,
    )

    producer_postcode = serializers.CharField(
        source="producer.postcode",
        read_only=True,
    )

    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    items = OrderItemSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = ProducerOrder

        fields = (
            "id",
            "producer_name",
            "producer_postcode",
            "delivery_at",
            "status",
            "status_display",
            "producer_note",
            "subtotal",
            "commission_amount",
            "producer_payment",
            "items",
        )


class CustomerOrderSerializer(serializers.ModelSerializer):
    """Order history belonging to the authenticated customer."""

    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    payment_status_display = serializers.CharField(
        source="get_payment_status_display",
        read_only=True,
    )

    producer_orders = CustomerProducerOrderSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = Order

        fields = (
            "id",
            "order_number",
            "status",
            "status_display",
            "payment_status",
            "payment_status_display",
            "delivery_address",
            "delivery_postcode",
            "special_instructions",
            "subtotal",
            "commission_amount",
            "producer_payment_total",
            "total_amount",
            "created_at",
            "updated_at",
            "producer_orders",
        )


class ProducerOrderSerializer(serializers.ModelSerializer):
    """Incoming-order data visible to the owning producer."""

    order_number = serializers.CharField(
        source="order.order_number",
        read_only=True,
    )

    order_created_at = serializers.DateTimeField(
        source="order.created_at",
        read_only=True,
    )

    customer_name = serializers.SerializerMethodField()

    customer_email = serializers.EmailField(
        source="order.customer.email",
        read_only=True,
    )

    customer_phone = serializers.SerializerMethodField()

    delivery_address = serializers.CharField(
        source="order.delivery_address",
        read_only=True,
    )

    delivery_postcode = serializers.CharField(
        source="order.delivery_postcode",
        read_only=True,
    )

    special_instructions = serializers.CharField(
        source="order.special_instructions",
        read_only=True,
    )

    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    items = OrderItemSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = ProducerOrder

        fields = (
            "id",
            "order_number",
            "order_created_at",
            "customer_name",
            "customer_email",
            "customer_phone",
            "delivery_address",
            "delivery_postcode",
            "special_instructions",
            "delivery_at",
            "status",
            "status_display",
            "producer_note",
            "subtotal",
            "commission_amount",
            "producer_payment",
            "items",
        )

    def get_customer_name(self, producer_order):
        customer = producer_order.order.customer

        return (
            customer.get_full_name()
            or customer.email
        )

    def get_customer_phone(self, producer_order):
        profile = getattr(
            producer_order.order.customer,
            "customer_profile",
            None,
        )

        if profile is None:
            return ""

        return profile.phone
