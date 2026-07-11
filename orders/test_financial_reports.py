from datetime import datetime, time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ProducerProfile, User

from .models import Order, ProducerOrder
from .reporting import previous_week_range


class FinancialReportTests(TestCase):
    def setUp(self):
        self.producer_user = User.objects.create_user(
            email="finance-producer@example.test",
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
            email="finance-dairy@example.test",
            password="DairyTest2026!",
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
            email="finance-customer@example.test",
            password="CustomerTest2026!",
            first_name="Robert",
            last_name="Johnson",
            role=User.Role.CUSTOMER,
        )

        self.admin_user = User.objects.create_user(
            email="finance-admin@example.test",
            password="AdminTest2026!",
            role=User.Role.ADMIN,
            is_staff=True,
        )

        self.week_start, self.week_end = (
            previous_week_range()
        )

        # Use Friday so the order created 72 hours earlier
        # still falls inside the same Monday-to-Sunday report period.
        delivery_date = (
            self.week_start
            + timedelta(days=4)
        )

        self.delivery_at = timezone.make_aware(
            datetime.combine(
                delivery_date,
                time(hour=12),
            )
        )

    def create_order(
        self,
        *,
        total: Decimal,
        status=Order.Status.COMPLETED,
    ):
        order = Order(
            customer=self.customer,
            delivery_address="45 Park Street, Bristol",
            delivery_postcode="BS1 5JG",
            status=status,
            payment_status=Order.PaymentStatus.PAID,
        )

        order.set_financial_totals(total)
        order.save()

        Order.objects.filter(
            pk=order.pk
        ).update(
            created_at=(
                self.delivery_at
                - timedelta(hours=72)
            )
        )

        order.refresh_from_db()

        return order

    def create_producer_order(
        self,
        *,
        order,
        producer,
        subtotal,
        status=ProducerOrder.Status.DELIVERED,
    ):
        producer_order = ProducerOrder(
            order=order,
            producer=producer,
            delivery_at=self.delivery_at,
            status=status,
        )

        producer_order.set_financial_totals(
            subtotal
        )

        producer_order.full_clean()
        producer_order.save()

        return producer_order

    def test_tc012_producer_weekly_settlement_totals(self):
        order = self.create_order(
            total=Decimal("100.00")
        )

        self.create_producer_order(
            order=order,
            producer=self.producer,
            subtotal=Decimal("100.00"),
        )

        self.client.force_login(
            self.producer_user
        )

        response = self.client.get(
            reverse(
                "reports:producer_settlement"
            ),
            {
                "start": self.week_start.isoformat(),
                "end": self.week_end.isoformat(),
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "£100.00",
        )

        self.assertContains(
            response,
            "£5.00",
        )

        self.assertContains(
            response,
            "£95.00",
        )

        self.assertContains(
            response,
            order.order_number,
        )

    def test_pending_producer_order_is_excluded(self):
        order = self.create_order(
            total=Decimal("50.00")
        )

        self.create_producer_order(
            order=order,
            producer=self.producer,
            subtotal=Decimal("50.00"),
            status=ProducerOrder.Status.PENDING,
        )

        self.client.force_login(
            self.producer_user
        )

        response = self.client.get(
            reverse(
                "reports:producer_settlement"
            ),
            {
                "start": self.week_start.isoformat(),
                "end": self.week_end.isoformat(),
            },
        )

        self.assertContains(
            response,
            "No delivered orders in this period",
        )

        self.assertNotContains(
            response,
            order.order_number,
        )

    def test_producer_can_download_csv(self):
        order = self.create_order(
            total=Decimal("100.00")
        )

        self.create_producer_order(
            order=order,
            producer=self.producer,
            subtotal=Decimal("100.00"),
        )

        self.client.force_login(
            self.producer_user
        )

        response = self.client.get(
            reverse(
                "reports:producer_settlement_csv"
            ),
            {
                "start": self.week_start.isoformat(),
                "end": self.week_end.isoformat(),
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response["Content-Type"],
            "text/csv",
        )

        self.assertIn(
            order.order_number,
            response.content.decode(),
        )

    def test_tc025_admin_multi_vendor_report(self):
        order = self.create_order(
            total=Decimal("150.00")
        )

        self.create_producer_order(
            order=order,
            producer=self.producer,
            subtotal=Decimal("80.00"),
        )

        self.create_producer_order(
            order=order,
            producer=self.other_producer,
            subtotal=Decimal("70.00"),
        )

        self.client.force_login(
            self.admin_user
        )

        response = self.client.get(
            reverse(
                "reports:commission_report"
            ),
            {
                "start": self.week_start.isoformat(),
                "end": self.week_end.isoformat(),
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "£150.00",
        )

        self.assertContains(
            response,
            "£7.50",
        )

        self.assertContains(
            response,
            "£76.00",
        )

        self.assertContains(
            response,
            "£66.50",
        )

        self.assertContains(
            response,
            "Bristol Valley Farm",
        )

        self.assertContains(
            response,
            "Hillside Dairy",
        )

    def test_non_admin_cannot_access_commission_report(self):
        self.client.force_login(
            self.producer_user
        )

        response = self.client.get(
            reverse(
                "reports:commission_report"
            )
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_admin_can_download_commission_csv(self):
        order = self.create_order(
            total=Decimal("100.00")
        )

        self.create_producer_order(
            order=order,
            producer=self.producer,
            subtotal=Decimal("100.00"),
        )

        self.client.force_login(
            self.admin_user
        )

        response = self.client.get(
            reverse(
                "reports:commission_report_csv"
            ),
            {
                "start": self.week_start.isoformat(),
                "end": self.week_end.isoformat(),
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response["Content-Type"],
            "text/csv",
        )

        csv_content = response.content.decode()

        self.assertIn(
            order.order_number,
            csv_content,
        )

        self.assertIn(
            "5.00",
            csv_content,
        )

        self.assertIn(
            "95.00",
            csv_content,
        )
