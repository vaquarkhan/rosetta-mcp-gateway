from rosetta.locking import EntityLocker

SAMPLE = (
    "facturas vencidas ${ENV} {{ticket}} %s $1 "
    "see https://erp.example/a and ops@example.com "
    "id 550e8400-e29b-41d4-a716-446655440000 on 2026-11-08 "
    "count 12 ```select 1```"
)


def test_mask_and_restore_round_trip():
    locker = EntityLocker(glossary=["facturas vencidas"])
    masked, originals = locker.mask(SAMPLE)
    assert locker.restore(masked, originals) == SAMPLE
    assert SAMPLE not in masked
    assert "https://erp.example/a" not in masked
    assert "550e8400-e29b-41d4-a716-446655440000" not in masked
    assert "${ENV}" not in masked
    assert "{{ticket}}" not in masked
    assert "2026-11-08" not in masked
    assert "```select 1```" not in masked
    assert any(piece == "facturas vencidas" for piece in originals)
