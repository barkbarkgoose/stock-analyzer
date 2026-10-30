"""Production settings: one Docker image behind host Caddy on a single VPS.

Everything comes from the environment (``/etc/stonks/app.env`` on the
server, passed in by compose.production.yaml).  Missing required values fail
at startup rather than falling back to something unsafe.
"""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import BASE_DIR, MIDDLEWARE, REPO_ROOT, SECRET_KEY, env

DEBUG = False

if not SECRET_KEY or SECRET_KEY in {"change-me", "change-me-in-production"}:
    raise ImproperlyConfigured("SECRET_KEY must be set to a long random value.")

# The public hostname(s), plus loopback for the container health check.
ALLOWED_HOSTS = [*env.list("ALLOWED_HOSTS"), "localhost", "127.0.0.1"]
CSRF_TRUSTED_ORIGINS = [f"https://{host}" for host in env.list("ALLOWED_HOSTS")]

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = 60
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

# The SPA and API share one origin, so no cross-origin access is needed.
CORS_ALLOWED_ORIGINS: list[str] = []
CORS_ALLOW_ALL_ORIGINS = False

# Caddy terminates TLS and redirects HTTP -> HTTPS; trust its header.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=3600)

# Static files: Django admin assets plus the built Vue app, both via WhiteNoise.
MIDDLEWARE = [
    MIDDLEWARE[0],  # SecurityMiddleware stays first
    "whitenoise.middleware.WhiteNoiseMiddleware",
    *MIDDLEWARE[1:],
]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
# Serve frontend/dist at the site root (/assets/..., /favicon.svg); index.html
# itself is returned by the SPA fallback view for client-side routes.
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
WHITENOISE_ROOT = FRONTEND_DIST
WHITENOISE_MAX_AGE = 3600

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {
        # Request bodies and tokens never get logged; 4xx noise stays at WARNING.
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}
