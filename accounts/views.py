from django.contrib.auth import authenticate, get_user_model
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import LoginSerializer, RegisterSerializer, UserSerializer

User = get_user_model()


class RegisterView(APIView):
    """Create user and return auth token."""

    permission_classes = [AllowAny]

    def post(self, request):
        ser = RegisterSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                {"success": False, "errors": ser.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = ser.save()
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {
                "success": True,
                "token": token.key,
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """Return token for valid email/password."""

    permission_classes = [AllowAny]

    def post(self, request):
        ser = LoginSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                {"success": False, "errors": ser.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        email = ser.validated_data["email"]
        password = ser.validated_data["password"]
        user = authenticate(request, username=email, password=password)
        if user is None:
            return Response(
                {"success": False, "error": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not user.is_active:
            return Response(
                {"success": False, "error": "User account is disabled."},
                status=status.HTTP_403_FORBIDDEN,
            )
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {
                "success": True,
                "token": token.key,
                "user": UserSerializer(user).data,
            },
        )


class MeView(APIView):
    """Current user profile (requires token)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"success": True, "user": UserSerializer(request.user).data})
