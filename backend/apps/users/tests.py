"""Tests for the users app: auth payload and UserSettingsView."""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.organizations.models import Organization

User = get_user_model()

VALID_PASSWORD = "ValidPassword123!"


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def sample_user():
    org = Organization.objects.create(name="Test Org")
    return User.objects.create_user(
        email="test@example.com",
        name="Test User",
        password=VALID_PASSWORD,
        organization=org,
    )


@pytest.mark.django_db
class TestAuthViews:
    def test_login_returns_user_payload(self, api_client, sample_user):
        response = api_client.post(
            "/api/v1/auth/login/",
            {"email": sample_user.email, "password": VALID_PASSWORD},
            format="json",
        )
        assert response.status_code == 200
        assert "access" in response.data
        assert "refresh" in response.data
        # Regression guard: the frontend needs the user payload on login,
        # otherwise it stays logged in with a null user.
        assert response.data["user"]["email"] == sample_user.email


@pytest.mark.django_db
def test_self_registration_is_disabled(api_client):
    # Accounts are created by an operator (manage.py add_user), never from the web.
    payload = {"email": "new@example.com", "password": "Sup3r-secret-pw", "name": "New"}
    response = api_client.post("/api/v1/auth/register/", payload, format="json")
    assert response.status_code == 404
    assert not User.objects.filter(email="new@example.com").exists()


@pytest.mark.django_db
class TestUserSettingsAPI:
    def test_settings_unauthenticated(self, api_client):
        response = api_client.get("/api/v1/auth/settings/")
        assert response.status_code == 401

    def test_get_settings_authenticated(self, api_client, sample_user):
        api_client.force_authenticate(user=sample_user)
        response = api_client.get("/api/v1/auth/settings/")
        assert response.status_code == 200
        assert "theme_colors" in response.data

    def test_update_settings_valid(self, api_client, sample_user):
        api_client.force_authenticate(user=sample_user)
        payload = {
            "theme_colors": {
                "primary": "#8b5cf6",
                "accent": "emerald",
            },
            "default_view": "upcoming",
        }
        response = api_client.patch("/api/v1/auth/settings/", payload, format="json")
        assert response.status_code == 200
        assert response.data["theme_colors"]["primary"] == "#8b5cf6"
        assert response.data["theme_colors"]["accent"] == "emerald"
        assert response.data["default_view"] == "upcoming"

        sample_user.refresh_from_db()
        assert sample_user.settings["theme_colors"]["primary"] == "#8b5cf6"

    def test_update_settings_strips_disallowed_keys(self, api_client, sample_user):
        api_client.force_authenticate(user=sample_user)
        payload = {
            "theme_colors": {"primary": "#10b981"},
            "is_staff": True,  # Disallowed / dangerous key
            "is_superuser": True,
            "role": "admin",
        }
        response = api_client.patch("/api/v1/auth/settings/", payload, format="json")
        assert response.status_code == 200
        sample_user.refresh_from_db()
        assert not sample_user.is_staff
        assert not sample_user.is_superuser
        assert "is_staff" not in sample_user.settings
        assert "role" not in sample_user.settings

    def test_update_settings_invalid_color_rejected(self, api_client, sample_user):
        api_client.force_authenticate(user=sample_user)
        payload = {"theme_colors": {"primary": "javascript:alert(1);"}}
        response = api_client.patch("/api/v1/auth/settings/", payload, format="json")
        assert response.status_code == 400
        assert "theme_colors" in response.data

    def test_api_keys_are_encrypted_at_rest_in_db(self, api_client, sample_user):
        api_client.force_authenticate(user=sample_user)
        raw_key = "AIzaSyDummySecretKeyForTesting12345"
        payload = {
            "api_keys": {
                "google": raw_key,
                "anthropic": "sk-ant-testkey67890",
            }
        }
        response = api_client.patch("/api/v1/auth/settings/", payload, format="json")
        assert response.status_code == 200

        # Safe response: raw key is never returned to the frontend.
        assert "api_keys" not in response.data
        status_info = response.data.get("api_keys_status", {})
        assert status_info["google"]["is_configured"] is True
        assert status_info["google"]["preview"].endswith("2345")
        assert raw_key not in status_info["google"]["preview"]

        # Database verification: the raw key is NOT plain text in SQLite.
        sample_user.refresh_from_db()
        stored_keys = sample_user.settings.get("api_keys", {})
        assert stored_keys["google"] != raw_key
        assert stored_keys["google"].startswith("gAAAAA")  # Fernet token

        from apps.users.crypto import decrypt_secret

        assert decrypt_secret(stored_keys["google"]) == raw_key
        assert decrypt_secret(stored_keys["anthropic"]) == "sk-ant-testkey67890"

    def test_api_key_can_be_removed(self, api_client, sample_user):
        api_client.force_authenticate(user=sample_user)
        api_client.patch(
            "/api/v1/auth/settings/",
            {"api_keys": {"openai": "sk-test-key-123456"}},
            format="json",
        )

        response = api_client.patch(
            "/api/v1/auth/settings/",
            {"api_keys": {"openai": ""}},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["api_keys_status"]["openai"]["is_configured"] is False


@pytest.mark.django_db
class TestAddUserCommand:
    def _run(self, monkeypatch, passwords, *args):
        from django.core.management import call_command

        answers = iter(passwords)
        monkeypatch.setattr("getpass.getpass", lambda prompt="": next(answers))
        call_command("add_user", *args)

    def test_creates_a_user_who_can_log_in(self, monkeypatch, api_client):
        self._run(monkeypatch, [VALID_PASSWORD, VALID_PASSWORD], "me@example.com", "--name", "Me")
        user = User.objects.get(email="me@example.com")
        assert not user.is_staff
        response = api_client.post(
            "/api/v1/auth/login/",
            {"email": "me@example.com", "password": VALID_PASSWORD},
            format="json",
        )
        assert response.status_code == 200

    def test_admin_flag(self, monkeypatch):
        self._run(monkeypatch, [VALID_PASSWORD, VALID_PASSWORD], "boss@example.com", "--name", "Boss", "--admin")
        assert User.objects.get(email="boss@example.com").is_superuser

    def test_rejects_mismatch_weak_and_duplicate(self, monkeypatch, sample_user):
        from django.core.management.base import CommandError

        with pytest.raises(CommandError, match="did not match"):
            self._run(monkeypatch, [VALID_PASSWORD, "other"], "a@example.com", "--name", "A")
        with pytest.raises(CommandError):
            self._run(monkeypatch, ["123", "123"], "a@example.com", "--name", "A")
        with pytest.raises(CommandError, match="already exists"):
            self._run(monkeypatch, [VALID_PASSWORD, VALID_PASSWORD], sample_user.email, "--name", "Dup")
        assert not User.objects.filter(email="a@example.com").exists()
