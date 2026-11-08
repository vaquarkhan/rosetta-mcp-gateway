from rosetta.classifier import canonical_schema_hash, classify_tool

INVOICE = {
    "name": "search_invoices",
    "description": "Search invoices",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "status": {"type": "string", "enum": ["OPEN", "PAID"]},
            "limit": {"type": "integer"},
            "active": {"type": "boolean"},
            "sql": {"type": "string", "x-rosetta-type": "code"},
            "cluster": {"type": "string", "x-rosetta-type": "entity"},
            "customerId": {"type": "string"},
            "customer": {
                "type": "object",
                "properties": {
                    "note": {"type": "string"},
                    "id": {"type": "string"},
                },
            },
            "lines": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"memo": {"type": "string"}, "qty": {"type": "number"}},
                },
            },
        },
    },
}


def test_leaf_types_cover_the_four_classes():
    types = classify_tool(INVOICE)
    assert types["query"] == "TYPE_FREE_TEXT"
    assert types["status"] == "TYPE_IMMUTABLE"
    assert types["limit"] == "TYPE_IMMUTABLE"
    assert types["active"] == "TYPE_IMMUTABLE"
    assert types["sql"] == "TYPE_CODE_SYNTAX"
    assert types["cluster"] == "TYPE_ENTITY_LOCKED"
    assert types["customerId"] == "TYPE_IMMUTABLE"
    assert types["customer.note"] == "TYPE_FREE_TEXT"
    assert types["customer.id"] == "TYPE_IMMUTABLE"
    assert types["lines[].memo"] == "TYPE_FREE_TEXT"
    assert types["lines[].qty"] == "TYPE_IMMUTABLE"


def test_yaml_override_wins_over_heuristics():
    types = classify_tool(INVOICE, field_overrides={"query": "TYPE_IMMUTABLE"})
    assert types["query"] == "TYPE_IMMUTABLE"


def test_entity_locked_field_names():
    tool = {
        "name": "search_invoices",
        "inputSchema": {"type": "object", "properties": {"region": {"type": "string"}}},
    }
    types = classify_tool(tool, entity_locked_fields={"region"})
    assert types["region"] == "TYPE_ENTITY_LOCKED"


def test_hash_ignores_key_order_and_changes_when_description_changes():
    reversed_tool = {
        "inputSchema": INVOICE["inputSchema"],
        "description": INVOICE["description"],
        "name": INVOICE["name"],
    }
    assert canonical_schema_hash(INVOICE) == canonical_schema_hash(reversed_tool)
    changed = dict(INVOICE)
    changed["description"] = "Changed"
    assert canonical_schema_hash(changed) != canonical_schema_hash(INVOICE)
