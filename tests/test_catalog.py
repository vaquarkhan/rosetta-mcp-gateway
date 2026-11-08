from rosetta.cache import Catalog
from tests.test_classifier import INVOICE


def test_unseen_hash_is_a_miss_and_a_repeat_is_a_hit():
    catalog = Catalog()
    first = catalog.observe(INVOICE)
    second = catalog.observe(INVOICE)
    assert first.cache == "miss"
    assert second.cache == "hit"
    assert catalog.misses == 1
    assert catalog.hits == 1
    assert first.record.type_map == second.record.type_map
    assert first.record.quarantined is False


def test_changed_hash_quarantines_until_an_operator_accepts_it():
    catalog = Catalog()
    catalog.observe(INVOICE)
    changed = dict(INVOICE)
    changed["description"] = "Replaced by a rug pull"
    observed = catalog.observe(changed)
    pending = observed.record.pending_hash
    assert observed.cache == "miss"
    assert observed.record.quarantined is True
    assert observed.record.schema_hash != pending

    accepted = catalog.accept(INVOICE["name"])
    assert accepted.quarantined is False
    assert accepted.pending_hash is None
    assert accepted.schema_hash == pending
    assert accepted.type_map["query"] == "TYPE_FREE_TEXT"
