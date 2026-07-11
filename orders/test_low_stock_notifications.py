from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.models import CustomerProfile, ProducerProfile, User
from marketplace.models import Category, Product

from .models import (
    Cart,
    CartItem,
    UserNotification,
)
from .notification_services import (
    sync_low_stock_notification,
)
from .services import create_order_from_cart


class LowStockNotificationTests(TestCase):
    def setUp(self):
        self.producer_user = User.objects.create_user(
            email="stock-producer@example.test",
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

        self.customer = User.objects.create_user(
            email="stock-customer@example.test",
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

        category = Category.objects.create(
            name="Dairy & Eggs",
            slug="dairy-eggs",
        )

        self.product = Product.objects.create(
            producer=self.producer,
            category=category,
            name="Fresh Eggs",
            description="Fresh free-range eggs.",
            price=Decimal("3.50"),
            unit=Product.Unit.DOZEN,
            stock_quantity=Decimal("50.00"),
            low_stock_threshold=Decimal("10.00"),
            availability_status=(
                Product.Availability.IN_SEASON
            ),
            allergen_information="Contains eggs",
            organic_certified=False,
            is_active=True,
        )

    def active_low_stock_notifications(self):
        return UserNotification.objects.filter(
            recipient=self.producer_user,
            product=self.product,
            notification_type=(
                UserNotification.NotificationType.LOW_STOCK
            ),
            is_resolved=False,
        )

    def test_tc023_no_alert_above_threshold(self):
        self.product.stock_quantity = Decimal("12.00")
        self.product.save(
            update_fields=["stock_quantity"]
        )

        sync_low_stock_notification(
            self.product
        )

        self.assertFalse(
            self.active_low_stock_notifications().exists()
        )

    def test_tc023_alert_created_below_threshold(self):
        self.product.stock_quantity = Decimal("9.00")
        self.product.save(
            update_fields=["stock_quantity"]
        )

        sync_low_stock_notification(
            self.product
        )

        notification = (
            self.active_low_stock_notifications().get()
        )

        self.assertEqual(
            notification.title,
            "Low Stock Alert: Fresh Eggs",
        )

        self.assertEqual(
            notification.message,
            (
                "Low Stock Alert: Fresh Eggs - "
                "Only 9 dozen remaining"
            ),
        )

    def test_existing_alert_is_updated_not_duplicated(self):
        self.product.stock_quantity = Decimal("9.00")
        self.product.save(
            update_fields=["stock_quantity"]
        )

        sync_low_stock_notification(
            self.product
        )

        self.product.stock_quantity = Decimal("7.00")
        self.product.save(
            update_fields=["stock_quantity"]
        )

        sync_low_stock_notification(
            self.product
        )

        self.assertEqual(
            self.active_low_stock_notifications().count(),
            1,
        )

        notification = (
            self.active_low_stock_notifications().get()
        )

        self.assertIn(
            "Only 7 dozen remaining",
            notification.message,
        )

    def test_alert_is_resolved_after_restocking(self):
        self.product.stock_quantity = Decimal("9.00")
        self.product.save(
            update_fields=["stock_quantity"]
        )

        notification = sync_low_stock_notification(
            self.product
        )

        self.product.stock_quantity = Decimal("40.00")
        self.product.save(
            update_fields=["stock_quantity"]
        )

        sync_low_stock_notification(
            self.product
        )

        notification.refresh_from_db()

        self.assertTrue(
            notification.is_resolved
        )

        self.assertTrue(
            notification.is_read
        )

    def test_checkout_automatically_generates_alert(self):
        self.product.stock_quantity = Decimal("12.00")
        self.product.save(
            update_fields=["stock_quantity"]
        )

        cart = Cart.objects.create(
            customer=self.customer
        )

        CartItem.objects.create(
            cart=cart,
            product=self.product,
            quantity=Decimal("3.00"),
        )

        create_order_from_cart(
            customer=self.customer,
            delivery_address="45 Park Street, Bristol",
            delivery_postcode="BS1 5JG",
            delivery_at=(
                timezone.now()
                + timedelta(hours=72)
            ),
            special_instructions="",
            payment_token="tok_success",
            card_last_four="4242",
        )

        self.product.refresh_from_db()

        self.assertEqual(
            self.product.stock_quantity,
            Decimal("9.00"),
        )

        self.assertTrue(
            self.active_low_stock_notifications().exists()
        )
