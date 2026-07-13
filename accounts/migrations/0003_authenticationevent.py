from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_customerprofile_producerprofile"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuthenticationEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            (
                                "login_success",
                                "Login Success",
                            ),
                            (
                                "login_failure",
                                "Login Failure",
                            ),
                            (
                                "login_blocked",
                                "Login Blocked",
                            ),
                            (
                                "logout",
                                "Logout",
                            ),
                        ],
                        max_length=30,
                    ),
                ),
                (
                    "email",
                    models.EmailField(
                        blank=True,
                        max_length=254,
                    ),
                ),
                (
                    "ip_address",
                    models.GenericIPAddressField(
                        blank=True,
                        null=True,
                    ),
                ),
                (
                    "user_agent",
                    models.CharField(
                        blank=True,
                        max_length=500,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=(
                            django.db.models.deletion.SET_NULL
                        ),
                        related_name="authentication_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=[
                            "email",
                            "ip_address",
                            "event_type",
                            "created_at",
                        ],
                        name="auth_event_lookup_idx",
                    ),
                ],
            },
        ),
    ]
