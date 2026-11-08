import io
import json

from fastapi.testclient import TestClient

from rosetta.config import Settings, load_settings
from rosetta.proxy.gateway import Gateway
from rosetta.proxy.http_app import create_app
from rosetta.proxy.stdio import serve_stdio
from rosetta.proxy.upstream import BridgedUpstream, HttpUpstream
from tests.test_classifier import INVOICE
import httpx


ARGUMENTS = {
    "query": "facturas vencidas https://erp.example/a",
    "status": "OPEN",
    "limit": 5,
    "active": True,
    "sql": "select * from invoices",
    "cluster": "prod-cluster-a",
    "customerId": "cust-1",
    "customer": {"note": "cliente nuevo", "id": "cust-1"},
    "lines": [{"memo": "línea uno", "qty": 2}],
}


class FakeUpstream:
    def __init__(self, tools):
        self.tools = tools
        self.calls = []

    def exchange(self, message, headers):
        self.calls.append((message, headers))
        method = message.get("method")
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "result": {"tools": self.tools},
            }, {}
        return {"jsonrpc": "2.0", "id": message.get("id"), "result": {"ok": True}}, {}


def _gateway(tools=None, **kwargs):
    settings = Settings(**kwargs)
    upstream = FakeUpstream(tools if tools is not None else [INVOICE])
    return Gateway(settings, upstream), upstream


def _call(locale="es-ES"):
    return {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {
            "name": "search_invoices",
            "arguments": ARGUMENTS,
            "_meta": {"locale": locale, "mode": "pivot"},
        },
    }


def test_spanish_call_plans_text_and_preserves_structure():
    gateway, upstream = _gateway()
    response = gateway.handle(_call("es-ES"))
    assert response["result"]["ok"] is True
    forwarded = upstream.calls[-1][0]["params"]["arguments"]
    assert forwarded == ARGUMENTS
    assert isinstance(forwarded["limit"], int)
    assert forwarded["status"] == "OPEN"
    assert forwarded["active"] is True
    plan = gateway.last_plan
    paths = {item.path: item for item in plan.items}
    assert set(paths) == {"query", "cluster", "customer.note", "lines[].memo"}
    assert "https://erp.example/a" not in paths["query"].masked
    assert paths["query"].original == ARGUMENTS["query"]
    assert "status" not in paths
    assert "sql" not in paths


def test_english_call_is_a_passthrough_with_an_empty_plan():
    gateway, upstream = _gateway()
    gateway.handle(_call("en-US"))
    forwarded = upstream.calls[-1][0]["params"]["arguments"]
    assert forwarded == ARGUMENTS
    assert gateway.last_plan.items == []


def test_missing_locale_on_free_text_is_rejected_before_upstream():
    gateway, upstream = _gateway()
    message = _call("es-ES")
    del message["params"]["_meta"]
    response = gateway.handle(message)
    assert response["error"]["data"]["code"] == "LOCALE_REQUIRED"
    assert [call[0]["method"] for call in upstream.calls] == ["tools/list"]


def test_ping_from_header_bypasses_classification():
    gateway, upstream = _gateway()
    response = gateway.handle({"jsonrpc": "2.0", "id": 1}, {"mcp-method": "ping"})
    assert response["result"]["ok"] is True
    assert "method" not in upstream.calls[0][0]
    assert gateway.catalog.misses == 0


def test_numeric_tool_does_not_require_a_locale():
    tool = {
        "name": "count_only",
        "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer"}}},
    }
    gateway, upstream = _gateway([tool])
    response = gateway.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "count_only", "arguments": {"limit": 2}},
        }
    )
    assert "error" not in response
    assert upstream.calls[-1][0]["params"]["arguments"]["limit"] == 2


def test_schema_change_quarantines_until_accept():
    gateway, upstream = _gateway()
    listed = gateway.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert listed["result"]["tools"][0]["name"] == "search_invoices"
    assert gateway.catalog.misses == 1

    changed = json.loads(json.dumps(INVOICE))
    changed["description"] = "rug pull"
    upstream.tools = [changed]
    gateway.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    blocked = gateway.handle(_call("es-ES"))
    assert blocked["error"]["data"]["code"] == "CATALOG_QUARANTINE"
    assert all(call[0].get("method") != "tools/call" for call in upstream.calls)

    accepted = gateway.catalog.accept("search_invoices")
    assert accepted.quarantined is False
    allowed = gateway.handle(_call("es-ES"))
    assert allowed["result"]["ok"] is True


def test_repeat_tools_list_is_a_cache_hit(tracing):
    tracing.clear()
    gateway, _upstream = _gateway()
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    gateway.handle(message)
    gateway.handle(message)
    assert gateway.catalog.hits == 1
    assert gateway.catalog.misses == 1
    spans = [span for span in tracing.get_finished_spans() if span.attributes.get("mcp.method") == "tools/list"]
    assert spans
    assert spans[-1].attributes.get("rosetta.cache") == "hit"
    assert spans[-1].attributes.get("mcp.server") == "upstream"


def test_http_catalog_and_accept_language():
    gateway, upstream = _gateway()
    client = TestClient(create_app(gateway))
    assert client.get("/healthz").json()["status"] == "ok"
    listed = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert listed.status_code == 200
    catalog = client.get("/catalog").json()
    assert catalog["tools"][0]["type_map"]["status"] == "TYPE_IMMUTABLE"

    denied = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "search_invoices", "arguments": ARGUMENTS},
        },
        headers={"Accept-Language": "es-ES,en;q=0.8"},
    )
    assert denied.status_code == 200
    assert "error" not in denied.json()
    assert upstream.calls[-1][0]["params"]["arguments"]["status"] == "OPEN"

    changed = json.loads(json.dumps(INVOICE))
    changed["description"] = "changed again"
    upstream.tools = [changed]
    client.post("/mcp", json={"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    quarantined = client.post(
        "/mcp",
        json=_call("es-ES"),
        headers={"Mcp-Method": "tools/call", "Mcp-Name": "search_invoices"},
    )
    assert quarantined.json()["error"]["data"]["code"] == "CATALOG_QUARANTINE"
    accepted = client.post("/catalog/accept", json={"name": "search_invoices"})
    assert accepted.json()["quarantined"] is False


def test_stdio_round_trip():
    gateway, _upstream = _gateway()
    stdin = io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}) + "\n")
    stdout = io.StringIO()
    serve_stdio(gateway, stdin, stdout)
    response = json.loads(stdout.getvalue())
    assert response["id"] == 1
    assert response["result"]["ok"] is True


def test_legacy_session_bridge_initializes_once():
    class Legacy:
        def __init__(self):
            self.calls = []

        def exchange(self, message, headers):
            method = message.get("method")
            session = headers.get("mcp-session-id")
            self.calls.append((method, session))
            if method == "initialize":
                return (
                    {"jsonrpc": "2.0", "id": message.get("id"), "result": {"protocolVersion": "2025-11-25"}},
                    {"Mcp-Session-Id": "sess-1"},
                )
            if method == "notifications/initialized":
                return None, {}
            if session != "sess-1":
                return {"jsonrpc": "2.0", "id": message.get("id"), "error": {"code": -32000, "message": "session required"}}, {}
            return {"jsonrpc": "2.0", "id": message.get("id"), "result": {"tools": [INVOICE]}}, {}

    inner = Legacy()
    bridge = BridgedUpstream(inner, "2025-11-25")
    gateway = Gateway(Settings(upstream_protocol="2025-11-25"), bridge)
    response = gateway.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert response["result"]["tools"][0]["name"] == "search_invoices"
    methods = [method for method, _session in inner.calls]
    assert methods[:3] == ["initialize", "notifications/initialized", "tools/list"]
    assert inner.calls[1][1] == "sess-1"
    assert inner.calls[2][1] == "sess-1"
    gateway.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert [method for method, _session in inner.calls].count("initialize") == 1


def test_http_upstream_posts_the_frame():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["method"] = request.headers.get("mcp-method")
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}})

    upstream = HttpUpstream("http://upstream/mcp", client=httpx.Client(transport=httpx.MockTransport(handler)))
    response, _headers = upstream.exchange({"jsonrpc": "2.0", "id": 1, "method": "ping"}, {})
    assert response["result"] == {}
    assert seen["body"]["method"] == "ping"
    assert seen["method"] == "ping"


def test_config_env_overrides(tmp_path, monkeypatch):
    path = tmp_path / "gateway.yaml"
    path.write_text(
        "schema_translation_mode: none\nupstream:\n  url: http://example/mcp\n  protocol: '2026-07-28'\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ROSETTA_UPSTREAM_URL", "http://override/mcp")
    monkeypatch.setenv("ROSETTA_PORT", "9090")
    settings = load_settings(str(path))
    assert settings.upstream_url == "http://override/mcp"
    assert settings.port == 9090
