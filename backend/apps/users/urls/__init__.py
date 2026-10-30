"""Users app URL configuration."""

from django.urls import path

from apps.users.views import (
    LoginView,
    RefreshTokenView,
    UserSettingsView,
)

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", RefreshTokenView.as_view(), name="refresh"),
    path("settings/", UserSettingsView.as_view(), name="user-settings"),
]
