import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app  # noqa: E402
from app.config import TestConfig  # noqa: E402
from app.models import db  # noqa: E402


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def make_item(client):
    def _make(**overrides):
        body = {"name": "Test Item", "quantity": 10, "price": 2.5, **overrides}
        resp = client.post("/api/items", json=body)
        assert resp.status_code == 201, resp.get_json()
        return resp.get_json()
    return _make


# Sample OpenFoodFacts payloads
OFF_NUTELLA = {
    "status": 1,
    "product": {
        "code": "3017620422003",
        "product_name": "Nutella",
        "brands": "Ferrero, Nutella",
        "categories": "Spreads, Sweet spreads",
        "generic_name": "Hazelnut spread with cocoa",
        "ingredients_text": "Sugar, palm oil, hazelnuts",
        "image_url": "https://images.example/nutella.jpg",
        "nutriscore_grade": "E",
    },
}


class FakeResponse:
    def __init__(self, payload=None, status=200):
        self._payload, self.status_code = payload, status

    def raise_for_status(self):
        import requests
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload
