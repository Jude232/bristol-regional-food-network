from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomerProfile, ProducerProfile, User
from marketplace.models import Category, Product

from .models import (
    Order,
    OrderItem,
    ProducerOrder,
    ProducerOrderStatusHistory,
    UserNotification,
)


class ProducerOrderManagementTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="customer-orders@example.test",
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
            email="farm-orders@example.test",
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
            email="other-orders@example.test",
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

        category = Category.objects.create(
            name="Vegetables",
            slug="vegetables",
        )

        self.product = Product.objects.create(
            producer=self.producer,
            category=category,
            name="Organic Carrots",
            description="Fresh carrots.",
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

        self.other_product = Product.objects.create(
            producer=self.other_producer,
            category=category,
            name="Fresh Potatoes",
            description="Fresh potatoes.",
            price=Decimal("2.00"),
            unit=Product.Unit.KILOGRAM,
            stock_quantity=Decimal("20.00"),
            low_stock_threshold=Decimal("5.00"),
            availability_status=Product.Availability.IN_SEASON,
            allergen_information="No common allergens",
            organic_certified=False,
            is_active=True,
        )

        self.order = Order(
            customer=self.customer,
            delivery_address="45 Park Street, Bristol",
            delivery_postcode="BS1 5JG",
            special_instructions="Leave at reception.",
            payment_status=Order.PaymentStatus.PAID,
        )

        self.order.set_financial_totals(
            Decimal("9.00")
        )

        self.order.save()

        self.producer_order = ProducerOrder(
            order=self.order,
            producer=self.producer,
            delivery_at=(
                timezone.now()
                + timedelta(hours=72)
            ),
        )

        self.producer_order.set_financial_totals(
            Decimal("5.00")
        )

        self.producer_order.full_clean()
        self.producer_order.save()

        item = OrderItem(
            producer_order=self.producer_order,
            product=self.product,
            quantity=Decimal("2.00"),
        )

        item.capture_product_snapshot()
        item.full_clean()
        item.save()

        self.other_producer_order = ProducerOrder(
            order=self.order,
            producer=self.other_producer,
            delivery_at=(
                timezone.now()
                + timedelta(hours=96)
            ),
        )

        self.other_producer_order.set_financial_totals(
            Decimal("4.00")
        )

        self.other_producer_order.full_clean()
        self.other_producer_order.save()

        other_item = OrderItem(
            producer_order=self.other_producer_order,
            product=self.other_product,
            quantity=Decimal("2.00"),
        )

        other_item.capture_product_snapshot()
        other_item.full_clean()
        other_item.save()

    def test_tc009_producer_sees_only_their_order_items(self):
        self.client.force_login(
            self.producer_user
        )

        response = self.client.get(
            reverse("orders:producer_order_list")
        )

        self.assertContains(
            response,
            "Organic Carrots",
        )

        self.assertNotContains(
            response,
            "Fresh Potatoes",
        )

        self.assertContains(
            response,
            "Robert Johnson",
        )

    def test_producer_cannot_view_another_producers_order(self):
        self.client.force_login(
            self.producer_user
        )

        response = self.client.get(
            reverse(
                "orders:producer_order_detail",
                args=[self.other_producer_order.id],
            )
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_tc010_status_progression_creates_audit_record(self):
        self.client.force_login(
            self.producer_user
        )

        response = self.client.post(
            reverse(
                "orders:producer_order_status_update",
                args=[self.producer_order.id],
            ),
            {
                "next_status": ProducerOrder.Status.CONFIRMED,
                "note": (
                    "Products will be prepared by delivery date."
                ),
            },
        )

        self.assertRedirects(
            response,
            reverse(
                "orders:producer_order_detail",
                args=[self.producer_order.id],
            ),
        )

        self.producer_order.refresh_from_db()
        self.order.refresh_from_db()

        self.assertEqual(
            self.producer_order.status,
            ProducerOrder.Status.CONFIRMED,
        )

        self.assertEqual(
            self.order.status,
            Order.Status.PROCESSING,
        )

        history = ProducerOrderStatusHistory.objects.get(
            producer_order=self.producer_order
        )

        self.assertEqual(
            history.previous_status,
            ProducerOrder.Status.PENDING,
        )

        self.assertEqual(
            history.new_status,
            ProducerOrder.Status.CONFIRMED,
        )

        self.assertEqual(
            history.changed_by,
            self.producer_user,
        )

    def test_status_stages_cannot_be_skipped(self):
        self.client.force_login(
            self.producer_user
        )

        self.client.post(
            reverse(
                "orders:producer_order_status_update",
                args=[self.producer_order.id],
            ),
            {
                "next_status": ProducerOrder.Status.READY,
                "note": "",
            },
        )

        self.producer_order.refresh_from_db()

        self.assertEqual(
            self.producer_order.status,
            ProducerOrder.Status.PENDING,
        )

        self.assertFalse(
            ProducerOrderStatusHistory.objects.filter(
                producer_order=self.producer_order
            ).exists()
        )

    def test_customer_receives_status_notification(self):
        self.client.force_login(
            self.producer_user
        )

        self.client.post(
            reverse(
                "orders:producer_order_status_update",
                args=[self.producer_order.id],
            ),
            {
                "next_status": ProducerOrder.Status.CONFIRMED,
                "note": "Order confirmed.",
            },
        )

        notification = UserNotification.objects.get(
            recipient=self.customer
        )

        self.assertIn(
            self.order.order_number,
            notification.title,
        )

        self.assertIn(
            "Confirmed",
            notification.message,
        )

        self.client.force_login(
            self.customer
        )

        response = self.client.get(
            reverse("orders:notification_list")
        )

        self.assertContains(
            response,
            self.order.order_number,
        )

    def test_customer_order_view_shows_updated_producer_status(self):
        self.producer_order.status = (
            ProducerOrder.Status.READY
        )

        self.producer_order.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        self.client.force_login(
            self.customer
        )

        response = self.client.get(
            reverse(
                "orders:order_detail",
                args=[self.order.id],
            )
        )

        self.assertContains(
            response,
            "Ready for Collection/Delivery",
        )
