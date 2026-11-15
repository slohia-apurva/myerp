"""Users and Roles screens.

Who may do what:
- Anyone with `users.manage` can add people, change their roles and companies,
  and deactivate them.
- Only an Owner can make someone an Owner, change an Owner's access, or edit
  roles, because those decide what everyone else may do.
- The last active Owner cannot be removed, and nobody can deactivate themselves.
"""

from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import permissions
from accounts.models import Role, User
from accounts.roles import OWNER
from core import duplicates
from core.models import Company
from tenancy.context import tenant_atomic

OWNER_ONLY = "Only an Owner can do this."


def _active_owner_count(exclude: User | None = None) -> int:
    owners = User.objects.filter(is_active=True, roles__code=OWNER)
    if exclude is not None:
        owners = owners.exclude(pk=exclude.pk)
    return owners.distinct().count()


class RoleSerializer(serializers.ModelSerializer):
    user_count = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = [
            "id",
            "code",
            "name",
            "description",
            "permissions",
            "is_standard",
            "is_active",
            "user_count",
        ]
        read_only_fields = ["code", "is_standard"]

    def get_user_count(self, role) -> int:
        return role.users.filter(is_active=True).count()

    def validate_permissions(self, value):
        try:
            return permissions.clean(value)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc


class UserSerializer(serializers.ModelSerializer):
    roles = serializers.PrimaryKeyRelatedField(many=True, queryset=Role.objects.all())
    companies = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Company.objects.all(), required=False
    )
    signed_in_before = serializers.SerializerMethodField()
    signature = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "full_name",
            "phone",
            "signature",
            "is_active",
            "roles",
            "companies",
            "last_login",
            "signed_in_before",
        ]
        read_only_fields = ["last_login"]

    def get_signed_in_before(self, user) -> bool:
        return bool(user.google_sub)

    def get_signature(self, user) -> str:
        return user.signature_url()

    def validate_email(self, value):
        value = value.strip().lower()
        if self.instance is not None and value != self.instance.email:
            raise ValidationError("An email address cannot be changed; add a new user instead.")
        return value


def _ids(qs) -> set[int]:
    return set(qs.values_list("pk", flat=True))


class UserListView(APIView):
    permission_classes = [permissions.requires("users.manage")]

    def get(self, request):
        users = User.objects.prefetch_related("roles", "companies")
        return Response(UserSerializer(users, many=True).data)

    @tenant_atomic()
    def post(self, request):
        serializer = UserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        roles = serializer.validated_data["roles"]
        _refuse_disabled(roles)
        if any(r.code == OWNER for r in roles) and not request.user.is_owner:
            raise PermissionDenied(OWNER_ONLY)
        clash = User.objects.filter(email__iexact=serializer.validated_data["email"]).first()
        if clash is not None:
            duplicates.refuse(
                "email", "This person is already a user.", clash, "user", name=clash.email
            )
        user = User.objects.create_user(
            email=serializer.validated_data["email"],
            full_name=serializer.validated_data.get("full_name", ""),
        )
        if serializer.validated_data.get("phone"):
            user.phone = serializer.validated_data["phone"]
            user.save(update_fields=["phone"])
        user.roles.set(roles)
        user.companies.set(serializer.validated_data.get("companies", []))
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class UserDetailView(APIView):
    permission_classes = [permissions.requires("users.manage")]

    @tenant_atomic()
    def patch(self, request, pk: int):
        user = User.objects.select_for_update().filter(pk=pk).first()
        if user is None:
            return Response({"detail": "No such user."}, status=status.HTTP_404_NOT_FOUND)
        serializer = UserSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        was_owner = user.is_owner
        new_roles = data.get("roles")
        if new_roles is not None:
            _refuse_disabled([r for r in new_roles if r not in user.roles.all()])
        becomes_owner = (
            any(r.code == OWNER for r in new_roles) if new_roles is not None else was_owner
        )
        if (was_owner or becomes_owner) and not request.user.is_owner:
            raise PermissionDenied(OWNER_ONLY)
        if user.pk == request.user.pk and data.get("is_active") is False:
            raise ValidationError({"is_active": ["You cannot deactivate yourself."]})
        stays_active_owner = becomes_owner and data.get("is_active", user.is_active)
        if was_owner and not stays_active_owner and _active_owner_count(exclude=user) == 0:
            raise ValidationError({"roles": ["There must always be at least one active Owner."]})

        for field in ("full_name", "phone", "is_active"):
            if field in data:
                setattr(user, field, data[field])
        user.save()
        if new_roles is not None:
            user.roles.set(new_roles)
        if "companies" in data:
            user.companies.set(data["companies"])
        return Response(UserSerializer(user).data)


SIGNATURE_MAX = 300 * 1024
SIGNATURE_TYPES = {b"\x89PNG\r\n\x1a\n": "image/png", b"\xff\xd8\xff": "image/jpeg"}


class SignatureView(APIView):
    """Upload or remove a person's signature. Only the person themselves or an
    Owner may, since it is printed as their approval on documents."""

    parser_classes = [MultiPartParser]

    def _user(self, request, pk: int) -> User:
        user = User.objects.filter(pk=pk).first()
        if user is None:
            raise NotFound("No such user.")
        if user.pk != request.user.pk and not request.user.is_owner:
            raise PermissionDenied("Only the person themselves or an Owner can change a signature.")
        return user

    @tenant_atomic()
    def post(self, request, pk: int):
        user = self._user(request, pk)
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": ["Choose an image of the signature."]})
        if upload.size > SIGNATURE_MAX:
            too_big = "The image is over 300 KB; crop it or save it smaller."
            raise ValidationError({"file": [too_big]})
        data = upload.read()
        kind = next((t for magic, t in SIGNATURE_TYPES.items() if data.startswith(magic)), "")
        if not kind:
            raise ValidationError({"file": ["Upload a PNG or JPG image."]})
        user.signature = data
        user.signature_type = kind
        user.save(update_fields=["signature", "signature_type"])
        return Response(UserSerializer(user).data)

    @tenant_atomic()
    def delete(self, request, pk: int):
        user = self._user(request, pk)
        user.signature = None
        user.signature_type = ""
        user.save(update_fields=["signature", "signature_type"])
        return Response(UserSerializer(user).data)


class RoleListView(APIView):
    def get_permissions(self):
        return [permissions.requires("users.manage")()]

    def get(self, request):
        return Response(
            {
                "roles": RoleSerializer(Role.objects.all(), many=True).data,
                "catalogue": permissions.catalogue(),
            }
        )

    def post(self, request):
        if not request.user.is_owner:
            raise PermissionDenied(OWNER_ONLY)
        serializer = RoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        name = duplicates.tidy(serializer.validated_data["name"])
        _unique_role_name(name)
        role = serializer.save(name=name, code=_unique_code(name), is_standard=False)
        return Response(RoleSerializer(role).data, status=status.HTTP_201_CREATED)


class RoleDetailView(APIView):
    def get_permissions(self):
        return [permissions.requires("users.manage")()]

    def _editable(self, request, pk) -> Role:
        if not request.user.is_owner:
            raise PermissionDenied(OWNER_ONLY)
        role = Role.objects.filter(pk=pk).first()
        if role is None:
            raise ValidationError({"detail": "No such role."})
        if role.is_owner:
            raise ValidationError({"detail": "The Owner role cannot be changed."})
        return role

    def patch(self, request, pk: int):
        role = self._editable(request, pk)
        serializer = RoleSerializer(role, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        extra = {}
        if "name" in serializer.validated_data:
            extra["name"] = duplicates.tidy(serializer.validated_data["name"])
            _unique_role_name(extra["name"], exclude=role.pk)
        if serializer.validated_data.get("is_active") is False and role.is_active:
            if role.is_standard:
                raise ValidationError({"detail": "Standard roles can be edited but not disabled."})
            if role.users.filter(is_active=True).exists():
                raise ValidationError({"detail": "Take this role off its users first."})
        serializer.save(**extra)
        return Response(serializer.data)


def _refuse_disabled(roles) -> None:
    off = [r.name for r in roles if not r.is_active]
    if off:
        raise ValidationError({"roles": [f"The role {off[0]} is disabled."]})


def _unique_role_name(name: str, exclude: int | None = None) -> None:
    duplicates.check_name(
        Role.objects.all(),
        name,
        exclude=exclude,
        kind="role",
        message='There is already a role named "{name}".',
    )


def _unique_code(name: str) -> str:
    from django.utils.text import slugify

    base = slugify(name)[:40] or "role"
    code, n = base, 2
    while Role.objects.filter(code=code).exists():
        code, n = f"{base}-{n}", n + 1
    return code
