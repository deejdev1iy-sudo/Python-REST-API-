from decimal import Decimal, InvalidOperation

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from .models import Item, db
from .off_client import OFFError, OFFNotFound, OpenFoodFactsClient

api = Blueprint("api", __name__, url_prefix="/api")


# ---------- helpers ----------
def error(message, status):
    return jsonify({"error": message}), status


def off_client():
    cfg = current_app.config
    return OpenFoodFactsClient(
        cfg["OFF_BASE_URL"], cfg["OFF_TIMEOUT"], cfg["OFF_USER_AGENT"]
    )


def validate(data, partial=False):
    """Return (clean_dict, error_message). Only WRITABLE keys are kept."""
    if not isinstance(data, dict):
        return None, "Request body must be a JSON object"
    clean = {k: data[k] for k in Item.WRITABLE if k in data}

    if "name" in clean:
        if not isinstance(clean["name"], str) or not clean["name"].strip():
            return None, "name must be a non-empty string"
        clean["name"] = clean["name"].strip()
    elif not partial:
        return None, "name is required"

    if "quantity" in clean:
        q = clean["quantity"]
        if isinstance(q, bool) or not isinstance(q, int) or q < 0:
            return None, "quantity must be a non-negative integer"

    if "price" in clean:
        raw = clean["price"]
        try:
            if isinstance(raw, bool):
                raise InvalidOperation
            p = Decimal(str(raw))
            if not p.is_finite() or p < 0:
                raise InvalidOperation
            clean["price"] = p.quantize(Decimal("0.01"))
        except InvalidOperation:
            return None, "price must be a non-negative number"

    if clean.get("barcode") is not None:
        b = str(clean["barcode"]).strip()
        if not b.isdigit() or not 8 <= len(b) <= 14:
            return None, "barcode must be 8-14 digits"
        clean["barcode"] = b
    elif "barcode" in clean:
        clean["barcode"] = None  # allow clearing

    if clean.get("nutriscore") is not None:
        n = str(clean["nutriscore"]).lower()
        if n not in ("a", "b", "c", "d", "e"):
            return None, "nutriscore must be one of a, b, c, d, e"
        clean["nutriscore"] = n
    return clean, None


def enrich_values(barcode=None, name=None):
    """Fetch OFF data; returns dict. Raises OFFError / OFFNotFound."""
    client = off_client()
    if barcode:
        return client.by_barcode(barcode)
    return client.by_name(name, limit=1)[0]


def commit():
    """Commit; return an error response on duplicate barcode, else None."""
    try:
        db.session.commit()
        return None
    except IntegrityError:
        db.session.rollback()
        return error("An item with this barcode already exists", 409)


# ---------- auth / errors ----------
@api.before_request
def require_api_key():
    key = current_app.config.get("ADMIN_API_KEY")
    if key and request.endpoint != "api.health":
        if request.headers.get("X-API-Key") != key:
            return error("Invalid or missing API key", 401)


@api.errorhandler(OFFError)
def handle_off_error(exc):
    return error(str(exc), 502)


@api.errorhandler(ValueError)
def handle_value_error(exc):
    return error(str(exc), 400)


# ---------- routes ----------
@api.get("/health")
def health():
    return jsonify({"status": "ok"})


@api.get("/items")
def list_items():
    q = Item.query
    search = request.args.get("q", "").strip()
    if search:
        like = f"%{search}%"
        q = q.filter(or_(Item.name.ilike(like), Item.brand.ilike(like),
                         Item.barcode.ilike(like), Item.category.ilike(like)))
    if request.args.get("low_stock", "").lower() in ("1", "true", "yes"):
        q = q.filter(Item.quantity <= current_app.config["LOW_STOCK_THRESHOLD"])

    try:
        page = max(int(request.args.get("page", 1)), 1)
        per_page = min(max(int(request.args.get("per_page", 20)), 1), 100)
    except ValueError:
        return error("page and per_page must be integers", 400)

    result = q.order_by(Item.id).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "items": [i.to_dict() for i in result.items],
        "page": page, "per_page": per_page,
        "total": result.total, "pages": result.pages,
    })


@api.post("/items")
def create_item():
    data = request.get_json(silent=True)
    clean, err = validate(data)
    if err:
        return error(err, 400)

    if data.get("enrich"):
        # Supplement only fields the client left empty; client values win.
        try:
            fetched = enrich_values(clean.get("barcode"), clean.get("name"))
        except OFFNotFound:
            fetched = {}  # item is still created, just without extra details
        for k, v in fetched.items():
            if v is not None and clean.get(k) in (None, ""):
                clean[k] = v

    item = Item(**clean)
    db.session.add(item)
    failed = commit()
    if failed:
        return failed
    return jsonify(item.to_dict()), 201


@api.get("/items/<int:item_id>")
def get_item(item_id):
    return jsonify(db.get_or_404(Item, item_id).to_dict())


@api.route("/items/<int:item_id>", methods=["PUT", "PATCH"])
def update_item(item_id):
    item = db.get_or_404(Item, item_id)
    data = request.get_json(silent=True)
    # PUT replaces (name required); PATCH is partial.
    clean, err = validate(data, partial=request.method == "PATCH")
    if err:
        return error(err, 400)
    if request.method == "PUT":
        for field in Item.WRITABLE:
            if field not in clean:
                clean[field] = 0 if field in ("quantity", "price") else None
    for k, v in clean.items():
        setattr(item, k, v)
    failed = commit()
    return failed or jsonify(item.to_dict())


@api.delete("/items/<int:item_id>")
def delete_item(item_id):
    item = db.get_or_404(Item, item_id)
    db.session.delete(item)
    db.session.commit()
    return "", 204


@api.post("/items/<int:item_id>/enrich")
def enrich_item(item_id):
    """Fill in missing details from OpenFoodFacts. ?overwrite=true replaces all."""
    item = db.get_or_404(Item, item_id)
    overwrite = request.args.get("overwrite", "").lower() in ("1", "true", "yes")
    try:
        fetched = enrich_values(item.barcode, None if item.barcode else item.name)
    except OFFNotFound as exc:
        return error(str(exc), 404)
    for k, v in fetched.items():
        if k == "barcode" and item.barcode:
            continue
        if v is not None and (overwrite or getattr(item, k) in (None, "")):
            setattr(item, k, v)
    failed = commit()
    return failed or jsonify(item.to_dict())


@api.get("/products/lookup")
def lookup_product():
    barcode = request.args.get("barcode")
    name = request.args.get("name")
    if not barcode and not name:
        return error("Provide either 'barcode' or 'name'", 400)
    try:
        if barcode:
            return jsonify({"products": [off_client().by_barcode(barcode)]})
        return jsonify({"products": off_client().by_name(name)})
    except OFFNotFound as exc:
        return error(str(exc), 404)
