"""Infers the smallest-safe SQLite type for each column from sampled string values."""

from __future__ import annotations
import re

# Order matters: widening moves left -> right through this list.
NULL, BOOLEAN, INTEGER, REAL, DATE, TIMESTAMP, TEXT = (
    "NULL",
    "BOOLEAN",
    "INTEGER",
    "REAL",
    "DATE",
    "TIMESTAMP",
    "TEXT",
)

_DATE_RE = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$")
_TIMESTAMP_RE = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}[ T]\d{1,2}:\d{2}(:\d{2})?$")

_WIDEN_TABLE = {
    frozenset({BOOLEAN, INTEGER}): INTEGER,
    frozenset({INTEGER, REAL}): REAL,
    frozenset({BOOLEAN, REAL}): REAL,
    frozenset({DATE, TIMESTAMP}): TIMESTAMP,
}


def _widen(a: str, b: str) -> str:
    if a == b:
        return a
    if a == NULL:
        return b
    if b == NULL:
        return a
    key = frozenset({a, b})
    return _WIDEN_TABLE.get(key, TEXT)  # incompatible types fall back to TEXT


def _classify_value(raw: str) -> str:
    s = raw.strip()
    if not s:
        return NULL
    lower = s.lower()
    if lower in ("true", "false"):
        return BOOLEAN
    try:
        int(s)
        return INTEGER
    except ValueError:
        pass
    try:
        float(s)
        return REAL
    except ValueError:
        pass
    if _TIMESTAMP_RE.match(s):
        return TIMESTAMP
    if _DATE_RE.match(s):
        return DATE
    return TEXT


def infer_column_type(values: list[str]) -> str:
    result = NULL
    for v in values:
        result = _widen(result, _classify_value(v))
        if result == TEXT:
            break  # already at the widest fallback, no need to keep scanning
    return result if result != NULL else TEXT  # an all-empty column still needs a real SQL type


def sqlite_type(inferred: str) -> str:
    """Maps our inferred type to a concrete SQLite column affinity.
    SQLite has no native BOOLEAN/DATE/TIMESTAMP type -- store as INTEGER/TEXT
    with the inferred type recorded for the UI, but the column affinity itself
    must be one SQLite understands."""
    return {
        BOOLEAN: "INTEGER",
        INTEGER: "INTEGER",
        REAL: "REAL",
        DATE: "TEXT",
        TIMESTAMP: "TEXT",
        TEXT: "TEXT",
        NULL: "TEXT",
    }[inferred]


def duckdb_type(inferred: str) -> str:
    """Maps our inferred type to a native DuckDB column type. Unlike SQLite,
    DuckDB has real BOOLEAN/DATE/TIMESTAMP types, so this mapping is exact
    rather than an affinity workaround."""
    return {
        BOOLEAN: "BOOLEAN",
        INTEGER: "BIGINT",
        REAL: "DOUBLE",
        DATE: "DATE",
        TIMESTAMP: "TIMESTAMP",
        TEXT: "VARCHAR",
        NULL: "VARCHAR",
    }[inferred]


def native_type(inferred: str, engine: str) -> str:
    return duckdb_type(inferred) if engine == "duckdb" else sqlite_type(inferred)
