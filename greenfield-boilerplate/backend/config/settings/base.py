"""Base settings for config project."""

import sys
from datetime import timedelta
from pathlib import Path

import environ

env = environ.Env()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Make the `keychain` package importable when settings load through a plain
# `python manage.py` invocation (dev.sh already adds backend/ to sys.path).
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

environ.Env.read_env(BASE_DIR / ".env")

from keychain import (  # noqa: E402
    KeychainNotInitializedError,
    get as keychain_get,
    get_int as keychain_get_int,
    get_list as keychain_get_list,
)


def _keychain_or_env(key: str, env_var: str, default: str | None = None) -> str | None:
    """Resolve a scalar setting from the keychain, falling back to the environment.

    The keychain is optional during first-run bootstrap: if it has not been
    initialized, values are read from `.env` so management commands keep working
    before `python -m keychain init`.
    """
    try:
        value = keychain_get(key)
    except KeychainNotInitializedError:
        value = None
    if value is not None:
        return value
    return env(env_var, default=default)


def _keychain_or_env_list(
    key: str, env_var: str, default: list[str] | None = None
) -> list[str]:
    """Resolve a comma-separated list setting from keychain or environment."""
    try:
        value = keychain_get_list(key)
    except KeychainNotInitializedError:
        value = None
    if value is not None:
        return value
    return env.list(env_var, default=default if default is not None else [])


SECRET_KEY = _keychain_or_env("SECRET_KEY", "SECRET_KEY")

DEBUG = env.bool("DEBUG", default=False)

ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "django_filters",
    "corsheaders",
    "apps.organizations",
    "apps.users",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

APPEND_SLASH = False

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

DATABASE_URL = _keychain_or_env(
    "DATABASE_URL", "DATABASE_URL", default="sqlite:///db.sqlite3"
)
DATABASES = {"default": env.db_url_config(DATABASE_URL)}

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CORS
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = _keychain_or_env_list(
    "CORS_ALLOWED_ORIGINS", "CORS_ALLOWED_ORIGINS"
)

# REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
}


def _jwt_lifetimes() -> tuple[timedelta, timedelta]:
    """Resolve JWT lifetimes from the keychain, falling back to safe defaults.

    These are read from the keychain so token lifetimes can be tuned per
    environment without editing code. Falls back to 60 minutes / 7 days when the
    keychain has not been initialized yet (e.g. during the first migration).
    """
    try:
        access_minutes = (
            keychain_get_int("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", default=60) or 60
        )
    except KeychainNotInitializedError:
        access_minutes = 60
    try:
        refresh_days = (
            keychain_get_int("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=7) or 7
        )
    except KeychainNotInitializedError:
        refresh_days = 7
    return timedelta(minutes=access_minutes), timedelta(days=refresh_days)


_ACCESS_LIFETIME, _REFRESH_LIFETIME = _jwt_lifetimes()

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": _ACCESS_LIFETIME,
    "REFRESH_TOKEN_LIFETIME": _REFRESH_LIFETIME,
}

# User settings / secrets-at-rest encryption. Optional: when unset, the users
# crypto helper falls back to keychain.key and then to a SHA-256 derivation of
# SECRET_KEY (see apps/users/crypto.py).
SETTINGS_ENCRYPTION_KEY = env("SETTINGS_ENCRYPTION_KEY", default="")
