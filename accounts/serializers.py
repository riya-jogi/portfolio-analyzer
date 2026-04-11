from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Read-only representation of the custom user."""

    class Meta:
        model = User
        fields = ("id", "email", "name", "is_admin")
        read_only_fields = fields


class RegisterSerializer(serializers.ModelSerializer):
    """Register with email, name, and password (write-only)."""

    password = serializers.CharField(write_only=True, min_length=8, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ("id", "email", "name", "password", "is_admin")
        read_only_fields = ("id", "is_admin")
        extra_kwargs = {"name": {"required": True}}

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        return user


class LoginSerializer(serializers.Serializer):
    """Validate credentials before issuing a token."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
