"""URL configuration for config project."""

from django.conf import settings
from django.contrib import admin
from django.db import connection
from django.http import FileResponse, Http404, JsonResponse
from django.urls import include, path, re_path
from django.views.decorators.cache import never_cache


def health(request):
    """Liveness for Caddy/uptime checks: the app answers and the DB connects.

    Deliberately anonymous and minimal; it says nothing about market data.
    """

    try:
        connection.ensure_connection()
    except Exception:  # noqa: BLE001
        return JsonResponse({"status": "db_unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


@never_cache
def spa_index(request):
    """Return the built Vue app for client-side routes (production only).

    In development Vite serves the frontend, so this route is not registered.
    """

    index = settings.FRONTEND_DIST / "index.html"
    if not index.exists():
        raise Http404("Frontend build not found.")
    return FileResponse(index.open("rb"), content_type="text/html")


urlpatterns = [
    path("health/", health, name="health"),
    path("admin/", admin.site.urls),
    path("api/v1/auth/", include("apps.users.urls")),
    path("api/v1/market/", include("apps.market.urls")),
]

if getattr(settings, "FRONTEND_DIST", None):
    # Anything that is not the API, admin, static or health goes to the SPA.
    urlpatterns.append(
        re_path(r"^(?!api/|admin/|static/|health/).*$", spa_index, name="spa")
    )
