import os
from pathlib import Path

import dj_database_url


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY", "local-development-only-secret-key")
DEBUG = os.getenv("DEBUG", "true").lower() in {"1", "true", "yes"}
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "catalog",
    "carts",
    "orders",
    "coupons",
    "reports",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
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
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{(BASE_DIR / 'db.sqlite3').as_posix()}",
        conn_max_age=0,
    )
}

if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
    DATABASES["default"]["OPTIONS"] = {
        "transaction_mode": "IMMEDIATE",
        "timeout": 20,
        "init_command": (
            "PRAGMA journal_mode=WAL; "
            "PRAGMA busy_timeout=20000; "
            "PRAGMA foreign_keys=ON;"
        ),
    }
    # A file-backed test database is required for thread-based concurrency tests.
    DATABASES["default"]["TEST"] = {"NAME": BASE_DIR / "test_db.sqlite3"}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "config.errors.exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Reliable Checkout and Rewards API",
    "VERSION": "1.0.0",
}

COUPON_EVERY_N_ORDERS = int(os.getenv("COUPON_EVERY_N_ORDERS", "5"))
COUPON_DISCOUNT_PERCENT = int(os.getenv("COUPON_DISCOUNT_PERCENT", "10"))

if COUPON_EVERY_N_ORDERS <= 0:
    raise ValueError("COUPON_EVERY_N_ORDERS must be positive")
if not 0 <= COUPON_DISCOUNT_PERCENT <= 100:
    raise ValueError("COUPON_DISCOUNT_PERCENT must be between 0 and 100")

