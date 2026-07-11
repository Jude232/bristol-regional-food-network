from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomerProfile, ProducerProfile, User
from marketplace.models import Category, Product

from .models import (
    Cart,
    CartItem,
    Order,
    PaymentTransaction,
    ProducerOrder,
)


class CheckoutFlowTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="checkout-customer@example.test",
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

        producer_user = User.objects.create_user(
            email="farm@example.test",
            password="ProducerTest2026!",
            first_name="Jane",
            last_name="Smith",
            role=User.Role.PRODUCER,
        )

        self.farm = ProducerProfile.objects.create(
            user=producer_user,
            business_name="Bristol Valley Farm",
            phone="01179 123456",
            business_address="1 Farm Lane, Bristol",
            postcode="BS1 4DJ",
            is_verified=True,
        )

        dairy_user = User.objects.create_user(
            email="dairy@example.test",
            password="DairyTest2026!",
            first_name="Helen",
            last_name="Brown",
            role=User.Role.PRODUCER,
        )

        self.dairy = ProducerProfile.objects.create(
            user=dairy_user,
            business_name="Hillside Dairy",
            phone="01179 999888",
            business_address="2 Dairy Lane, Bristol",
            postcode="BS2 2AA",
            is_verified=True,
        )

        vegetables = Category.objects.create(
            name="Vegetables",
            slug="vegetables",
        )

        dairy_category = Category.objects.create(
            name="Dairy & Eggs",
            slug="dairy-eggs",
        )

        self.carrots = Product.objects.create(
            producer=self.farm,
            category=vegetables,
            name="Organic Carrots",
            description="Fresh organic carrots.",
            price=Decimal("2.50"),
            unit=Product.Unit.KILOGRAM,
            stock_quantity=Decimal("10.00"),
            low_stock_threshold=Decimal("2.00"),
            availability_status=Product.Availability.IN_SEASON,
            allergen_information="No common allergens",
            organic_certified=True,
            organic_certification_details="Test certification",
            is_active=True,
        )

        self.milk = Product.objects.create(
            producer=self.dairy,
            category=dairy_category,
            name="Fresh Milk",
            description="Fresh whole milk.",
            price=Decimal("1.80"),
            unit=Product.Unit.LITRE,
            stock_quantity=Decimal("20.00"),
            low_stock_threshold=Decimal("3.00"),
            availability_status=Product.Availability.YEAR_ROUND,
            allergen_information="Contains milk",
            organic_certified=False,
            is_active=True,
        )

        self.cart = Cart.objects.create(
            customer=self.customer
        )

        self.client.force_login(
            self.customer
        )

    def checkout_data(
        self,
        *,
        payment_token="tok_success",
        hours_from_now=72,
    ):
        delivery_at = timezone.localtime(
            timezone.now()
            + timedelta(hours=hours_from_now)
        ).replace(
            second=0,
            microsecond=0,
        )

        return {
            "delivery_address": "45 Park Street, Bristol",
            "delivery_postcode": "BS1 5JG",
            "delivery_at": delivery_at.strftime(
                "%Y-%m-%dT%H:%M"
            ),
            "special_instructions": "Leave at reception.",
            "payment_token": payment_token,
            "card_last_four": "4242",
        }

    def test_tc007_single_producer_checkout_succeeds(self):
        CartItem.objects.create(
            cart=self.cart,
            product=self.carrots,
            quantity=Decimal("2.00"),
        )

        response = self.client.post(
            reverse("orders:checkout"),
            self.checkout_data(),
        )

        order = Order.objects.get(
            customer=self.customer
        )

        self.assertRedirects(
            response,
            reverse(
                "orders:order_detail",
                args=[order.id],
            ),
        )

        self.assertEqual(
            order.subtotal,
            Decimal("5.00"),
        )

        self.assertEqual(
            order.commission_amount,
            Decimal("0.25"),
        )

        self.assertEqual(
            order.producer_payment_total,
            Decimal("4.75"),
        )

        self.assertEqual(
            order.payment_status,
            Order.PaymentStatus.PAID,
        )

        self.assertEqual(
            order.producer_orders.count(),
            1,
        )

        self.assertTrue(
            PaymentTransaction.objects.filter(
                order=order,
                status=(
                    PaymentTransaction.Status.SUCCEEDED
                ),
            ).exists()
        )

        self.carrots.refresh_from_db()

        self.assertEqual(
            self.carrots.stock_quantity,
            Decimal("8.00"),
        )

        self.assertFalse(
            self.cart.items.exists()
        )

    def test_tc008_multi_producer_checkout_creates_suborders(self):
        CartItem.objects.create(
            cart=self.cart,
            product=self.carrots,
            quantity=Decimal("2.00"),
        )

        CartItem.objects.create(
            cart=self.cart,
            product=self.milk,
            quantity=Decimal("3.00"),
        )

        self.client.post(
            reverse("orders:checkout"),
            self.checkout_data(),
        )

        order = Order.objects.get(
            customer=self.customer
        )

        self.assertEqual(
            order.total_amount,
            Decimal("10.40"),
        )

        self.assertEqual(
            order.commission_amount,
            Decimal("0.52"),
        )

        self.assertEqual(
            order.producer_orders.count(),
            2,
        )

        farm_order = ProducerOrder.objects.get(
            order=order,
            producer=self.farm,
        )

        dairy_order = ProducerOrder.objects.get(
            order=order,
            producer=self.dairy,
        )

        self.assertEqual(
            farm_order.subtotal,
            Decimal("5.00"),
        )

        self.assertEqual(
            farm_order.producer_payment,
            Decimal("4.75"),
        )

        self.assertEqual(
            dairy_order.subtotal,
            Decimal("5.40"),
        )

        self.assertEqual(
            dairy_order.producer_payment,
            Decimal("5.13"),
        )

        self.assertEqual(
            farm_order.items.count(),
            1,
        )

        self.assertEqual(
            dairy_order.items.count(),
            1,
        )

    def test_declined_payment_does_not_create_order(self):
        CartItem.objects.create(
            cart=self.cart,
            product=self.carrots,
            quantity=Decimal("2.00"),
        )

        response = self.client.post(
            reverse("orders:checkout"),
            self.checkout_data(
                payment_token="tok_declined"
            ),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "MockPay declined",
        )

        self.assertFalse(
            Order.objects.filter(
                customer=self.customer
            ).exists()
        )

        self.carrots.refresh_from_db()

        self.assertEqual(
            self.carrots.stock_quantity,
            Decimal("10.00"),
        )

        self.assertTrue(
            self.cart.items.exists()
        )

    def test_delivery_less_than_48_hours_is_rejected(self):
        CartItem.objects.create(
            cart=self.cart,
            product=self.carrots,
            quantity=Decimal("1.00"),
        )

        response = self.client.post(
            reverse("orders:checkout"),
            self.checkout_data(
                hours_from_now=24
            ),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "at least 48 hours",
        )

        self.assertFalse(
            Order.objects.exists()
        )

    def test_empty_cart_cannot_checkout(self):
        response = self.client.get(
            reverse("orders:checkout")
        )

        self.assertRedirects(
            response,
            reverse("orders:cart_detail"),
        )

        self.assertFalse(
            Order.objects.exists()
        )
