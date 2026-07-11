from django.test import TestCase
from django.urls import reverse

from .models import CustomerProfile, ProducerProfile, User


class ProducerRegistrationTests(TestCase):
    def test_tc001_producer_can_register(self):
        response = self.client.post(
            reverse("accounts:producer_register"),
            {
                "email": "jane.smith@bristolvalleyfarm.test",
                "first_name": "Jane",
                "last_name": "Smith",
                "business_name": "Bristol Valley Farm",
                "phone": "01179 123456",
                "business_address": "1 Farm Lane, Bristol",
                "postcode": "BS1 4DJ",
                "password1": "SafePass-2026-Producer!",
                "password2": "SafePass-2026-Producer!",
            },
        )

        self.assertRedirects(
            response,
            reverse("accounts:login"),
        )

        user = User.objects.get(
            email="jane.smith@bristolvalleyfarm.test"
        )

        self.assertEqual(
            user.role,
            User.Role.PRODUCER,
        )

        self.assertTrue(
            user.check_password("SafePass-2026-Producer!")
        )

        self.assertNotEqual(
            user.password,
            "SafePass-2026-Producer!",
        )

        profile = ProducerProfile.objects.get(
            user=user,
        )

        self.assertEqual(
            profile.business_name,
            "Bristol Valley Farm",
        )

        self.assertEqual(
            profile.postcode,
            "BS1 4DJ",
        )


class CustomerRegistrationTests(TestCase):
    def test_tc002_customer_can_register(self):
        response = self.client.post(
            reverse("accounts:customer_register"),
            {
                "email": "robert.johnson@example.test",
                "first_name": "Robert",
                "last_name": "Johnson",
                "phone": "07700 900123",
                "delivery_address": "45 Park Street, Bristol",
                "postcode": "BS1 5JG",
                "accepted_terms": True,
                "password1": "SafePass-2026-Customer!",
                "password2": "SafePass-2026-Customer!",
            },
        )

        self.assertRedirects(
            response,
            reverse("accounts:login"),
        )

        user = User.objects.get(
            email="robert.johnson@example.test"
        )

        self.assertEqual(
            user.role,
            User.Role.CUSTOMER,
        )

        self.assertTrue(
            user.check_password("SafePass-2026-Customer!")
        )

        profile = CustomerProfile.objects.get(
            user=user,
        )

        self.assertEqual(
            profile.delivery_address,
            "45 Park Street, Bristol",
        )

        self.assertTrue(
            profile.accepted_terms,
        )

    def test_terms_must_be_accepted(self):
        response = self.client.post(
            reverse("accounts:customer_register"),
            {
                "email": "no.terms@example.test",
                "first_name": "No",
                "last_name": "Terms",
                "phone": "07700 900999",
                "delivery_address": "1 Test Street, Bristol",
                "postcode": "BS1 1AA",
                "password1": "SafePass-2026-Customer!",
                "password2": "SafePass-2026-Customer!",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertFalse(
            User.objects.filter(
                email="no.terms@example.test"
            ).exists()
        )


class AuthenticationSecurityTests(TestCase):
    def test_weak_password_is_rejected(self):
        response = self.client.post(
            reverse("accounts:customer_register"),
            {
                "email": "weak.password@example.test",
                "first_name": "Weak",
                "last_name": "Password",
                "phone": "07700 900555",
                "delivery_address": "2 Test Street, Bristol",
                "postcode": "BS1 1AB",
                "accepted_terms": True,
                "password1": "123",
                "password2": "123",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertFalse(
            User.objects.filter(
                email="weak.password@example.test"
            ).exists()
        )

        self.assertContains(
            response,
            "This password is too short",
        )

    def test_dashboard_requires_authentication(self):
        response = self.client.get(
            reverse("accounts:dashboard")
        )

        expected_url = (
            f"{reverse('accounts:login')}"
            f"?next={reverse('accounts:dashboard')}"
        )

        self.assertRedirects(
            response,
            expected_url,
        )
