from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import ProducerProfile, User

from .models import Order, ProducerOrder


class CheckoutModelTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="checkout-customer@example.test",
            password="CustomerTest2026!",
            role=User.Role.CUSTOMER,
        )

        producer_user = User.objects.create_user(
            email="checkout-producer@example.test",
            password="ProducerTest2026!",
            role=User.Role.PRODUCER,
        )

        self.producer = ProducerProfile.objects.create(
            user=producer_user,
            business_name="Checkout Test Farm",
            phone="01179 100200",
            business_address="1 Test Farm Road, Bristol",
            postcode="BS1 1AA",
            is_verified=True,
        )

    def create_order(self):
        order = Order(
            customer=self.customer,
            delivery_address="45 Park Street, Bristol",
            delivery_postcode="BS1 5JG",
        )

        order.set_financial_totals(
            Decimal("100.00")
        )

        order.save()

        return order

    def test_order_calculates_five_percent_commission(self):
        order = self.create_order()

        self.assertEqual(
            order.subtotal,
            Decimal("100.00"),
        )

        self.assertEqual(
            order.commission_amount,
            Decimal("5.00"),
        )

        self.assertEqual(
            order.producer_payment_total,
            Decimal("95.00"),
        )

        self.assertEqual(
            order.total_amount,
            Decimal("100.00"),
        )

    def test_producer_allocation_is_calculated_separately(self):
        order = self.create_order()

        producer_order = ProducerOrder(
            order=order,
            producer=self.producer,
            delivery_at=(
                timezone.now()
                + timedelta(hours=72)
            ),
        )

        producer_order.set_financial_totals(
            Decimal("80.00")
        )

        producer_order.full_clean()
        producer_order.save()

        self.assertEqual(
            producer_order.commission_amount,
            Decimal("4.00"),
        )

        self.assertEqual(
            producer_order.producer_payment,
            Decimal("76.00"),
        )

    def test_delivery_with_less_than_48_hours_is_rejected(self):
        order = self.create_order()

        producer_order = ProducerOrder(
            order=order,
            producer=self.producer,
            delivery_at=(
                timezone.now()
                + timedelta(hours=24)
            ),
        )

        producer_order.set_financial_totals(
            Decimal("50.00")
        )

        with self.assertRaises(ValidationError):
            producer_order.full_clean()

    def test_order_numbers_are_automatically_unique(self):
        first_order = self.create_order()
        second_order = self.create_order()

        self.assertNotEqual(
            first_order.order_number,
            second_order.order_number,
        )
