"""Native-language tool calls are translated before an English-only MCP server.

The phrase book stands in for the network or CTranslate2 provider so the test
checks the gateway, not a particular model. A live provider is covered separately.
"""

import pytest

from rosetta.config import Settings
from rosetta.proxy.gateway import Gateway
from rosetta.translate.cache import CachingTranslator
from tests.test_classifier import INVOICE

ENGLISH = "overdue invoices"
SQL = "select id from invoices where status = 'OPEN'"

# locale, native wording of "overdue invoices"
CASES = [
    ("en-US", ENGLISH),
    ("hi-IN", "बकाया चालान"),
    ("es-ES", "facturas vencidas"),
    ("ar-SA", "فواتير متأخرة"),
    ("fr-FR", "factures impayées"),
    ("zh-CN", "逾期发票"),
    ("pt-BR", "faturas vencidas"),
    ("de-DE", "überfällige Rechnungen"),
    ("ja-JP", "延滞した請求書"),
    ("ru-RU", "просроченные счета"),
    ("bn-BD", "বকেয়া চালান"),
    ("ko-KR", "연체된 청구서"),
]


class PhraseBook:
    """Exact translations for the fixture phrases, in both directions."""

    def __init__(self) -> None:
        self.by_locale = {locale: text for locale, text in CASES if not locale.startswith("en")}

    def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        output = []
        for text in texts:
            if target.lower().startswith("en"):
                native = self.by_locale.get(source, "")
                stripped = text.strip()
                if stripped == native:
                    output.append(text.replace(stripped, ENGLISH))
                else:
                    output.append(text)
            else:
                native = self.by_locale.get(target, text)
                output.append(native if text == ENGLISH else text)
        return output


class EnglishOnlyMcp:
    """Invoice search that only matches the English query text."""

    def __init__(self):
        self.calls = []

    def exchange(self, message, headers):
        self.calls.append(message)
        method = message.get("method")
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "result": {"tools": [INVOICE]},
            }, {}
        arguments = message["params"]["arguments"]
        if arguments.get("status") not in {"OPEN", "PAID"}:
            return _error(message, "status is not an English enum"), {}
        if not isinstance(arguments.get("limit"), int):
            return _error(message, "limit is not an integer"), {}
        if not str(arguments.get("sql", "")).lower().startswith("select"):
            return _error(message, "sql is not English SQL"), {}
        query = arguments["query"]
        matched = "overdue" in query.lower() and "invoice" in query.lower()
        hits = [ENGLISH] if matched else []
        return {
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "result": {"hits": hits, "matched": matched},
        }, {}


def _error(message, text):
    return {
        "jsonrpc": "2.0",
        "id": message.get("id"),
        "error": {"code": -32602, "message": text},
    }


def _call(locale, query, **extra):
    arguments = {"query": query, "status": "OPEN", "limit": 3, "sql": SQL}
    arguments.update(extra)
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "search_invoices",
            "arguments": arguments,
            "_meta": {"locale": locale, "mode": "pivot"},
        },
    }


@pytest.mark.parametrize(("locale", "query"), CASES)
def test_native_query_is_translated_for_the_english_mcp(locale, query):
    upstream = EnglishOnlyMcp()
    gateway = Gateway(Settings(), upstream, translator=PhraseBook())

    response = gateway.handle(_call(locale, query))

    assert "error" not in response
    forwarded = upstream.calls[-1]["params"]["arguments"]
    assert forwarded["status"] == "OPEN"
    assert forwarded["limit"] == 3
    assert forwarded["sql"] == SQL
    assert response["result"]["matched"] is True
    if locale.startswith("en"):
        assert forwarded["query"] == ENGLISH
        assert gateway.last_plan.items == []
        assert response["result"]["hits"] == [ENGLISH]
    else:
        assert forwarded["query"] == ENGLISH
        assert gateway.last_plan.locale == locale
        assert gateway.last_plan.items[0].original == query
        assert gateway.last_plan.items[0].translated == ENGLISH
        assert response["result"]["hits"] == [query]


def test_locked_url_survives_translation():
    upstream = EnglishOnlyMcp()
    gateway = Gateway(Settings(), upstream, translator=PhraseBook())
    query = "बकाया चालान https://erp.example/invoices/1"

    response = gateway.handle(_call("hi-IN", query))

    forwarded = upstream.calls[-1]["params"]["arguments"]["query"]
    assert response["result"]["matched"] is True
    assert "https://erp.example/invoices/1" in forwarded
    assert "बकाया चालान" not in forwarded
    assert forwarded.startswith(ENGLISH)


def test_entity_and_repeat_use_the_cache():
    class ClusterToolMcp(EnglishOnlyMcp):
        def exchange(self, message, headers):
            if message.get("method") == "tools/call":
                arguments = message["params"]["arguments"]
                assert arguments["cluster"] == "prod-cluster-a"
            return super().exchange(message, headers)

    book = PhraseBook()
    cached = CachingTranslator(book)
    upstream = ClusterToolMcp()
    gateway = Gateway(Settings(), upstream, translator=cached)
    call = _call("fr-FR", "factures impayées", cluster="prod-cluster-a")

    gateway.handle(call)
    gateway.handle(call)

    assert cached.hits >= 1
    assert upstream.calls[-1]["params"]["arguments"]["cluster"] == "prod-cluster-a"
