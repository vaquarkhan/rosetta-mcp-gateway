"""Translation types assigned to schema leaves."""

from enum import Enum


class TranslationType(str, Enum):
    IMMUTABLE = "TYPE_IMMUTABLE"
    CODE_SYNTAX = "TYPE_CODE_SYNTAX"
    ENTITY_LOCKED = "TYPE_ENTITY_LOCKED"
    FREE_TEXT = "TYPE_FREE_TEXT"


TRANSLATABLE = frozenset(
    {TranslationType.ENTITY_LOCKED.value, TranslationType.FREE_TEXT.value}
)
