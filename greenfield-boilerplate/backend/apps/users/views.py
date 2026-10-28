"""Users app views."""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import (
    LoginSerializer,
    RegisterSerializer,
    UserSerializer,
    UserSettingsSerializer,
    format_safe_user_settings,
)

User = get_user_model()


class UserSettingsView(APIView):
    """
    Retrieve and update the authenticated user's UI settings.

    --------------------------------------------------------------------------
    SECURITY CONSIDERATIONS:
    1. Authentication & Ownership Isolation: Requires an authenticated session
       or JWT. Users can ONLY inspect and modify their own settings object,
       preventing cross-tenant / horizontal privilege escalation.
    2. Partial Merging with Strict Validation: Updates are validated through
       UserSettingsSerializer. Unauthorized keys are stripped.
    3. Key Masking on Read: Stored API keys are masked before serialization.
    --------------------------------------------------------------------------
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(format_safe_user_settings(request.user.settings or {}))

    def patch(self, request):
        serializer = UserSettingsSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        current_settings = request.user.settings or {}
        incoming = serializer.validated_data

        # Merge nested api_keys if provided so providers are updated individually.
        if "api_keys" in incoming and isinstance(current_settings.get("api_keys"), dict):
            incoming["api_keys"] = {**current_settings["api_keys"], **incoming["api_keys"]}

        request.user.settings = {**current_settings, **incoming}
        request.user.save(update_fields=["settings"])

        return Response(
            format_safe_user_settings(request.user.settings),
            status=status.HTTP_200_OK,
        )


class RegisterView(APIView):
    """Register a new user with organization."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        refresh = RefreshToken.for_user(user)

        user_data = UserSerializer(user).data
        user_data["token"] = str(refresh.access_token)

        return Response(user_data, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    """Authenticate user and return JWT tokens plus the user payload."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response(
                {"detail": "Invalid credentials."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.check_password(password):
            return Response(
                {"detail": "Invalid credentials."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            return Response(
                {"detail": "User account is disabled."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        refresh = RefreshToken.for_user(user)
        user_data = UserSerializer(user).data

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": user_data,
            },
            status=status.HTTP_200_OK,
        )


class RefreshTokenView(APIView):
    """Refresh access token using refresh token."""

    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"detail": "Refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            refresh = RefreshToken(refresh_token)
        except Exception:
            return Response(
                {"detail": "Invalid or expired refresh token."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return Response(
            {"access": str(refresh.access_token)},
            status=status.HTTP_200_OK,
        )
