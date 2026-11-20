"""Attachments box on entry screens: purchase orders and goods receipts."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from audit.models import AuditEntry
from core.models import Attachment
from tenancy.context import use_tenant
from tests.test_purchase_orders import (  # noqa: F401  (fixtures)
    HOST,
    buyer,
    call,
    client_for,
    order,
    owner,
    world,
)

pytestmark = [pytest.mark.django_db(databases="__all__"), pytest.mark.usefixtures("hsn_list")]

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


@pytest.fixture
def po(buyer, world):  # noqa: F811
    made = call(
        buyer, "post", f"companies/{world['company']}/purchase-orders/", order(world, submit=True)
    )
    assert made.status_code == 201, made.json()
    return made.json()


def attach(client, record_id, name="challan.pdf", data=PDF, record_type="purchase_order", **more):
    upload = SimpleUploadedFile(name, data, content_type="application/pdf")
    body = {"type": record_type, "id": record_id, "file": upload, **more}
    return client.post("/api/v1/attachments/", body, HTTP_HOST=HOST)


def test_files_are_added_listed_opened_retyped_and_removed(buyer, po, alpha):  # noqa: F811
    added = attach(buyer, po["id"], kind="challan")
    assert added.status_code == 201, added.json()
    row = added.json()
    assert (row["filename"], row["kind_label"], row["added_by_name"]) == (
        "challan.pdf",
        "Supplier's challan",
        "Buyer",
    )
    photo = attach(buyer, po["id"], name="truck.jpg", data=b"\xff\xd8\xff").json()
    assert photo["kind"] == "photo"  # pictures default to Photo

    listed = call(buyer, "get", f"attachments/?type=purchase_order&id={po['id']}").json()
    assert listed["can_change"] is True
    assert [r["filename"] for r in listed["rows"]] == ["challan.pdf", "truck.jpg"]

    opened = call(buyer, "get", f"attachments/{row['id']}/")
    assert opened["Content-Type"] == "application/pdf"
    assert opened["Content-Disposition"].startswith("inline")
    assert b"".join(opened) == PDF

    retyped = call(buyer, "patch", f"attachments/{row['id']}/", {"kind": "invoice"}).json()
    assert retyped["kind_label"] == "Supplier's invoice"
    assert call(buyer, "delete", f"attachments/{photo['id']}/").status_code == 204

    with use_tenant(alpha):
        assert list(Attachment.objects.values_list("filename", flat=True)) == ["challan.pdf"]
        entries = AuditEntry.objects.filter(record_type="purchase_order", record_id=po["id"])
        said = [
            e.changes[0]["new"]
            for e in entries.order_by("id")
            if e.changes and e.changes[0]["field"] == "attachments"
        ]
    assert said == [
        "Added challan.pdf (Supplier's challan)",
        "Added truck.jpg (Photo)",
        "challan.pdf is now Supplier's invoice",
        "Removed truck.jpg",
    ]


def test_wrong_files_are_refused(buyer, po):  # noqa: F811
    assert "PDF, image, Word or Excel" in str(attach(buyer, po["id"], name="run.exe").json())
    big = b"x" * (Attachment.MAX_SIZE + 1)
    assert "over 10 MB" in str(attach(buyer, po["id"], data=big).json())
    assert "Pick a type" in str(attach(buyer, po["id"], kind="secret").json())
    assert attach(buyer, po["id"], record_type="nothing").status_code == 404
    assert attach(buyer, 999999).status_code == 404


def test_roles_decide_who_sees_and_who_changes(alpha, buyer, po):  # noqa: F811
    row = attach(buyer, po["id"]).json()
    store = client_for(alpha, "stores@x.in", "storekeeper")  # sees orders, cannot change them
    listed = call(store, "get", f"attachments/?type=purchase_order&id={po['id']}").json()
    assert (listed["can_change"], len(listed["rows"])) == (False, 1)
    assert attach(store, po["id"]).status_code == 403
    assert call(store, "delete", f"attachments/{row['id']}/").status_code == 403
    sales = client_for(alpha, "sales@x.in", "sales")  # no purchase rights at all
    assert call(sales, "get", f"attachments/?type=purchase_order&id={po['id']}").status_code == 404
    assert call(sales, "get", f"attachments/{row['id']}/").status_code == 404


def test_a_storekeeper_attaches_to_a_goods_receipt(alpha, world, po):  # noqa: F811
    from buying.models import GoodsReceipt

    with use_tenant(alpha):
        draft = GoodsReceipt.objects.create(
            company_id=world["company"],
            branch_id=world["branch"],
            supplier_id=po["supplier"],
            receipt_date=po["order_date"],
        )
    store = client_for(alpha, "stores@x.in", "storekeeper")
    added = attach(store, draft.pk, name="lr.pdf", record_type="goods_receipt", kind="lr")
    assert added.status_code == 201, added.json()
    assert added.json()["kind_label"] == "Lorry receipt (LR)"


def test_a_company_can_need_a_file_before_submit(owner, buyer, world, alpha):  # noqa: F811
    link = f"companies/{world['company']}/"
    shown = call(owner, "get", link).json()["company"]
    assert shown["attachments_required"] == []
    assert [code for code, _ in shown["attachment_types"]] == [
        "purchase_order",
        "goods_receipt",
        "purchase_invoice",
        "purchase_return",
        "debit_note",
        "tds_adjustment",
        "sales_order",
        "pick_list",
        "delivery_note",
        "sales_invoice",
        "credit_note",
    ]
    wrong = call(owner, "patch", link, {"attachments_required": ["sales_return"]})
    assert wrong.status_code == 400 and "Unknown entry type" in str(wrong.json())
    ticked = call(owner, "patch", link, {"attachments_required": ["purchase_order"]})
    assert ticked.status_code == 200 and ticked.json()["attachments_required"] == ["purchase_order"]

    # Submit straight from a new form: refused, but the draft is kept.
    orders = f"companies/{world['company']}/purchase-orders/"
    refused = call(buyer, "post", orders, order(world, submit=True))
    assert refused.status_code == 400
    assert "Add at least one attachment" in refused.json()["attachments"][0]
    draft_id = refused.json()["id"]
    draft = call(buyer, "get", f"purchase-orders/{draft_id}/").json()
    assert draft["status"] == "draft" and not draft["number"]
    # The separate Submit action is refused too.
    assert call(buyer, "post", f"purchase-orders/{draft_id}/submit/").status_code == 400

    assert attach(buyer, draft_id).status_code == 201
    done = call(buyer, "patch", f"purchase-orders/{draft_id}/", order(world, submit=True))
    assert done.status_code == 200, done.json()
    assert done.json()["number"]
    with use_tenant(alpha):
        entry = AuditEntry.objects.filter(
            record_type="company", changes__0__field="attachments_required"
        )
        assert entry.exists()
