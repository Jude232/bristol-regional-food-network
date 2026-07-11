from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomerProfile, ProducerProfile, User
from marketplace.models import Category, Product


class MarketplaceTestDataMixin:
    def setUp(self):
        self.producer_user = User.objects.create_user(
            email="producer@example.test",
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
            email="other-producer@example.test",
            password="OtherProducer2026!",
            first_name="Alex",
            last_name="Green",
            role=User.Role.PRODUCER,
        )

        self.other_producer = ProducerProfile.objects.create(
            user=self.other_producer_user,
            business_name="Hillside Dairy",
            phone="01179 222333",
            business_address="2 Dairy Lane, Bristol",
            postcode="BS2 2AA",
            is_verified=True,
        )

        self.customer_user = User.objects.create_user(
            email="customer@example.test",
            password="CustomerTest2026!",
            first_name="Robert",
            last_name="Johnson",
            role=User.Role.CUSTOMER,
        )

        CustomerProfile.objects.create(
            user=self.customer_user,
            phone="07700 900123",
            delivery_address="45 Park Street, Bristol",
            postcode="BS1 5JG",
            accepted_terms=True,
        )

        self.vegetables = Category.objects.create(
            name="Vegetables",
            slug="vegetables",
        )

        self.dairy = Category.objects.create(
            name="Dairy & Eggs",
            slug="dairy-eggs",
        )

    def create_product(self, **overrides):
        data = {
            "producer": self.producer,
            "category": self.vegetables,
            "name": "Organic Tomatoes",
            "description": "Fresh locally grown organic tomatoes.",
            "price": Decimal("3.50"),
            "unit": Product.Unit.KILOGRAM,
            "stock_quantity": Decimal("20.00"),
            "low_stock_threshold": Decimal("5.00"),
            "availability_status": Product.Availability.IN_SEASON,
            "allergen_information": "No common allergens",
            "organic_certified": True,
            "organic_certification_details": "Certified test producer",
            "is_active": True,
        }

        data.update(overrides)

        return Product.objects.create(**data)


class ProductModelTests(
    MarketplaceTestDataMixin,
    TestCase,
):
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
            category=self.vegetables,
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


class ProductBrowsingTests(
    MarketplaceTestDataMixin,
    TestCase,
):
    def test_tc004_category_filter_displays_matching_products(self):
        vegetables_product = self.create_product()

        dairy_product = self.create_product(
            name="Fresh Milk",
            description="Fresh whole milk.",
            category=self.dairy,
            organic_certified=False,
            organic_certification_details="",
        )

        response = self.client.get(
            reverse("marketplace:product_list"),
            {
                "category": "vegetables",
            },
        )

        self.assertContains(
            response,
            vegetables_product.name,
        )

        self.assertNotContains(
            response,
            dairy_product.name,
        )

    def test_tc005_search_matches_product_description(self):
        self.create_product(
            name="Red Salad Produce",
            description="Fresh organic tomatoes for salads.",
        )

        response = self.client.get(
            reverse("marketplace:product_list"),
            {
                "q": "tomatoes",
            },
        )

        self.assertContains(
            response,
            "Red Salad Produce",
        )

    def test_tc014_organic_filter_excludes_non_organic_products(self):
        organic_product = self.create_product()

        non_organic_product = self.create_product(
            name="Standard Carrots",
            organic_certified=False,
            organic_certification_details="",
        )

        response = self.client.get(
            reverse("marketplace:product_list"),
            {
                "organic": "true",
            },
        )

        self.assertContains(
            response,
            organic_product.name,
        )

        self.assertNotContains(
            response,
            non_organic_product.name,
        )

    def test_unavailable_products_are_hidden_from_customers(self):
        visible_product = self.create_product()

        hidden_product = self.create_product(
            name="Out of Season Strawberries",
            availability_status=Product.Availability.OUT_OF_SEASON,
        )

        response = self.client.get(
            reverse("marketplace:product_list")
        )

        self.assertContains(
            response,
            visible_product.name,
        )

        self.assertNotContains(
            response,
            hidden_product.name,
        )

    def test_tc015_allergen_information_is_displayed(self):
        product = self.create_product(
            name="Walnut Bread",
            category=self.dairy,
            allergen_information=(
                "Contains wheat (gluten) and walnuts"
            ),
        )

        response = self.client.get(
            reverse(
                "marketplace:product_detail",
                args=[product.id],
            )
        )

        self.assertContains(
            response,
            "Contains wheat (gluten) and walnuts",
        )


class ProducerProductManagementTests(
    MarketplaceTestDataMixin,
    TestCase,
):
    def test_tc003_producer_can_create_owned_product(self):
        self.client.force_login(
            self.producer_user
        )

        response = self.client.post(
            reverse("marketplace:product_create"),
            {
                "category": self.dairy.id,
                "name": "Organic Free Range Eggs",
                "description": (
                    "Fresh organic eggs from free-range hens."
                ),
                "price": "3.50",
                "unit": Product.Unit.DOZEN,
                "stock_quantity": "50.00",
                "low_stock_threshold": "10.00",
                "availability_status": (
                    Product.Availability.IN_SEASON
                ),
                "available_from": "",
                "available_until": "",
                "harvest_date": timezone.localdate().isoformat(),
                "best_before_date": (
                    timezone.localdate()
                    + timedelta(days=14)
                ).isoformat(),
                "allergen_information": "Contains eggs",
                "organic_certified": "on",
                "organic_certification_details": (
                    "Certified organic test record"
                ),
                "is_active": "on",
            },
        )

        self.assertRedirects(
            response,
            reverse(
                "marketplace:producer_product_list"
            ),
        )

        product = Product.objects.get(
            name="Organic Free Range Eggs"
        )

        self.assertEqual(
            product.producer,
            self.producer,
        )

        self.assertEqual(
            product.stock_quantity,
            Decimal("50.00"),
        )

    def test_customer_cannot_access_product_creation(self):
        self.client.force_login(
            self.customer_user
        )

        response = self.client.get(
            reverse("marketplace:product_create")
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_producer_cannot_edit_another_producers_product(self):
        other_product = self.create_product(
            producer=self.other_producer,
            name="Hillside Milk",
            category=self.dairy,
            organic_certified=False,
            organic_certification_details="",
        )

        self.client.force_login(
            self.producer_user
        )

        response = self.client.get(
            reverse(
                "marketplace:product_update",
                args=[other_product.id],
            )
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_tc011_producer_can_update_stock(self):
        product = self.create_product(
            stock_quantity=Decimal("20.00"),
        )

        self.client.force_login(
            self.producer_user
        )

        response = self.client.post(
            reverse(
                "marketplace:product_update",
                args=[product.id],
            ),
            {
                "category": self.vegetables.id,
                "name": product.name,
                "description": product.description,
                "price": str(product.price),
                "unit": product.unit,
                "stock_quantity": "35.00",
                "low_stock_threshold": "5.00",
                "availability_status": (
                    Product.Availability.IN_SEASON
                ),
                "available_from": "",
                "available_until": "",
                "harvest_date": "",
                "best_before_date": "",
                "allergen_information": (
                    product.allergen_information
                ),
                "organic_certified": "on",
                "organic_certification_details": (
                    product.organic_certification_details
                ),
                "is_active": "on",
            },
        )

        self.assertRedirects(
            response,
            reverse(
                "marketplace:producer_product_list"
            ),
        )

        product.refresh_from_db()

        self.assertEqual(
            product.stock_quantity,
            Decimal("35.00"),
        )
