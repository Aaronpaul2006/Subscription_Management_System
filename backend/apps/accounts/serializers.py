from django.contrib.auth import password_validation
from rest_framework import serializers

from .models import Customer, Role, User


class UserSerializer(serializers.ModelSerializer):
    customer_id = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "name", "role", "phone", "is_active", "date_joined", "customer_id"]
        read_only_fields = ["id", "email", "role", "is_active", "date_joined", "customer_id"]

    def get_customer_id(self, obj) -> int | None:
        customer = getattr(obj, "customer", None)
        return customer.id if customer else None


def _validate_new_password(password: str, user: User | None = None) -> str:
    password_validation.validate_password(password, user)
    return password


class SignupSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    company = serializers.CharField(max_length=200, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)

    def validate_email(self, value: str) -> str:
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate(self, attrs):
        probe = User(email=attrs["email"], name=attrs["name"])
        _validate_new_password(attrs["password"], probe)
        return attrs


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)


class StaffSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False, required=False)

    class Meta:
        model = User
        fields = ["id", "email", "name", "phone", "role", "is_active", "date_joined", "password"]
        read_only_fields = ["id", "date_joined"]

    def validate_email(self, value: str) -> str:
        value = value.strip().lower()
        qs = User.objects.filter(email__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate_role(self, value: str) -> str:
        if value not in (Role.ADMIN, Role.STAFF):
            raise serializers.ValidationError("Team members are Admin or Internal staff.")
        return value

    def validate(self, attrs):
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": "A starting password is required."})
        if attrs.get("password"):
            probe = User(email=attrs.get("email", ""), name=attrs.get("name", ""))
            _validate_new_password(attrs["password"], probe)
        return attrs

    def create(self, validated):
        password = validated.pop("password")
        user = User(**validated)
        user.is_staff = False  # Django admin site stays superuser-only
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated):
        password = validated.pop("password", None)
        for key, value in validated.items():
            setattr(instance, key, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class CustomerSerializer(serializers.ModelSerializer):
    has_portal_access = serializers.SerializerMethodField()
    active_subscriptions = serializers.IntegerField(read_only=True, required=False)
    outstanding = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, required=False
    )

    class Meta:
        model = Customer
        fields = [
            "id",
            "name",
            "company",
            "email",
            "phone",
            "address",
            "city",
            "state",
            "country",
            "tax_id",
            "notes",
            "has_portal_access",
            "created_at",
            "active_subscriptions",
            "outstanding",
        ]
        read_only_fields = ["id", "created_at"]

    def get_has_portal_access(self, obj) -> bool:
        return obj.user_id is not None

    def validate_email(self, value: str) -> str:
        value = value.strip().lower()
        qs = Customer.objects.filter(email__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A customer with this email already exists.")
        return value


class CustomerLiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["id", "name", "company", "email"]
