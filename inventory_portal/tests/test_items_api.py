"""CRUD, validation, search and auth tests (no external calls)."""


def test_health(client):
    assert client.get("/api/health").get_json() == {"status": "ok"}


def test_create_and_get_item(client):
    resp = client.post("/api/items", json={
        "name": " Milk ", "barcode": "12345678", "quantity": 3, "price": "1.299"})
    assert resp.status_code == 201
    item = resp.get_json()
    assert item["name"] == "Milk"          # trimmed
    assert item["price"] == 1.30           # rounded to 2dp
    got = client.get(f"/api/items/{item['id']}")
    assert got.status_code == 200 and got.get_json()["barcode"] == "12345678"


def test_create_defaults(client):
    item = client.post("/api/items", json={"name": "Bare"}).get_json()
    assert item["quantity"] == 0 and item["price"] == 0


import pytest


@pytest.mark.parametrize("body,fragment", [
    ({}, "name is required"),
    ({"name": ""}, "name"),
    ({"name": "x", "quantity": -1}, "quantity"),
    ({"name": "x", "quantity": 1.5}, "quantity"),
    ({"name": "x", "quantity": True}, "quantity"),
    ({"name": "x", "price": "abc"}, "price"),
    ({"name": "x", "price": -2}, "price"),
    ({"name": "x", "barcode": "12ab"}, "barcode"),
    ({"name": "x", "barcode": "123"}, "barcode"),
    ({"name": "x", "nutriscore": "z"}, "nutriscore"),
])
def test_create_validation(client, body, fragment):
    resp = client.post("/api/items", json=body)
    assert resp.status_code == 400
    assert fragment in resp.get_json()["error"]


def test_create_rejects_non_json(client):
    resp = client.post("/api/items", data="nope", content_type="text/plain")
    assert resp.status_code == 400


def test_duplicate_barcode_conflict(client, make_item):
    make_item(barcode="11111111")
    resp = client.post("/api/items", json={"name": "Other", "barcode": "11111111"})
    assert resp.status_code == 409


def test_unknown_fields_ignored(client):
    item = client.post("/api/items", json={"name": "A", "id": 999, "evil": 1}).get_json()
    assert item["id"] != 999 and "evil" not in item


def test_get_404(client):
    resp = client.get("/api/items/12345")
    assert resp.status_code == 404 and "error" in resp.get_json()


def test_list_search_and_pagination(client, make_item):
    for i in range(5):
        make_item(name=f"Apple {i}", brand="Orchard")
    make_item(name="Bread", brand="Baker")
    all_ = client.get("/api/items").get_json()
    assert all_["total"] == 6
    apples = client.get("/api/items?q=apple").get_json()
    assert apples["total"] == 5
    by_brand = client.get("/api/items?q=baker").get_json()
    assert [i["name"] for i in by_brand["items"]] == ["Bread"]
    page2 = client.get("/api/items?per_page=4&page=2").get_json()
    assert len(page2["items"]) == 2 and page2["pages"] == 2


def test_list_bad_pagination(client):
    assert client.get("/api/items?page=abc").status_code == 400


def test_low_stock_filter(client, make_item):
    make_item(name="Low", quantity=2)
    make_item(name="High", quantity=50)
    data = client.get("/api/items?low_stock=true").get_json()
    assert [i["name"] for i in data["items"]] == ["Low"]


def test_patch_partial_update(client, make_item):
    item = make_item(name="Old", quantity=4, brand="B")
    resp = client.patch(f"/api/items/{item['id']}", json={"quantity": 9})
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["quantity"] == 9 and body["name"] == "Old" and body["brand"] == "B"


def test_put_replaces_item(client, make_item):
    item = make_item(name="Old", brand="B", quantity=4)
    resp = client.put(f"/api/items/{item['id']}", json={"name": "New"})
    body = resp.get_json()
    assert body["name"] == "New" and body["brand"] is None and body["quantity"] == 0


def test_put_requires_name(client, make_item):
    item = make_item()
    assert client.put(f"/api/items/{item['id']}", json={"quantity": 1}).status_code == 400


def test_update_to_duplicate_barcode(client, make_item):
    make_item(barcode="22222222")
    other = make_item(name="B", barcode="33333333")
    resp = client.patch(f"/api/items/{other['id']}", json={"barcode": "22222222"})
    assert resp.status_code == 409


def test_update_404(client):
    assert client.patch("/api/items/9", json={"name": "x"}).status_code == 404


def test_delete(client, make_item):
    item = make_item()
    assert client.delete(f"/api/items/{item['id']}").status_code == 204
    assert client.get(f"/api/items/{item['id']}").status_code == 404
    assert client.delete(f"/api/items/{item['id']}").status_code == 404


def test_api_key_enforced(app):
    app.config["ADMIN_API_KEY"] = "secret"
    c = app.test_client()
    assert c.get("/api/health").status_code == 200          # health stays open
    assert c.get("/api/items").status_code == 401
    assert c.get("/api/items", headers={"X-API-Key": "wrong"}).status_code == 401
    assert c.get("/api/items", headers={"X-API-Key": "secret"}).status_code == 200
