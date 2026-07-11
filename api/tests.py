from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import (
    CustomerProfile,
    ProducerProfile,
    User,
)
from marketplace.models import Category, Product
from orders.models import Order, ProducerOrder


class MarketplaceAPITests(APITestCase):
    def setUp(self):
        self.producer_user = User.objects.create_user(
            email="api-producer@example.test",
            password="ProducerTest2026!",
            first_name="Jane",
            last_name="Smith",
            role=User.Role.PRODUCER,
        )

        self.producer = ProducerProfile.objects.create(
            user=self.producer_user,
            business_name="Bristol Valley Farm",
            phone="01179 123456",
            business_address="1 Farm Lane, Bristol",
            postcode="BS1 4DJ",
            is_verified=True,
        )

        self.other_producer_user = User.objects.create_user(
            email="api-other-producer@example.test",
            password="OtherProducer2026!",
            first_name="Helen",
            last_name="Brown",
            role=User.Role.PRODUCER,
        )

        self.other_producer = ProducerProfile.objects.create(
            user=self.other_producer_user,
            business_name="Hillside Dairy",
            phone="01179 333444",
            business_address="2 Dairy Lane, Bristol",
            postcode="BS2 2AA",
            is_verified=True,
        )

        self.customer = User.objects.create_user(
            email="api-customer@example.test",
            password="CustomerTest2026!",
            first_name="Robert",
            last_name="Johnson",
            role=User.Role.CUSTOMER,
        )

        CustomerProfile.objects.create(
            user=self.customer,
            phone="07700 900123",
            delivery_address="45 Park Street, Bristol",
            postcode="BS1 5JG",
            accepted_terms=True,
        )

        self.other_customer = User.objects.create_user(
            email="api-other-customer@example.test",
            password="OtherCustomer2026!",
            first_name="Alice",
            last_name="Green",
            role=User.Role.CUSTOMER,
        )

        CustomerProfile.objects.create(
            user=self.other_customer,
            phone="07700 900456",
            delivery_address="20 Queen Square, Bristol",
            postcode="BS1 4ND",
            accepted_terms=True,
        )

        self.category = Category.objects.create(
            name="Vegetables",
            slug="vegetables",
            description="Fresh local vegetables.",
        )

        self.product = Product.objects.create(
            producer=self.producer,
            category=self.category,
            name="Organic Carrots",
            description="Fresh organic carrots.",
            price=Decimal("2.50"),
            unit=Product.Unit.KILOGRAM,
            stock_quantity=Decimal("20.00"),
            low_stock_threshold=Decimal("5.00"),
            availability_status=(
                Product.Availability.IN_SEASON
            ),
            allergen_information="No common allergens",
            organic_certified=True,
            organic_certification_details=(
                "Test organic certification"
            ),
            is_active=True,
        )

        self.other_product = Product.objects.create(
            producer=self.other_producer,
            category=self.category,
            name="Fresh Potatoes",
            description="Fresh local potatoes.",
            price=Decimal("2.00"),
            unit=Product.Unit.KILOGRAM,
            stock_quantity=Decimal("20.00"),
            low_stock_threshold=Decimal("5.00"),
            availability_status=(
                Product.Availability.YEAR_ROUND
            ),
            allergen_information="No common allergens",
            organic_certified=False,
            is_active=True,
        )

    def create_order(self, customer):
        order = Order(
            customer=customer,
            delivery_address="45 Park Street, Bristol",
            delivery_postcode="BS1 5JG",
            payment_status=Order.PaymentStatus.PAID,
        )

        order.set_financial_totals(
            Decimal("10.00")
        )

        order.save()

        return order

    def create_producer_order(
        self,
        *,
        order,
        producer,
        subtotal=Decimal("5.00"),
    ):
        producer_order = ProducerOrder(
            order=order,
            producer=producer,
            delivery_at=(
                timezone.now()
                + timedelta(hours=72)
            ),
        )

        producer_order.set_financial_totals(
            subtotal
        )

        producer_order.full_clean()
        producer_order.save()

        return producer_order

    def test_public_category_and_product_endpoints(self):
        category_response = self.client.get(
            reverse("api:category-list")
        )

        product_response = self.client.get(
            reverse("api:public-product-list")
        )

        self.assertEqual(
            category_response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            product_response.status_code,
            status.HTTP_200_OK,
        )

        product_names = {
            product["name"]
            for product in product_response.data
        }

        self.assertIn(
            "Organic Carrots",
            product_names,
        )

        self.assertIn(
            "Fresh Potatoes",
            product_names,
        )

    def test_public_api_hides_unavailable_products(self):
        hidden_product = Product.objects.create(
            producer=self.producer,
            category=self.category,
            name="Unavailable Beetroot",
            description="Currently unavailable.",
            price=Decimal("2.25"),
            unit=Product.Unit.KILOGRAM,
            stock_quantity=Decimal("0.00"),
            low_stock_threshold=Decimal("5.00"),
            availability_status=(
                Product.Availability.UNAVAILABLE
            ),
            allergen_information="No common allergens",
            organic_certified=False,
            is_active=True,
        )

        response = self.client.get(
            reverse("api:public-product-list")
        )

        product_ids = {
            product["id"]
            for product in response.data
        }

        self.assertNotIn(
            hidden_product.id,
            product_ids,
        )

    def test_anonymous_user_cannot_access_producer_api(self):
        response = self.client.get(
            reverse("api:producer-product-list")
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_producer_can_create_owned_product(self):
        self.client.force_authenticate(
            self.producer_user
        )

        response = self.client.post(
            reverse("api:producer-product-list"),
            {
                "category": self.category.id,
                "name": "Organic Cabbage",
                "description": "Fresh local cabbage.",
                "price": "1.80",
                "unit": Product.Unit.ITEM,
                "stock_quantity": "30.00",
                "low_stock_threshold": "5.00",
                "availability_status": (
                    Product.Availability.IN_SEASON
                ),
                "available_from": None,
                "available_until": None,
                "harvest_date": None,
                "best_before_date": None,
                "allergen_information": (
                    "No common allergens"
                ),
                "organic_certified": True,
                "organic_certification_details": (
                    "Test organic certification"
                ),
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        product = Product.objects.get(
            name="Organic Cabbage"
        )

        self.assertEqual(
            product.producer,
            self.producer,
        )

    def test_customer_cannot_create_producer_product(self):
        self.client.force_authenticate(
            self.customer
        )

        response = self.client.post(
            reverse("api:producer-product-list"),
            {
                "category": self.category.id,
                "name": "Unauthorised Product",
                "description": "Should not be created.",
                "price": "1.00",
                "unit": Product.Unit.ITEM,
                "stock_quantity": "1.00",
                "low_stock_threshold": "1.00",
                "availability_status": (
                    Product.Availability.IN_SEASON
                ),
                "allergen_information": (
                    "No common allergens"
                ),
                "organic_certified": False,
                "organic_certification_details": "",
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.assertFalse(
            Product.objects.filter(
                name="Unauthorised Product"
            ).exists()
        )

    def test_producer_api_isolates_product_ownership(self):
        self.client.force_authenticate(
            self.producer_user
        )

        list_response = self.client.get(
            reverse("api:producer-product-list")
        )

        product_ids = {
            product["id"]
            for product in list_response.data
        }

        self.assertIn(
            self.product.id,
            product_ids,
        )

        self.assertNotIn(
            self.other_product.id,
            product_ids,
        )

        update_response = self.client.patch(
            reverse(
                "api:producer-product-detail",
                args=[self.other_product.id],
            ),
            {
                "price": "99.00",
            },
            format="json",
        )

        self.assertEqual(
            update_response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

        self.other_product.refresh_from_db()

        self.assertEqual(
            self.other_product.price,
            Decimal("2.00"),
        )

    def test_customer_order_api_returns_only_owned_orders(self):
        own_order = self.create_order(
            self.customer
        )

        other_order = self.create_order(
            self.other_customer
        )

        self.client.force_authenticate(
            self.customer
        )

        response = self.client.get(
            reverse("api:customer-order-list")
        )

        order_numbers = {
            order["order_number"]
            for order in response.data
        }

        self.assertIn(
            own_order.order_number,
            order_numbers,
        )

        self.assertNotIn(
            other_order.order_number,
            order_numbers,
        )

    def test_producer_order_api_returns_only_owned_sections(self):
        order = self.create_order(
            self.customer
        )

        own_section = self.create_producer_order(
            order=order,
            producer=self.producer,
            subtotal=Decimal("5.00"),
        )

        other_section = self.create_producer_order(
            order=order,
            producer=self.other_producer,
            subtotal=Decimal("5.00"),
        )

        self.client.force_authenticate(
            self.producer_user
        )

        response = self.client.get(
            reverse("api:producer-order-list")
        )

        producer_order_ids = {
            producer_order["id"]
            for producer_order in response.data
        }

        self.assertIn(
            own_section.id,
            producer_order_ids,
        )

        self.assertNotIn(
            other_section.id,
            producer_order_ids,
        )
