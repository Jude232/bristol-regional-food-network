from django.test import TestCase
from django.urls import reverse

from accounts.models import AuthenticationEvent, User


class AuthenticationSecurityTests(TestCase):
    def setUp(self):
        self.password = "StrongPassword2026!"

        self.user = User.objects.create_user(
            email="security-customer@example.test",
            password=self.password,
            first_name="Security",
            last_name="Customer",
            role=User.Role.CUSTOMER,
        )

        self.login_url = reverse(
            "accounts:login"
        )

        self.logout_url = reverse(
            "accounts:logout"
        )

    def test_tc022_password_is_hashed(self):
        self.assertNotEqual(
            self.user.password,
            self.password,
        )

        self.assertTrue(
            self.user.check_password(
                self.password
            )
        )

    def test_tc022_failed_login_is_generic_and_logged(self):
        existing_response = self.client.post(
            self.login_url,
            {
                "username": self.user.email,
                "password": "IncorrectPassword!",
            },
        )

        unknown_response = self.client.post(
            self.login_url,
            {
                "username": "unknown@example.test",
                "password": "IncorrectPassword!",
            },
        )

        self.assertEqual(
            existing_response.status_code,
            200,
        )

        self.assertEqual(
            unknown_response.status_code,
            200,
        )

        self.assertEqual(
            list(
                existing_response.context[
                    "form"
                ].non_field_errors()
            ),
            list(
                unknown_response.context[
                    "form"
                ].non_field_errors()
            ),
        )

        self.assertEqual(
            AuthenticationEvent.objects.filter(
                event_type=(
                    AuthenticationEvent.EventType.LOGIN_FAILURE
                )
            ).count(),
            2,
        )

    def test_tc022_remember_me_controls_session_expiry(self):
        response = self.client.post(
            self.login_url,
            {
                "username": self.user.email,
                "password": self.password,
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertTrue(
            self.client.session.get_expire_at_browser_close()
        )

        self.client.post(
            self.logout_url
        )

        response = self.client.post(
            self.login_url,
            {
                "username": self.user.email,
                "password": self.password,
                "remember_me": "on",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertFalse(
            self.client.session.get_expire_at_browser_close()
        )

    def test_tc022_repeated_failures_are_blocked(self):
        for _attempt in range(5):
            response = self.client.post(
                self.login_url,
                {
                    "username": self.user.email,
                    "password": "IncorrectPassword!",
                },
            )

            self.assertEqual(
                response.status_code,
                200,
            )

        blocked_response = self.client.post(
            self.login_url,
            {
                "username": self.user.email,
                "password": "IncorrectPassword!",
            },
        )

        self.assertEqual(
            blocked_response.status_code,
            429,
        )

        self.assertContains(
            blocked_response,
            "Too many unsuccessful login attempts",
            status_code=429,
        )

        self.assertTrue(
            AuthenticationEvent.objects.filter(
                event_type=(
                    AuthenticationEvent.EventType.LOGIN_BLOCKED
                )
            ).exists()
        )

    def test_tc022_logout_terminates_session(self):
        self.client.post(
            self.login_url,
            {
                "username": self.user.email,
                "password": self.password,
            },
        )

        self.assertIn(
            "_auth_user_id",
            self.client.session,
        )

        self.client.post(
            self.logout_url
        )

        self.assertNotIn(
            "_auth_user_id",
            self.client.session,
        )

        protected_response = self.client.get(
            reverse("accounts:dashboard")
        )

        self.assertEqual(
            protected_response.status_code,
            302,
        )

        self.assertTrue(
            AuthenticationEvent.objects.filter(
                event_type=(
                    AuthenticationEvent.EventType.LOGOUT
                )
            ).exists()
        )

    def test_security_headers_are_present(self):
        response = self.client.get(
            reverse("accounts:home")
        )

        self.assertEqual(
            response.headers["X-Frame-Options"],
            "DENY",
        )

        self.assertEqual(
            response.headers[
                "X-Content-Type-Options"
            ],
            "nosniff",
        )

        self.assertEqual(
            response.headers["Referrer-Policy"],
            "same-origin",
        )

        self.assertEqual(
            response.headers[
                "Cross-Origin-Opener-Policy"
            ],
            "same-origin",
        )
