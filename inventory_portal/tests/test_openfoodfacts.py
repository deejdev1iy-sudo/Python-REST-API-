"""External API integration tests. requests.get is always mocked."""
from unittest.mock import patch

import pytest
import requests

from app.off_client import OFFError, OFFNotFound, OpenFoodFactsClient, normalize
from tests.conftest import OFF_NUTELLA, FakeResponse

GET = "app.off_client.requests.get"


# ----- client unit tests -----
def test_normalize_maps_fields():
    n = normalize(OFF_NUTELLA["product"])
    assert n["name"] == "Nutella" and n["brand"] == "Ferrero"
    assert n["category"] == "Spreads" and n["nutriscore"] == "e"


def test_normalize_handles_missing_and_bad_values():
    n = normalize({"code": "1", "nutriscore_grade": "unknown", "product_name": "  "})
    assert n["name"] is None and n["nutriscore"] is None and n["brand"] is None


def test_by_barcode_success_and_request_shape():
    c = OpenFoodFactsClient("https://off.test/", timeout=3, user_agent="UA")
    with patch(GET, return_value=FakeResponse(OFF_NUTELLA)) as m:
        result = c.by_barcode("3017620422003")
    assert result["name"] == "Nutella"
    args, kwargs = m.call_args
    assert args[0] == "https://off.test/api/v2/product/3017620422003.json"
    assert kwargs["timeout"] == 3 and kwargs["headers"]["User-Agent"] == "UA"


def test_by_barcode_not_found():
    c = OpenFoodFactsClient("https://off.test")
    with patch(GET, return_value=FakeResponse({"status": 0})):
        with pytest.raises(OFFNotFound):
            c.by_barcode("00000000")


def test_by_barcode_rejects_non_digits():
    with pytest.raises(ValueError):
        OpenFoodFactsClient("https://off.test").by_barcode("abc; drop")


@pytest.mark.parametrize("side_effect,msg", [
    (requests.Timeout(), "timed out"),
    (requests.ConnectionError("boom"), "failed"),
])
def test_network_errors_become_offerror(side_effect, msg):
    with patch(GET, side_effect=side_effect):
        with pytest.raises(OFFError, match=msg):
            OpenFoodFactsClient("https://off.test").by_barcode("12345678")


def test_http_error_and_bad_json():
    c = OpenFoodFactsClient("https://off.test")
    with patch(GET, return_value=FakeResponse({}, status=503)):
        with pytest.raises(OFFError):
            c.by_barcode("12345678")
    with patch(GET, return_value=FakeResponse(ValueError("bad"))):
        with pytest.raises(OFFError, match="invalid JSON"):
            c.by_barcode("12345678")


def test_by_name_success_and_empty():
    c = OpenFoodFactsClient("https://off.test")
    with patch(GET, return_value=FakeResponse({"products": [OFF_NUTELLA["product"]]})) as m:
        res = c.by_name("nutella", limit=1)
    assert res[0]["name"] == "Nutella"
    assert m.call_args.kwargs["params"]["search_terms"] == "nutella"
    with patch(GET, return_value=FakeResponse({"products": []})):
        with pytest.raises(OFFNotFound):
            c.by_name("zzzz")
    with pytest.raises(ValueError):
        c.by_name("   ")


# ----- API endpoint integration -----
def test_lookup_by_barcode(client):
    with patch(GET, return_value=FakeResponse(OFF_NUTELLA)):
        resp = client.get("/api/products/lookup?barcode=3017620422003")
    assert resp.status_code == 200
    assert resp.get_json()["products"][0]["brand"] == "Ferrero"


def test_lookup_by_name(client):
    with patch(GET, return_value=FakeResponse({"products": [OFF_NUTELLA["product"]]})):
        resp = client.get("/api/products/lookup?name=nutella")
    assert resp.status_code == 200 and len(resp.get_json()["products"]) == 1


def test_lookup_requires_param(client):
    assert client.get("/api/products/lookup").status_code == 400


def test_lookup_invalid_barcode_is_400(client):
    assert client.get("/api/products/lookup?barcode=abc").status_code == 400


def test_lookup_not_found_404(client):
    with patch(GET, return_value=FakeResponse({"status": 0})):
        assert client.get("/api/products/lookup?barcode=99999999").status_code == 404


def test_lookup_upstream_failure_502(client):
    with patch(GET, side_effect=requests.Timeout()):
        resp = client.get("/api/products/lookup?barcode=12345678")
    assert resp.status_code == 502 and "timed out" in resp.get_json()["error"]


def test_create_with_enrich_fills_gaps_but_keeps_user_values(client):
    with patch(GET, return_value=FakeResponse(OFF_NUTELLA)):
        resp = client.post("/api/items", json={
            "name": "Our Nutella Jar", "barcode": "3017620422003",
            "price": 4.99, "quantity": 12, "enrich": True})
    item = resp.get_json()
    assert resp.status_code == 201
    assert item["name"] == "Our Nutella Jar"      # user value wins
    assert item["brand"] == "Ferrero"             # gap filled
    assert item["nutriscore"] == "e" and item["image_url"].endswith("nutella.jpg")


def test_create_with_enrich_not_found_still_creates(client):
    with patch(GET, return_value=FakeResponse({"status": 0})):
        resp = client.post("/api/items", json={
            "name": "Mystery", "barcode": "99999999", "enrich": True})
    assert resp.status_code == 201 and resp.get_json()["brand"] is None


def test_create_with_enrich_upstream_failure_502_and_nothing_saved(client):
    with patch(GET, side_effect=requests.ConnectionError("down")):
        resp = client.post("/api/items", json={
            "name": "X", "barcode": "12345678", "enrich": True})
    assert resp.status_code == 502
    assert client.get("/api/items").get_json()["total"] == 0


def test_enrich_existing_item_fills_only_blanks(client, make_item):
    item = make_item(name="My Name", barcode="3017620422003", brand="Custom")
    with patch(GET, return_value=FakeResponse(OFF_NUTELLA)):
        body = client.post(f"/api/items/{item['id']}/enrich").get_json()
    assert body["name"] == "My Name" and body["brand"] == "Custom"
    assert body["category"] == "Spreads"


def test_enrich_overwrite(client, make_item):
    item = make_item(name="My Name", barcode="3017620422003")
    with patch(GET, return_value=FakeResponse(OFF_NUTELLA)):
        body = client.post(f"/api/items/{item['id']}/enrich?overwrite=true").get_json()
    assert body["name"] == "Nutella"


def test_enrich_by_name_when_no_barcode(client, make_item):
    item = make_item(name="Nutella")
    with patch(GET, return_value=FakeResponse({"products": [OFF_NUTELLA["product"]]})):
        body = client.post(f"/api/items/{item['id']}/enrich").get_json()
    assert body["brand"] == "Ferrero"
    assert body["barcode"] == "3017620422003"


def test_enrich_missing_item_and_not_found(client, make_item):
    assert client.post("/api/items/99/enrich").status_code == 404
    item = make_item(barcode="99999999")
    with patch(GET, return_value=FakeResponse({"status": 0})):
        assert client.post(f"/api/items/{item['id']}/enrich").status_code == 404
