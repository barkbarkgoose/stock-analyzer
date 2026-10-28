"""Users app models."""

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models

from apps.organizations.models import Organization


class UserManager(BaseUserManager):
    """Custom manager for User model."""

    def create_user(
        self, email, name, password=None, organization=None, **extra_fields
    ):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(
            email=email, name=name, organization=organization, **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(
        self, email, name, password=None, organization=None, **extra_fields
    ):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if organization is None:
            organization = Organization.objects.create(name=f"Superuser Org ({email})")
        return self.create_user(email, name, password, organization, **extra_fields)


def default_user_settings() -> dict:
    """Default schema for per-user UI preferences."""
    return {
        "theme_colors": {},
        "default_view": "all",
    }


class User(AbstractBaseUser, PermissionsMixin):
    organization = models.ForeignKey(
        Organization, on_delete=models.SET_NULL, null=True, blank=True
    )
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # --------------------------------------------------------------------------
    # SECURITY CONSIDERATIONS (User Settings JSONField):
    # 1. Scope Restriction: This field is strictly reserved for non-sensitive UI/UX
    #    preferences and encrypted credentials (e.g. theme colors, AI providers).
    # 2. Privilege Separation: NEVER store authorization flags (is_staff, is_superuser,
    #    roles), permissions, passwords, or security-critical state in this dictionary.
    # 3. Input Sanitization: All incoming updates MUST be validated and whitelisted at
    #    the serializer layer (UserSettingsSerializer) to prevent injection of
    #    unexpected keys, payload bloat (DoS), or untrusted HTML/scripts.
    # 4. Encryption: Secret values (e.g. api_keys) are encrypted at rest via
    #    apps.users.crypto before being persisted.
    # --------------------------------------------------------------------------
    settings = models.JSONField(
        default=default_user_settings,
        blank=True,
        help_text="User UI/UX preferences and encrypted per-user credentials.",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    objects = UserManager()

    class Meta:
        ordering = ["-created_at"]
