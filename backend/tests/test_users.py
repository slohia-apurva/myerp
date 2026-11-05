"""Users and Roles screens: who may change whom."""

from io import StringIO

import pytest
from django.core.management import call_command
from django.test import Client

from accounts import permissions
from accounts.models import Role, User
from tenancy.context import use_tenant

pytestmark = pytest.mark.django_db(databases="__all__")

HOST = "alpha.localhost"


@pytest.fixture
def as_user(alpha):
    """as_user("owner") -> (client signed in with that role, the user)."""

    def make(*role_codes: str, email: str | None = None):
        with use_tenant(alpha):
            user = User.objects.create_user(email or f"{'-'.join(role_codes) or 'none'}@x.in")
            user.roles.set(Role.objects.filter(code__in=role_codes))
            client = Client()
            client.force_login(user)
        return client, user

    return make


def call(client, method, path, data=None):
    fn = getattr(client, method)
    kwargs = {"HTTP_HOST": HOST}
    if data is not None:
        kwargs.update(data=data, content_type="application/json")
    return fn(f"/api/v1/{path}", **kwargs)


def role_id(alpha, code):
    with use_tenant(alpha):
        return Role.objects.get(code=code).pk


def test_every_tenant_starts_with_standard_roles(alpha):
    with use_tenant(alpha):
        codes = set(Role.objects.values_list("code", flat=True))
    assert {"owner", "accountant", "sales", "purchase", "storekeeper", "viewer"} <= codes


def test_standard_roles_use_only_known_permissions(alpha):
    with use_tenant(alpha):
        for perms in Role.objects.values_list("permissions", flat=True):
            assert set(perms) <= permissions.ALL


def test_owner_can_do_everything_viewer_cannot_manage(alpha, as_user):
    _, owner = as_user("owner")
    _, viewer = as_user("viewer")
    with use_tenant(alpha):
        assert owner.permission_codes() == permissions.ALL
        assert viewer.can("sales.view") and not viewer.can("sales.create")
        assert not viewer.can("users.manage")


def test_session_lists_permissions(as_user):
    client, _ = as_user("accountant")
    state = client.get("/api/auth/session/", HTTP_HOST=HOST).json()
    assert "accounts.submit" in state["permissions"]
    assert "users.manage" not in state["permissions"]
    assert state["user"]["is_owner"] is False


def test_users_screen_needs_users_manage(as_user):
    client, _ = as_user("accountant")
    assert call(client, "get", "users/").status_code == 403


def test_owner_adds_a_user_with_roles(alpha, as_user):
    client, _ = as_user("owner")
    response = call(
        client,
        "post",
        "users/",
        {"email": " New@Apurva.org.in ", "full_name": "New", "roles": [role_id(alpha, "sales")]},
    )
    assert response.status_code == 201, response.json()
    assert response.json()["email"] == "new@apurva.org.in"
    with use_tenant(alpha):
        assert User.objects.get(email="new@apurva.org.in").can("sales.create")


def test_adding_the_same_email_twice_is_refused(alpha, as_user):
    client, _ = as_user("owner")
    body = {"email": "dup@x.in", "roles": []}
    assert call(client, "post", "users/", body).status_code == 201
    assert call(client, "post", "users/", body).status_code == 400


def test_only_owner_can_make_an_owner(alpha, as_user):
    with use_tenant(alpha):
        admin_role = Role.objects.create(code="admin", name="Admin", permissions=["users.manage"])
    client, _ = as_user("admin")
    body = {"email": "boss@x.in", "roles": [role_id(alpha, "owner")]}
    assert call(client, "post", "users/", body).status_code == 403
    # ...and cannot promote someone, or themselves, to Owner later either.
    _, other = as_user("viewer")
    response = call(client, "patch", f"users/{other.pk}/", {"roles": [role_id(alpha, "owner")]})
    assert response.status_code == 403
    assert admin_role.pk


def test_non_owner_cannot_change_an_owner(alpha, as_user):
    with use_tenant(alpha):
        Role.objects.create(code="admin", name="Admin", permissions=["users.manage"])
    _, owner = as_user("owner")
    client, _ = as_user("admin")
    response = call(client, "patch", f"users/{owner.pk}/", {"is_active": False})
    assert response.status_code == 403


def test_last_owner_cannot_be_removed(alpha, as_user):
    client, owner = as_user("owner")
    response = call(client, "patch", f"users/{owner.pk}/", {"roles": [role_id(alpha, "viewer")]})
    assert response.status_code == 400
    # With a second owner, it is allowed.
    _, second = as_user("owner", email="second@x.in")
    response = call(client, "patch", f"users/{owner.pk}/", {"roles": [role_id(alpha, "viewer")]})
    assert response.status_code == 200
    with use_tenant(alpha):
        assert second.is_owner and not User.objects.get(pk=owner.pk).is_owner


def test_nobody_can_deactivate_themselves(as_user):
    client, owner = as_user("owner")
    _, _second = as_user("owner", email="second@x.in")
    response = call(client, "patch", f"users/{owner.pk}/", {"is_active": False})
    assert response.status_code == 400


def test_deactivated_user_loses_everything(alpha, as_user):
    client, _ = as_user("owner")
    sales_client, sales = as_user("sales")
    assert call(client, "patch", f"users/{sales.pk}/", {"is_active": False}).status_code == 200
    with use_tenant(alpha):
        assert User.objects.get(pk=sales.pk).permission_codes() == frozenset()
    assert sales_client.get("/api/whoami/", HTTP_HOST=HOST).status_code == 403


def test_email_cannot_be_changed(as_user):
    client, _ = as_user("owner")
    _, other = as_user("viewer")
    response = call(client, "patch", f"users/{other.pk}/", {"email": "else@x.in"})
    assert response.status_code == 400


def test_owner_creates_edits_and_deletes_a_custom_role(alpha, as_user):
    client, _ = as_user("owner")
    created = call(
        client, "post", "roles/", {"name": "Dispatch clerk", "permissions": ["stock.view"]}
    )
    assert created.status_code == 201
    rid = created.json()["id"]
    assert created.json()["code"] == "dispatch-clerk"

    edited = call(client, "patch", f"roles/{rid}/", {"permissions": ["stock.view", "sales.view"]})
    assert edited.json()["permissions"] == ["sales.view", "stock.view"]
    assert call(client, "delete", f"roles/{rid}/").status_code == 204


def test_unknown_permission_is_refused(as_user):
    client, _ = as_user("owner")
    response = call(client, "post", "roles/", {"name": "X", "permissions": ["root.everything"]})
    assert response.status_code == 400


def test_owner_role_and_standard_roles_are_protected(alpha, as_user):
    client, _ = as_user("owner")
    owner_id = role_id(alpha, "owner")
    assert call(client, "patch", f"roles/{owner_id}/", {"permissions": []}).status_code == 400
    assert call(client, "delete", f"roles/{role_id(alpha, 'viewer')}/").status_code == 400


def test_role_in_use_cannot_be_deleted(alpha, as_user):
    client, _ = as_user("owner")
    rid = call(client, "post", "roles/", {"name": "Temp", "permissions": []}).json()["id"]
    as_user("temp")
    assert call(client, "delete", f"roles/{rid}/").status_code == 400


def test_only_owner_edits_roles(alpha, as_user):
    with use_tenant(alpha):
        Role.objects.create(code="admin", name="Admin", permissions=["users.manage"])
    client, _ = as_user("admin")
    assert call(client, "get", "roles/").status_code == 200
    rid = role_id(alpha, "viewer")
    assert call(client, "patch", f"roles/{rid}/", {"permissions": []}).status_code == 403


def test_roles_belong_to_their_tenant(alpha, beta, as_user):
    client, _ = as_user("owner")
    call(client, "post", "roles/", {"name": "Alpha only", "permissions": []})
    with use_tenant(beta):
        assert not Role.objects.filter(name="Alpha only").exists()


def test_create_tenant_user_gives_roles(alpha):
    call_command("create_tenant_user", "alpha", "admin@x.in", "--role", "owner", stdout=StringIO())
    with use_tenant(alpha):
        assert User.objects.get(email="admin@x.in").is_owner
