# Inventory Admin Portal

Flask REST API + OpenFoodFacts integration + CLI + tests.

## Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py                      # API on http://127.0.0.1:5000
```
Config (env vars): `DATABASE_URL` (default `sqlite:///inventory.db`), `ADMIN_API_KEY`
(if set, clients must send `X-API-Key`), `OFF_TIMEOUT`, `OFF_USER_AGENT`,
`LOW_STOCK_THRESHOLD`. OpenFoodFacts asks API users to send a descriptive
User-Agent, so set `OFF_USER_AGENT` to your company contact.

## REST API
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness (never requires key) |
| GET | `/api/items?q=&low_stock=&page=&per_page=` | search / paginate |
| POST | `/api/items` | create; `"enrich": true` fills blanks from OpenFoodFacts |
| GET | `/api/items/<id>` | read |
| PUT / PATCH | `/api/items/<id>` | replace / partial update |
| DELETE | `/api/items/<id>` | delete (204) |
| POST | `/api/items/<id>/enrich[?overwrite=true]` | pull OFF data into an item |
| GET | `/api/products/lookup?barcode=` or `?name=` | OFF lookup, no DB change |

Status codes: 400 validation, 401 bad key, 404 missing item / product,
409 duplicate barcode, 502 OpenFoodFacts unreachable.

## CLI
```bash
export INVENTORY_API_URL=http://127.0.0.1:5000   # optional
python cli.py add --name "Oat Milk" --barcode 3017620422003 --quantity 20 --price 2.49 --enrich
python cli.py list --search milk
python cli.py list --low-stock
python cli.py update 1 --quantity 35
python cli.py lookup --name "nutella"
python cli.py enrich 1
python cli.py delete 1            # asks to confirm; -y skips
python cli.py --json get 1        # machine-readable output
```

## Tests
```bash
python -m pytest -v
```
The suite (64 tests) never touches the network: `requests.get` is mocked for
OpenFoodFacts, and CLI tests run against the real Flask app in-process.

## Layout
```
app/        __init__ (factory) · config · models · routes · off_client
cli.py      argparse CLI (ApiClient + one function per command)
tests/      API CRUD · OpenFoodFacts integration · CLI
run.py      dev server entry point
```
