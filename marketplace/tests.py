from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import ProducerProfile, User
from marketplace.models import Category, Product


class ProductModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="producer@example.test",
            password="ProducerTest2026!",
            first_name="Jane",
            last_name="Smith",
            role=User.Role.PRODUCER,
        )

        self.producer = ProducerProfile.objects.create(
            user=self.user,
            business_name="Bristol Valley Farm",
            phone="01179 123456",
            business_address="1 Farm Lane, Bristol",
            postcode="BS1 4DJ",
            is_verified=True,
        )

        self.category = Category.objects.create(
            name="Vegetables",
            slug="vegetables",
        )

    def create_product(self, **overrides):
        data = {
            "producer": self.producer,
            "category": self.category,
            "name": "Organic Tomatoes",
            "description": "Fresh locally grown tomatoes.",
            "price": Decimal("3.50"),
            "unit": Product.Unit.KILOGRAM,
            "stock_quantity": Decimal("20.00"),
            "low_stock_threshold": Decimal("5.00"),
            "availability_status": Product.Availability.IN_SEASON,
            "allergen_information": "No common allergens",
            "organic_certified": True,
        }

        data.update(overrides)

        return Product.objects.create(**data)

    def test_available_product_is_available_now(self):
        product = self.create_product()

        self.assertTrue(product.is_available_now)

    def test_out_of_season_product_is_not_available(self):
        product = self.create_product(
            availability_status=Product.Availability.OUT_OF_SEASON,
        )

        self.assertFalse(product.is_available_now)

    def test_out_of_stock_product_is_not_available(self):
        product = self.create_product(
            stock_quantity=Decimal("0.00"),
        )

        self.assertFalse(product.is_available_now)

    def test_low_stock_threshold_is_detected(self):
        product = self.create_product(
            stock_quantity=Decimal("4.00"),
            low_stock_threshold=Decimal("5.00"),
        )

        self.assertTrue(product.is_low_stock)

    def test_invalid_seasonal_date_range_is_rejected(self):
        today = timezone.localdate()

        product = Product(
            producer=self.producer,
            category=self.category,
            name="Seasonal Strawberries",
            description="Summer strawberries.",
            price=Decimal("4.00"),
            unit=Product.Unit.KILOGRAM,
            stock_quantity=Decimal("10.00"),
            availability_status=Product.Availability.IN_SEASON,
            available_from=today + timedelta(days=10),
            available_until=today,
            allergen_information="No common allergens",
        )

        with self.assertRaises(ValidationError):
            product.full_clean()

    def test_farm_origin_uses_producer_details(self):
        product = self.create_product()

        self.assertEqual(
            product.farm_origin,
            "Bristol Valley Farm, BS1 4DJ",
        )
