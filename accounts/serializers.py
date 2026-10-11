from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from accounts.models import User


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ["id", "username", "email", "password", "role"]
        read_only_fields = ["id", "role"]

    def validate(self, attrs):
        # Validate against a transient user so similarity checks see username/email.
        validate_password(attrs["password"], User(username=attrs["username"], email=attrs["email"]))
        return attrs

    def create(self, validated_data):
        # Self-registration always yields a standard user; admins are promoted by admins.
        return User.objects.create_user(role=User.Role.STANDARD, **validated_data)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "role"]
        read_only_fields = fields
