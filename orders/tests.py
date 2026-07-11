from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import CustomerProfile, ProducerProfile, User
from marketplace.models import Category, Product

from .models import Cart, CartItem


class CartTestDataMixin:
    def setUp(self):
        self.customer = User.objects.create_user(
            email="customer@example.test",
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
            email="dairy@example.test",
            password="DairyTest2026!",
            first_name="Helen",
            last_name="Brown",
            role=User.Role.PRODUCER,
        )

        self.other_producer = ProducerProfile.objects.create(
            user=self.other_producer_user,
            business_name="Hillside Dairy",
            phone="01179 888999",
            business_address="2 Dairy Road, Bristol",
            postcode="BS2 2AA",
            is_verified=True,
        )

        self.vegetables = Category.objects.create(
            name="Vegetables",
            slug="vegetables",
        )

        self.dairy = Category.objects.create(
            name="Dairy & Eggs",
            slug="dairy-eggs",
        )

        self.carrots = Product.objects.create(
            producer=self.producer,
            category=self.vegetables,
            name="Organic Carrots",
            description="Fresh organic carrots.",
            price=Decimal("2.50"),
            unit=Product.Unit.KILOGRAM,
            stock_quantity=Decimal("20.00"),
            low_stock_threshold=Decimal("5.00"),
            availability_status=Product.Availability.IN_SEASON,
            allergen_information="No common allergens",
            organic_certified=True,
            organic_certification_details="Test certification",
            is_active=True,
        )

        self.milk = Product.objects.create(
            producer=self.other_producer,
            category=self.dairy,
            name="Fresh Milk",
            description="Fresh whole milk.",
            price=Decimal("1.80"),
            unit=Product.Unit.LITRE,
            stock_quantity=Decimal("30.00"),
            low_stock_threshold=Decimal("5.00"),
            availability_status=Product.Availability.YEAR_ROUND,
            allergen_information="Contains milk",
            organic_certified=False,
            is_active=True,
        )

        self.client.force_login(self.customer)


class CartTests(
    CartTestDataMixin,
    TestCase,
):
    def test_tc006_customer_can_add_product_to_cart(self):
        response = self.client.post(
            reverse(
                "orders:add_to_cart",
                args=[self.carrots.id],
            ),
            {
                "quantity": "2.00",
            },
        )

        self.assertRedirects(
            response,
            reverse("orders:cart_detail"),
        )

        cart_item = CartItem.objects.get(
            cart__customer=self.customer,
            product=self.carrots,
        )

        self.assertEqual(
            cart_item.quantity,
            Decimal("2.00"),
        )

        self.assertEqual(
            cart_item.line_total,
            Decimal("5.00"),
        )

    def test_adding_existing_product_increases_quantity(self):
        cart = Cart.objects.create(
            customer=self.customer
        )

        CartItem.objects.create(
            cart=cart,
            product=self.carrots,
            quantity=Decimal("2.00"),
        )

        self.client.post(
            reverse(
                "orders:add_to_cart",
                args=[self.carrots.id],
            ),
            {
                "quantity": "3.00",
            },
        )

        cart_item = CartItem.objects.get(
            cart=cart,
            product=self.carrots,
        )

        self.assertEqual(
            cart_item.quantity,
            Decimal("5.00"),
        )

    def test_customer_can_update_cart_quantity(self):
        cart = Cart.objects.create(
            customer=self.customer
        )

        item = CartItem.objects.create(
            cart=cart,
            product=self.carrots,
            quantity=Decimal("2.00"),
        )

        response = self.client.post(
            reverse(
                "orders:update_cart_item",
                args=[item.id],
            ),
            {
                "quantity": "3.00",
            },
        )

        self.assertRedirects(
            response,
            reverse("orders:cart_detail"),
        )

        item.refresh_from_db()

        self.assertEqual(
            item.quantity,
            Decimal("3.00"),
        )

        self.assertEqual(
            item.line_total,
            Decimal("7.50"),
        )

    def test_customer_can_remove_cart_item(self):
        cart = Cart.objects.create(
            customer=self.customer
        )

        item = CartItem.objects.create(
            cart=cart,
            product=self.carrots,
            quantity=Decimal("2.00"),
        )

        response = self.client.post(
            reverse(
                "orders:remove_cart_item",
                args=[item.id],
            )
        )

        self.assertRedirects(
            response,
            reverse("orders:cart_detail"),
        )

        self.assertFalse(
            CartItem.objects.filter(
                pk=item.id
            ).exists()
        )

    def test_quantity_cannot_exceed_stock(self):
        self.client.post(
            reverse(
                "orders:add_to_cart",
                args=[self.carrots.id],
            ),
            {
                "quantity": "21.00",
            },
        )

        self.assertFalse(
            CartItem.objects.filter(
                cart__customer=self.customer,
                product=self.carrots,
            ).exists()
        )

    def test_cart_groups_products_by_producer(self):
        cart = Cart.objects.create(
            customer=self.customer
        )

        CartItem.objects.create(
            cart=cart,
            product=self.carrots,
            quantity=Decimal("2.00"),
        )

        CartItem.objects.create(
            cart=cart,
            product=self.milk,
            quantity=Decimal("3.00"),
        )

        response = self.client.get(
            reverse("orders:cart_detail")
        )

        self.assertContains(
            response,
            "Bristol Valley Farm",
        )

        self.assertContains(
            response,
            "Hillside Dairy",
        )

        self.assertContains(
            response,
            "Organic Carrots",
        )

        self.assertContains(
            response,
            "Fresh Milk",
        )

        self.assertEqual(
            cart.total,
            Decimal("10.40"),
        )

    def test_producer_cannot_access_customer_cart(self):
        self.client.force_login(
            self.producer_user
        )

        response = self.client.get(
            reverse("orders:cart_detail")
        )

        self.assertEqual(
            response.status_code,
            403,
        )
