from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from accounts.models import (
    CustomerProfile,
    ProducerProfile,
    User,
)
from marketplace.models import Category, Product
from orders.models import (
    Cart,
    CartItem,
    Order,
    OrderItem,
    PaymentTransaction,
    ProducerOrder,
    ProducerOrderStatusHistory,
    UserNotification,
)
from orders.notification_services import (
    sync_low_stock_notification,
)
from orders.reporting import previous_week_range


DEMO_PASSWORD = "DemoPassword2026!"

DEMO_EMAILS = {
    "admin": "demo.admin@example.test",
    "farm": "demo.farm@example.test",
    "dairy": "demo.dairy@example.test",
    "customer": "demo.customer@example.test",
    "restaurant": "demo.restaurant@example.test",
}

DEMO_MARKER = "[DEMO]"


class Command(BaseCommand):
    help = (
        "Create reusable demonstration accounts, products, "
        "orders, notifications and report data."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(
            "Preparing Bristol Regional Food Network demo data..."
        )

        self.reset_demo_records()

        users = self.create_users()
        producers = self.create_profiles(users)
        categories = self.create_categories()
        products = self.create_products(
            producers=producers,
            categories=categories,
        )

        self.create_demo_cart(
            customer=users["restaurant"],
            products=products,
        )

        completed_order = self.create_completed_order(
            customer=users["customer"],
            products=products,
        )

        active_order = self.create_active_order(
            customer=users["customer"],
            products=products,
        )

        sync_low_stock_notification(
            products["eggs"]
        )

        self.create_order_notifications(
            order=active_order,
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Demo data created successfully."
            )
        )

        self.print_summary(
            completed_order=completed_order,
            active_order=active_order,
        )

    def reset_demo_records(self):
        """
        Remove generated records while preserving non-demo data.
        """

        demo_email_values = list(
            DEMO_EMAILS.values()
        )

        demo_orders = Order.objects.filter(
            customer__email__in=demo_email_values,
            special_instructions__startswith=DEMO_MARKER,
        )

        PaymentTransaction.objects.filter(
            order__in=demo_orders
        ).delete()

        demo_orders.delete()

        CartItem.objects.filter(
            cart__customer__email__in=demo_email_values
        ).delete()

        Cart.objects.filter(
            customer__email__in=demo_email_values
        ).delete()

        UserNotification.objects.filter(
            recipient__email__in=demo_email_values
        ).delete()

        Product.objects.filter(
            producer__user__email__in=[
                DEMO_EMAILS["farm"],
                DEMO_EMAILS["dairy"],
            ]
        ).delete()

    def ensure_user(
        self,
        *,
        email,
        first_name,
        last_name,
        role,
        is_staff=False,
        is_superuser=False,
    ):
        user, _created = User.objects.get_or_create(
            email=email,
        )

        user.first_name = first_name
        user.last_name = last_name
        user.role = role
        user.is_active = True
        user.is_staff = is_staff
        user.is_superuser = is_superuser
        user.set_password(DEMO_PASSWORD)
        user.save()

        return user

    def create_users(self):
        return {
            "admin": self.ensure_user(
                email=DEMO_EMAILS["admin"],
                first_name="Demo",
                last_name="Administrator",
                role=User.Role.ADMIN,
                is_staff=True,
                is_superuser=True,
            ),
            "farm": self.ensure_user(
                email=DEMO_EMAILS["farm"],
                first_name="Jane",
                last_name="Smith",
                role=User.Role.PRODUCER,
            ),
            "dairy": self.ensure_user(
                email=DEMO_EMAILS["dairy"],
                first_name="Helen",
                last_name="Brown",
                role=User.Role.PRODUCER,
            ),
            "customer": self.ensure_user(
                email=DEMO_EMAILS["customer"],
                first_name="Robert",
                last_name="Johnson",
                role=User.Role.CUSTOMER,
            ),
            "restaurant": self.ensure_user(
                email=DEMO_EMAILS["restaurant"],
                first_name="Sam",
                last_name="Taylor",
                role=User.Role.RESTAURANT,
            ),
        }

    def create_profiles(self, users):
        farm, _created = ProducerProfile.objects.update_or_create(
            user=users["farm"],
            defaults={
                "business_name": "Bristol Valley Farm",
                "phone": "01179 123456",
                "business_address": (
                    "1 Farm Lane, Bristol"
                ),
                "postcode": "BS1 4DJ",
                "is_verified": True,
            },
        )

        dairy, _created = ProducerProfile.objects.update_or_create(
            user=users["dairy"],
            defaults={
                "business_name": "Hillside Dairy",
                "phone": "01179 333444",
                "business_address": (
                    "2 Dairy Lane, Bristol"
                ),
                "postcode": "BS2 2AA",
                "is_verified": True,
            },
        )

        CustomerProfile.objects.update_or_create(
            user=users["customer"],
            defaults={
                "phone": "07700 900123",
                "delivery_address": (
                    "45 Park Street, Bristol"
                ),
                "postcode": "BS1 5JG",
                "accepted_terms": True,
            },
        )

        CustomerProfile.objects.update_or_create(
            user=users["restaurant"],
            defaults={
                "phone": "07700 900456",
                "delivery_address": (
                    "8 Harbourside Walk, Bristol"
                ),
                "postcode": "BS1 5UH",
                "accepted_terms": True,
            },
        )

        return {
            "farm": farm,
            "dairy": dairy,
        }

    def create_categories(self):
        category_data = {
            "vegetables": (
                "Vegetables",
                "Fresh seasonal vegetables.",
            ),
            "dairy-eggs": (
                "Dairy & Eggs",
                "Local dairy products and eggs.",
            ),
            "bakery": (
                "Bakery",
                "Freshly baked local products.",
            ),
            "fruit": (
                "Fruit",
                "Seasonal locally grown fruit.",
            ),
            "preserves": (
                "Preserves",
                "Local jams, chutneys and preserves.",
            ),
        }

        categories = {}

        for slug, values in category_data.items():
            name, description = values

            category, _created = (
                Category.objects.update_or_create(
                    slug=slug,
                    defaults={
                        "name": name,
                        "description": description,
                        "is_active": True,
                    },
                )
            )

            categories[slug] = category

        return categories

    def ensure_product(
        self,
        *,
        producer,
        category,
        name,
        description,
        price,
        unit,
        stock,
        threshold,
        availability,
        allergens,
        organic=False,
        certification="",
        harvest_date=None,
        best_before_date=None,
    ):
        product, _created = Product.objects.update_or_create(
            producer=producer,
            name=name,
            defaults={
                "category": category,
                "description": description,
                "price": price,
                "unit": unit,
                "stock_quantity": stock,
                "low_stock_threshold": threshold,
                "availability_status": availability,
                "available_from": (
                    timezone.localdate()
                    - timedelta(days=30)
                ),
                "available_until": (
                    timezone.localdate()
                    + timedelta(days=120)
                ),
                "harvest_date": harvest_date,
                "best_before_date": best_before_date,
                "allergen_information": allergens,
                "organic_certified": organic,
                "organic_certification_details": certification,
                "is_active": True,
            },
        )

        product.full_clean()
        product.save()

        return product

    def create_products(
        self,
        *,
        producers,
        categories,
    ):
        today = timezone.localdate()

        return {
            "carrots": self.ensure_product(
                producer=producers["farm"],
                category=categories["vegetables"],
                name="Organic Carrots",
                description=(
                    "Fresh organic carrots grown near Bristol."
                ),
                price=Decimal("2.50"),
                unit=Product.Unit.KILOGRAM,
                stock=Decimal("32.00"),
                threshold=Decimal("5.00"),
                availability=(
                    Product.Availability.IN_SEASON
                ),
                allergens="No common allergens",
                organic=True,
                certification=(
                    "Soil Association demonstration record"
                ),
                harvest_date=today - timedelta(days=1),
                best_before_date=today + timedelta(days=10),
            ),
            "tomatoes": self.ensure_product(
                producer=producers["farm"],
                category=categories["vegetables"],
                name="Heritage Tomatoes",
                description=(
                    "Mixed heritage tomatoes grown locally."
                ),
                price=Decimal("3.50"),
                unit=Product.Unit.KILOGRAM,
                stock=Decimal("18.00"),
                threshold=Decimal("4.00"),
                availability=(
                    Product.Availability.IN_SEASON
                ),
                allergens="No common allergens",
                organic=True,
                certification=(
                    "Organic demonstration certification"
                ),
                harvest_date=today,
                best_before_date=today + timedelta(days=7),
            ),
            "bread": self.ensure_product(
                producer=producers["farm"],
                category=categories["bakery"],
                name="Sourdough Loaf",
                description=(
                    "Traditional slow-fermented sourdough loaf."
                ),
                price=Decimal("3.00"),
                unit=Product.Unit.LOAF,
                stock=Decimal("16.00"),
                threshold=Decimal("4.00"),
                availability=(
                    Product.Availability.YEAR_ROUND
                ),
                allergens=(
                    "Contains wheat and gluten"
                ),
                best_before_date=today + timedelta(days=3),
            ),
            "milk": self.ensure_product(
                producer=producers["dairy"],
                category=categories["dairy-eggs"],
                name="Fresh Whole Milk",
                description=(
                    "Fresh whole milk from a local dairy herd."
                ),
                price=Decimal("1.80"),
                unit=Product.Unit.LITRE,
                stock=Decimal("24.00"),
                threshold=Decimal("5.00"),
                availability=(
                    Product.Availability.YEAR_ROUND
                ),
                allergens="Contains milk",
                best_before_date=today + timedelta(days=6),
            ),
            "eggs": self.ensure_product(
                producer=producers["dairy"],
                category=categories["dairy-eggs"],
                name="Free Range Eggs",
                description=(
                    "A dozen free-range eggs from local hens."
                ),
                price=Decimal("3.50"),
                unit=Product.Unit.DOZEN,
                stock=Decimal("8.00"),
                threshold=Decimal("10.00"),
                availability=(
                    Product.Availability.YEAR_ROUND
                ),
                allergens="Contains eggs",
                best_before_date=today + timedelta(days=18),
            ),
            "cheddar": self.ensure_product(
                producer=producers["dairy"],
                category=categories["dairy-eggs"],
                name="Mature Cheddar",
                description=(
                    "A 250g pack of mature local cheddar."
                ),
                price=Decimal("4.20"),
                unit=Product.Unit.PACK,
                stock=Decimal("14.00"),
                threshold=Decimal("3.00"),
                availability=(
                    Product.Availability.YEAR_ROUND
                ),
                allergens="Contains milk",
                best_before_date=today + timedelta(days=30),
            ),
        }

    def create_cart_item(
        self,
        *,
        cart,
        product,
        quantity,
    ):
        item = CartItem(
            cart=cart,
            product=product,
            quantity=quantity,
        )

        item.full_clean()
        item.save()

    def create_demo_cart(
        self,
        *,
        customer,
        products,
    ):
        cart, _created = Cart.objects.get_or_create(
            customer=customer
        )

        cart.items.all().delete()

        self.create_cart_item(
            cart=cart,
            product=products["tomatoes"],
            quantity=Decimal("2.00"),
        )

        self.create_cart_item(
            cart=cart,
            product=products["cheddar"],
            quantity=Decimal("3.00"),
        )

    def aware_datetime(
        self,
        *,
        date_value,
        hour,
    ):
        return timezone.make_aware(
            datetime.combine(
                date_value,
                time(hour=hour),
            )
        )

    def create_order(
        self,
        *,
        customer,
        created_at,
        delivery_at,
        line_items,
        order_status,
        producer_statuses,
        instructions,
    ):
        total = sum(
            (
                product.price * quantity
                for product, quantity in line_items
            ),
            Decimal("0.00"),
        )

        order = Order(
            customer=customer,
            delivery_address=(
                customer.customer_profile.delivery_address
            ),
            delivery_postcode=(
                customer.customer_profile.postcode
            ),
            special_instructions=(
                f"{DEMO_MARKER} {instructions}"
            ),
            status=order_status,
            payment_status=Order.PaymentStatus.PAID,
        )

        order.set_financial_totals(total)
        order.full_clean()
        order.save()

        Order.objects.filter(
            pk=order.pk
        ).update(
            created_at=created_at
        )

        order.refresh_from_db()

        grouped_items = defaultdict(list)

        for product, quantity in line_items:
            grouped_items[product.producer_id].append(
                (product, quantity)
            )

        producer_orders = []

        for producer_id, items in grouped_items.items():
            producer = items[0][0].producer

            producer_subtotal = sum(
                (
                    product.price * quantity
                    for product, quantity in items
                ),
                Decimal("0.00"),
            )

            producer_order = ProducerOrder(
                order=order,
                producer=producer,
                delivery_at=delivery_at,
                status=producer_statuses[producer_id],
            )

            producer_order.set_financial_totals(
                producer_subtotal
            )

            producer_order.full_clean()
            producer_order.save()

            for product, quantity in items:
                order_item = OrderItem(
                    producer_order=producer_order,
                    product=product,
                    quantity=quantity,
                )

                order_item.capture_product_snapshot()
                order_item.full_clean()
                order_item.save()

            producer_orders.append(producer_order)

        PaymentTransaction.objects.create(
            order=order,
            provider="MockPay",
            transaction_reference=(
                f"DEMO-{order.order_number}"
            ),
            status=(
                PaymentTransaction.Status.SUCCEEDED
            ),
            amount=order.total_amount,
            card_last_four="4242",
        )

        return order, producer_orders

    def create_completed_order(
        self,
        *,
        customer,
        products,
    ):
        previous_start, _previous_end = (
            previous_week_range()
        )

        created_at = self.aware_datetime(
            date_value=(
                previous_start + timedelta(days=1)
            ),
            hour=9,
        )

        delivery_at = self.aware_datetime(
            date_value=(
                previous_start + timedelta(days=4)
            ),
            hour=11,
        )

        line_items = [
            (
                products["carrots"],
                Decimal("2.00"),
            ),
            (
                products["tomatoes"],
                Decimal("1.00"),
            ),
            (
                products["eggs"],
                Decimal("2.00"),
            ),
            (
                products["milk"],
                Decimal("3.00"),
            ),
        ]

        producer_statuses = {
            products["carrots"].producer_id: (
                ProducerOrder.Status.DELIVERED
            ),
            products["milk"].producer_id: (
                ProducerOrder.Status.DELIVERED
            ),
        }

        order, _producer_orders = self.create_order(
            customer=customer,
            created_at=created_at,
            delivery_at=delivery_at,
            line_items=line_items,
            order_status=Order.Status.COMPLETED,
            producer_statuses=producer_statuses,
            instructions=(
                "Completed multi-producer report example."
            ),
        )

        return order

    def create_active_order(
        self,
        *,
        customer,
        products,
    ):
        created_at = (
            timezone.now() - timedelta(hours=1)
        )

        delivery_at = (
            timezone.now() + timedelta(hours=72)
        )

        line_items = [
            (
                products["carrots"],
                Decimal("1.00"),
            ),
            (
                products["bread"],
                Decimal("2.00"),
            ),
            (
                products["milk"],
                Decimal("2.00"),
            ),
        ]

        farm_id = products["carrots"].producer_id
        dairy_id = products["milk"].producer_id

        producer_statuses = {
            farm_id: ProducerOrder.Status.CONFIRMED,
            dairy_id: ProducerOrder.Status.READY,
        }

        order, producer_orders = self.create_order(
            customer=customer,
            created_at=created_at,
            delivery_at=delivery_at,
            line_items=line_items,
            order_status=Order.Status.PROCESSING,
            producer_statuses=producer_statuses,
            instructions=(
                "Active order for the producer dashboard."
            ),
        )

        for producer_order in producer_orders:
            if (
                producer_order.status
                == ProducerOrder.Status.CONFIRMED
            ):
                ProducerOrderStatusHistory.objects.create(
                    producer_order=producer_order,
                    previous_status=(
                        ProducerOrder.Status.PENDING
                    ),
                    new_status=(
                        ProducerOrder.Status.CONFIRMED
                    ),
                    note="Demo producer confirmed the order.",
                    changed_by=producer_order.producer.user,
                )

            if (
                producer_order.status
                == ProducerOrder.Status.READY
            ):
                ProducerOrderStatusHistory.objects.create(
                    producer_order=producer_order,
                    previous_status=(
                        ProducerOrder.Status.PENDING
                    ),
                    new_status=(
                        ProducerOrder.Status.CONFIRMED
                    ),
                    note="Demo producer confirmed the order.",
                    changed_by=producer_order.producer.user,
                )

                ProducerOrderStatusHistory.objects.create(
                    producer_order=producer_order,
                    previous_status=(
                        ProducerOrder.Status.CONFIRMED
                    ),
                    new_status=(
                        ProducerOrder.Status.READY
                    ),
                    note="Demo order is ready.",
                    changed_by=producer_order.producer.user,
                )

        return order

    def create_order_notifications(self, *, order):
        for producer_order in order.producer_orders.all():
            UserNotification.objects.create(
                recipient=producer_order.producer.user,
                notification_type=(
                    UserNotification.NotificationType.NEW_ORDER
                ),
                title=f"New order {order.order_number}",
                message=(
                    "A demonstration order is available "
                    "in the incoming-orders dashboard."
                ),
                link=reverse(
                    "orders:producer_order_detail",
                    args=[producer_order.id],
                ),
            )

        UserNotification.objects.create(
            recipient=order.customer,
            notification_type=(
                UserNotification.NotificationType.ORDER_STATUS
            ),
            title=(
                f"Order {order.order_number} status updated"
            ),
            message=(
                "Your demonstration order is being prepared "
                "by its producers."
            ),
            link=reverse(
                "orders:order_detail",
                args=[order.id],
            ),
        )

    def print_summary(
        self,
        *,
        completed_order,
        active_order,
    ):
        self.stdout.write("")
        self.stdout.write("Demo login password:")
        self.stdout.write(f"  {DEMO_PASSWORD}")
        self.stdout.write("")

        self.stdout.write("Demo accounts:")

        for label, email in DEMO_EMAILS.items():
            self.stdout.write(
                f"  {label:10} {email}"
            )

        self.stdout.write("")
        self.stdout.write(
            "Completed report order: "
            f"{completed_order.order_number}"
        )

        self.stdout.write(
            "Active producer order:   "
            f"{active_order.order_number}"
        )

        self.stdout.write("")
        self.stdout.write(
            "Open http://localhost:8000/ to begin."
        )

        self.stdout.write(
            "These are local demonstration credentials only."
        )
