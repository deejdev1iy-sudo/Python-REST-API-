"""CLI tests. The CLI talks to the real Flask app through an in-process session."""
import json
from unittest.mock import patch

import pytest
import requests

import cli
from tests.conftest import OFF_NUTELLA, FakeResponse


class FlaskSession:
    """Adapts Flask's test client to the requests.Session.request() interface."""

    def __init__(self, test_client):
        self.c = test_client

    def request(self, method, url, params=None, json=None, headers=None, timeout=None):
        path = url.split("://", 1)[1].split("/", 1)[1]
        resp = self.c.open("/" + path, method=method, query_string=params,
                           json=json, headers=headers)

        class R:
            status_code = resp.status_code
            content = resp.data
            text = resp.get_data(as_text=True)
            def json(self_inner):
                return resp.get_json()
        return R()


@pytest.fixture()
def run(client, capsys):
    api = cli.ApiClient("http://api.test", session=FlaskSession(client))

    def _run(*argv):
        code = cli.main(list(argv), client=api)
        out = capsys.readouterr()
        return code, out.out, out.err
    return _run


def test_add_list_get_flow(run):
    code, out, _ = run("add", "--name", "Cola", "--quantity", "7", "--price", "1.5",
                       "--barcode", "12345678")
    assert code == 0 and "Created item" in out
    code, out, _ = run("list")
    assert code == 0 and "Cola" in out and "1 item(s)" in out
    code, out, _ = run("get", "1")
    assert code == 0 and "12345678" in out


def test_json_output(run):
    run("add", "--name", "Cola")
    code, out, _ = run("--json", "get", "1")
    assert code == 0 and json.loads(out)["name"] == "Cola"


def test_list_search_and_low_stock(run):
    run("add", "--name", "Cola", "--quantity", "1")
    run("add", "--name", "Juice", "--quantity", "100")
    assert "Juice" not in run("list", "--search", "cola")[1]
    low = run("list", "--low-stock")[1]
    assert "Cola" in low and "Juice" not in low


def test_list_empty(run):
    assert "No items found" in run("list")[1]


def test_update(run):
    run("add", "--name", "Cola", "--quantity", "1")
    code, out, _ = run("update", "1", "--quantity", "20")
    assert code == 0 and "20" in out
    assert "20" in run("get", "1")[1]


def test_update_requires_a_field(run):
    code, _, err = run("update", "1")
    assert code == 2 and "Nothing to update" in err


def test_delete_with_yes_and_missing(run):
    run("add", "--name", "Cola")
    assert run("delete", "1", "--yes")[0] == 0
    code, _, err = run("get", "1")
    assert code == 1 and "404" in err


def test_delete_confirmation_declined(run):
    run("add", "--name", "Cola")
    with patch("builtins.input", return_value="n"):
        code, out, _ = run("delete", "1")
    assert code == 1 and "Cancelled" in out
    assert run("get", "1")[0] == 0   # still exists


def test_validation_error_reported(run):
    code, _, err = run("add", "--name", "Bad", "--barcode", "xyz")
    assert code == 1 and "barcode" in err


def test_lookup_and_add_with_enrich(run):
    with patch("app.off_client.requests.get", return_value=FakeResponse(OFF_NUTELLA)):
        code, out, _ = run("lookup", "--barcode", "3017620422003")
        assert code == 0 and "Ferrero" in out
        code, out, _ = run("add", "--name", "Jar", "--barcode", "3017620422003", "--enrich")
        assert code == 0 and "Ferrero" in out


def test_enrich_command(run):
    run("add", "--name", "Jar", "--barcode", "3017620422003")
    with patch("app.off_client.requests.get", return_value=FakeResponse(OFF_NUTELLA)):
        code, out, _ = run("enrich", "1")
    assert code == 0 and "Spreads" in out


def test_upstream_failure_message(run):
    with patch("app.off_client.requests.get", side_effect=requests.Timeout()):
        code, _, err = run("lookup", "--name", "x")
    assert code == 1 and "502" in err


def test_unreachable_api_exit_code(capsys):
    class Boom:
        def request(self, *a, **k):
            raise requests.ConnectionError("refused")
    api = cli.ApiClient("http://nowhere", session=Boom())
    assert cli.main(["list"], client=api) == 2
    assert "Cannot reach API" in capsys.readouterr().err


def test_api_key_header_sent():
    seen = {}

    class Spy:
        def request(self, method, url, **kw):
            seen.update(kw["headers"])
            class R:
                status_code, content = 200, b"{}"
                def json(self): return {}
            return R()
    cli.ApiClient("http://x", api_key="k", session=Spy()).request("GET", "/api/items")
    assert seen == {"X-API-Key": "k"}


def test_lookup_requires_barcode_or_name():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["lookup"])
