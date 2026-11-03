#!/usr/bin/env python3
"""Command-line admin interface for the inventory API.

Environment:
  INVENTORY_API_URL  base URL of the API (default http://127.0.0.1:5000)
  ADMIN_API_KEY      sent as X-API-Key when set
"""
import argparse
import json
import os
import sys

import requests


class ApiClient:
    def __init__(self, base_url, api_key=None, session=None, timeout=15):
        self.base_url = base_url.rstrip("/")
        self.headers = {"X-API-Key": api_key} if api_key else {}
        self.session = session or requests.Session()
        self.timeout = timeout

    def request(self, method, path, params=None, body=None):
        """Return (status_code, parsed_json_or_None)."""
        resp = self.session.request(
            method, f"{self.base_url}{path}", params=params, json=body,
            headers=self.headers, timeout=self.timeout,
        )
        try:
            payload = resp.json() if resp.content else None
        except ValueError:
            payload = {"error": resp.text.strip() or "Unexpected response"}
        return resp.status_code, payload


# ---------- output ----------
def fmt_table(items):
    if not items:
        return "No items found."
    cols = [("ID", "id", 5), ("BARCODE", "barcode", 15), ("NAME", "name", 32),
            ("BRAND", "brand", 18), ("QTY", "quantity", 5), ("PRICE", "price", 9)]
    def cell(item, key, width):
        v = item.get(key)
        v = "" if v is None else (f"{v:.2f}" if key == "price" else str(v))
        return (v[: width - 1] + "…") if len(v) > width else v
    header = "  ".join(f"{t:<{w}}" for t, _, w in cols)
    lines = [header, "-" * len(header)]
    for it in items:
        lines.append("  ".join(f"{cell(it, k, w):<{w}}" for _, k, w in cols))
    return "\n".join(lines)


def fmt_item(item):
    return "\n".join(f"{k:>12}: {v}" for k, v in item.items() if v not in (None, ""))


def emit(args, data, human):
    print(json.dumps(data, indent=2) if args.json else human)


# ---------- commands ----------
def cmd_list(api, args):
    params = {"page": args.page, "per_page": args.per_page}
    if args.search:
        params["q"] = args.search
    if args.low_stock:
        params["low_stock"] = "true"
    status, data = api.request("GET", "/api/items", params=params)
    if status != 200:
        return fail(data, status)
    human = fmt_table(data["items"]) + (
        f"\n\nPage {data['page']}/{max(data['pages'], 1)} — {data['total']} item(s)"
    )
    emit(args, data, human)
    return 0


def cmd_get(api, args):
    status, data = api.request("GET", f"/api/items/{args.id}")
    if status != 200:
        return fail(data, status)
    emit(args, data, fmt_item(data))
    return 0


def item_body(args, include_none=False):
    fields = ("name", "barcode", "brand", "category", "description",
              "quantity", "price", "image_url", "ingredients", "nutriscore")
    body = {f: getattr(args, f, None) for f in fields}
    return body if include_none else {k: v for k, v in body.items() if v is not None}


def cmd_add(api, args):
    body = item_body(args)
    if args.enrich:
        body["enrich"] = True
    status, data = api.request("POST", "/api/items", body=body)
    if status != 201:
        return fail(data, status)
    emit(args, data, "Created item:\n" + fmt_item(data))
    return 0


def cmd_update(api, args):
    body = item_body(args)
    if not body:
        print("Nothing to update: supply at least one field option.", file=sys.stderr)
        return 2
    status, data = api.request("PATCH", f"/api/items/{args.id}", body=body)
    if status != 200:
        return fail(data, status)
    emit(args, data, "Updated item:\n" + fmt_item(data))
    return 0


def cmd_delete(api, args):
    if not args.yes:
        answer = input(f"Delete item {args.id}? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Cancelled.")
            return 1
    status, data = api.request("DELETE", f"/api/items/{args.id}")
    if status != 204:
        return fail(data, status)
    print(f"Deleted item {args.id}.")
    return 0


def cmd_lookup(api, args):
    params = {"barcode": args.barcode} if args.barcode else {"name": args.name}
    status, data = api.request("GET", "/api/products/lookup", params=params)
    if status != 200:
        return fail(data, status)
    human = "\n\n".join(fmt_item(p) for p in data["products"])
    emit(args, data, human)
    return 0


def cmd_enrich(api, args):
    params = {"overwrite": "true"} if args.overwrite else None
    status, data = api.request("POST", f"/api/items/{args.id}/enrich", params=params)
    if status != 200:
        return fail(data, status)
    emit(args, data, "Enriched item:\n" + fmt_item(data))
    return 0


def fail(data, status):
    msg = (data or {}).get("error", "Request failed")
    print(f"Error ({status}): {msg}", file=sys.stderr)
    return 1


# ---------- parser ----------
def add_item_fields(p, required_name=False):
    p.add_argument("--name", required=required_name)
    p.add_argument("--barcode")
    p.add_argument("--brand")
    p.add_argument("--category")
    p.add_argument("--description")
    p.add_argument("--quantity", type=int)
    p.add_argument("--price", type=float)
    p.add_argument("--image-url", dest="image_url")
    p.add_argument("--ingredients")
    p.add_argument("--nutriscore", choices=list("abcde"))


def build_parser():
    p = argparse.ArgumentParser(prog="inventory", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default=os.environ.get("INVENTORY_API_URL", "http://127.0.0.1:5000"))
    p.add_argument("--api-key", default=os.environ.get("ADMIN_API_KEY"))
    p.add_argument("--json", action="store_true", help="print raw JSON")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("list", help="list items")
    s.add_argument("--search", "-s")
    s.add_argument("--low-stock", action="store_true")
    s.add_argument("--page", type=int, default=1)
    s.add_argument("--per-page", type=int, default=20)
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("get", help="show one item")
    s.add_argument("id", type=int)
    s.set_defaults(func=cmd_get)

    s = sub.add_parser("add", help="add an item")
    add_item_fields(s, required_name=True)
    s.add_argument("--enrich", action="store_true", help="fill gaps from OpenFoodFacts")
    s.set_defaults(func=cmd_add)

    s = sub.add_parser("update", help="update fields of an item")
    s.add_argument("id", type=int)
    add_item_fields(s)
    s.set_defaults(func=cmd_update)

    s = sub.add_parser("delete", help="delete an item")
    s.add_argument("id", type=int)
    s.add_argument("--yes", "-y", action="store_true", help="skip confirmation")
    s.set_defaults(func=cmd_delete)

    s = sub.add_parser("lookup", help="search OpenFoodFacts (no inventory change)")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--barcode")
    g.add_argument("--name")
    s.set_defaults(func=cmd_lookup)

    s = sub.add_parser("enrich", help="fill an existing item's details from OpenFoodFacts")
    s.add_argument("id", type=int)
    s.add_argument("--overwrite", action="store_true")
    s.set_defaults(func=cmd_enrich)
    return p


def main(argv=None, client=None):
    args = build_parser().parse_args(argv)
    api = client or ApiClient(args.url, args.api_key)
    try:
        return args.func(api, args)
    except requests.RequestException as exc:
        print(f"Cannot reach API at {api.base_url}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
