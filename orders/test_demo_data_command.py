from django.core.management import call_command
from django.test import TestCase

from accounts.models import User
from marketplace.models import Product
from orders.models import (
    Cart,
    Order,
    ProducerOrder,
    UserNotification,
)


class DemoDataCommandTests(TestCase):
    def run_command(self):
        call_command(
            "seed_demo_data",
            verbosity=0,
        )

    def demo_counts(self):
        demo_emails = [
            "demo.admin@example.test",
            "demo.farm@example.test",
            "demo.dairy@example.test",
            "demo.customer@example.test",
            "demo.restaurant@example.test",
        ]

        return {
            "users": User.objects.filter(
                email__in=demo_emails
            ).count(),
            "products": Product.objects.filter(
                producer__user__email__in=[
                    "demo.farm@example.test",
                    "demo.dairy@example.test",
                ]
            ).count(),
            "orders": Order.objects.filter(
                customer__email=(
                    "demo.customer@example.test"
                ),
                special_instructions__startswith="[DEMO]",
            ).count(),
            "producer_orders": (
                ProducerOrder.objects.filter(
                    order__customer__email=(
                        "demo.customer@example.test"
                    ),
                    order__special_instructions__startswith=(
                        "[DEMO]"
                    ),
                ).count()
            ),
            "notifications": (
                UserNotification.objects.filter(
                    recipient__email__in=demo_emails
                ).count()
            ),
        }

    def test_command_creates_demo_records(self):
        self.run_command()

        admin = User.objects.get(
            email="demo.admin@example.test"
        )

        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)

        self.assertEqual(
            User.objects.filter(
                email__startswith="demo."
            ).count(),
            5,
        )

        self.assertEqual(
            Product.objects.filter(
                producer__user__email__in=[
                    "demo.farm@example.test",
                    "demo.dairy@example.test",
                ]
            ).count(),
            6,
        )

        self.assertEqual(
            Order.objects.filter(
                customer__email=(
                    "demo.customer@example.test"
                )
            ).count(),
            2,
        )

        self.assertEqual(
            ProducerOrder.objects.filter(
                order__customer__email=(
                    "demo.customer@example.test"
                )
            ).count(),
            4,
        )

        self.assertTrue(
            Cart.objects.filter(
                customer__email=(
                    "demo.restaurant@example.test"
                )
            ).exists()
        )

        self.assertTrue(
            UserNotification.objects.filter(
                notification_type=(
                    UserNotification.NotificationType.LOW_STOCK
                )
            ).exists()
        )

    def test_command_can_be_run_repeatedly(self):
        self.run_command()
        first_counts = self.demo_counts()

        self.run_command()
        second_counts = self.demo_counts()

        self.assertEqual(
            first_counts,
            second_counts,
        )
