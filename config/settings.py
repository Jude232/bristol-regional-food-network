"""
Django settings for the Bristol Regional Food Network project.
"""

import os
from pathlib import Path


# Build paths inside the project like this: BASE_DIR / "subdir".
BASE_DIR = Path(__file__).resolve().parent.parent


# Development settings
# The real secret key will later be supplied through an environment variable.
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "development-only-secret-key-change-before-deployment",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() == "true"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get(
        "DJANGO_ALLOWED_HOSTS",
        "localhost,127.0.0.1",
    ).split(",")
    if host.strip()
]


# Application definition

INSTALLED_APPS = [
    # Django applications
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party applications
    "rest_framework",
    "django_filters",

    # Project applications
    "accounts",
    "marketplace",
    "orders",
    "api",
]


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


ROOT_URLCONF = "config.urls"


TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR / "templates",
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "orders.context_processors.cart_summary",
            ],
        },
    },
]


WSGI_APPLICATION = "config.wsgi.application"


# Database
# SQLite is used during development on csctcloud.
# PostgreSQL will be configured later for Docker.

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        ),
        "OPTIONS": {
            "min_length": 8,
        },
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        ),
    },
]


# Custom user model

AUTH_USER_MODEL = "accounts.User"


# Internationalisation

LANGUAGE_CODE = "en-gb"

TIME_ZONE = "Europe/London"

USE_I18N = True

USE_TZ = True


# Static files

STATIC_URL = "static/"

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

STATIC_ROOT = BASE_DIR / "staticfiles"


# Uploaded media files

MEDIA_URL = "media/"

MEDIA_ROOT = BASE_DIR / "media"


# Default primary key field type

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Django REST Framework

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
}

# Authentication redirects

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:dashboard"
LOGOUT_REDIRECT_URL = "accounts:home"


# Docker and PostgreSQL deployment configuration
# ------------------------------------------------
# SQLite remains the default for direct development on csctcloud.
# Docker supplies POSTGRES_HOST and therefore selects PostgreSQL.

import os


docker_secret_key = os.getenv(
    "DJANGO_SECRET_KEY",
    "",
).strip()

if docker_secret_key:
    SECRET_KEY = docker_secret_key


docker_debug = os.getenv(
    "DJANGO_DEBUG",
)

if docker_debug is not None:
    DEBUG = docker_debug.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


docker_allowed_hosts = os.getenv(
    "DJANGO_ALLOWED_HOSTS",
    "",
).strip()

if docker_allowed_hosts:
    ALLOWED_HOSTS = [
        host.strip()
        for host in docker_allowed_hosts.split(",")
        if host.strip()
    ]


docker_csrf_origins = os.getenv(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "",
).strip()

if docker_csrf_origins:
    CSRF_TRUSTED_ORIGINS = [
        origin.strip()
        for origin in docker_csrf_origins.split(",")
        if origin.strip()
    ]


postgres_host = os.getenv(
    "POSTGRES_HOST",
    "",
).strip()

if postgres_host:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv(
                "POSTGRES_DB",
                "brfn_marketplace",
            ),
            "USER": os.getenv(
                "POSTGRES_USER",
                "brfn_user",
            ),
            "PASSWORD": os.getenv(
                "POSTGRES_PASSWORD",
                "",
            ),
            "HOST": postgres_host,
            "PORT": os.getenv(
                "POSTGRES_PORT",
                "5432",
            ),
            "CONN_MAX_AGE": 60,
        }
    }


STATIC_ROOT = BASE_DIR / "staticfiles"

if not DEBUG:
    STORAGES = {
        "default": {
            "BACKEND": (
                "django.core.files.storage."
                "FileSystemStorage"
            ),
        },
        "staticfiles": {
            "BACKEND": (
                "whitenoise.storage."
                "CompressedManifestStaticFilesStorage"
            ),
        },
    }

