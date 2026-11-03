"""Thin client for the OpenFoodFacts API (https://world.openfoodfacts.org)."""
import requests

FIELDS = (
    "code,product_name,brands,categories,generic_name,"
    "ingredients_text,image_url,nutriscore_grade"
)


class OFFError(Exception):
    """The external service failed (network error, timeout, bad response)."""


class OFFNotFound(Exception):
    """The external service has no matching product."""


def normalize(raw):
    """Map an OpenFoodFacts product to our inventory field names."""
    brand = (raw.get("brands") or "").split(",")[0].strip() or None
    category = (raw.get("categories") or "").split(",")[0].strip() or None
    grade = (raw.get("nutriscore_grade") or "").strip().lower()
    return {
        "barcode": raw.get("code") or None,
        "name": (raw.get("product_name") or "").strip() or None,
        "brand": brand,
        "category": category,
        "description": (raw.get("generic_name") or "").strip() or None,
        "ingredients": (raw.get("ingredients_text") or "").strip() or None,
        "image_url": raw.get("image_url") or None,
        "nutriscore": grade if grade in ("a", "b", "c", "d", "e") else None,
    }


class OpenFoodFactsClient:
    def __init__(self, base_url, timeout=8, user_agent="InventoryAdminPortal/1.0"):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = {"User-Agent": user_agent}

    def _get(self, url, params=None):
        try:
            resp = requests.get(
                url, params=params, headers=self.headers, timeout=self.timeout
            )
            resp.raise_for_status()
            return resp.json()
        except requests.Timeout as exc:
            raise OFFError("OpenFoodFacts request timed out") from exc
        except requests.RequestException as exc:
            raise OFFError(f"OpenFoodFacts request failed: {exc}") from exc
        except ValueError as exc:
            raise OFFError("OpenFoodFacts returned invalid JSON") from exc

    def by_barcode(self, barcode):
        barcode = str(barcode).strip()
        if not barcode.isdigit():
            raise ValueError("barcode must contain digits only")
        data = self._get(
            f"{self.base_url}/api/v2/product/{barcode}.json", {"fields": FIELDS}
        )
        if data.get("status") != 1 or not data.get("product"):
            raise OFFNotFound(f"No product found for barcode {barcode}")
        product = data["product"]
        product.setdefault("code", barcode)
        return normalize(product)

    def by_name(self, name, limit=5):
        name = (name or "").strip()
        if not name:
            raise ValueError("name must not be empty")
        data = self._get(
            f"{self.base_url}/cgi/search.pl",
            {
                "search_terms": name, "search_simple": 1, "action": "process",
                "json": 1, "page_size": limit, "fields": FIELDS,
            },
        )
        products = data.get("products") or []
        if not products:
            raise OFFNotFound(f"No products found matching '{name}'")
        return [normalize(p) for p in products]
