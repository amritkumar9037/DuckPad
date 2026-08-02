"""In-memory SQLite backend: import tabular data, run SQL, introspect schema."""

from __future__ import annotations
import re
import sqlite3
import time
from dataclasses import dataclass, field


def safe_identifier(raw: str, fallback_index: int) -> str:
    """Sanitizes a header cell into a safe SQL identifier."""
    cleaned = re.sub(r"[^0-9A-Za-z_]", "_", raw.strip()).strip("_")
    if not cleaned or cleaned[0].isdigit():
        return f"col_{fallback_index}"
    return cleaned


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list]
    elapsed_ms: float
    rows_affected: int = 0


@dataclass
class ColumnInfo:
    name: str
    data_type: str


@dataclass
class TableInfo:
    name: str
    columns: list[ColumnInfo] = field(default_factory=list)


class Database:
    """Wraps one in-memory SQLite connection -- the whole app talks to one of these."""

    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self._scratch_counter = 0

    def next_scratch_name(self) -> str:
        """Finds the next unused table1/table2/... name (matches the spec's
        'Paste as Table' -> table1, table2, table3 behavior)."""
        existing = {t.name for t in self.get_schema()}
        n = 1
        while f"table{n}" in existing:
            n += 1
        return f"table{n}"

    def import_table(
        self,
        table_name: str | None,
        columns: list[tuple[str, str]],  # (name, inferred_type)
        rows: list[list[str]],
    ) -> TableInfo:
        """Creates (or replaces) a table and inserts all rows. columns are
        (identifier, inferred_type) pairs; inferred_type is our schema.py
        vocabulary (INTEGER/REAL/BOOLEAN/DATE/TIMESTAMP/TEXT/NULL)."""
        from . import schema as schema_mod

        name = table_name or self.next_scratch_name()
        safe_name = safe_identifier(name, 1) or name

        col_defs = ", ".join(
            f'"{col_name}" {schema_mod.sqlite_type(inferred)}'
            for col_name, inferred in columns
        )
        self.conn.execute(f'DROP TABLE IF EXISTS "{safe_name}";')
        self.conn.execute(f'CREATE TABLE "{safe_name}" ({col_defs});')

        placeholders = ", ".join("?" for _ in columns)
        insert_sql = f'INSERT INTO "{safe_name}" VALUES ({placeholders})'
        coerced_rows = [
            [self._coerce(row[i] if i < len(row) else "", columns[i][1]) for i in range(len(columns))]
            for row in rows
        ]
        with self.conn:
            self.conn.executemany(insert_sql, coerced_rows)

        return TableInfo(
            name=safe_name,
            columns=[ColumnInfo(name=c, data_type=t) for c, t in columns],
        )

    @staticmethod
    def _coerce(raw: str, inferred_type: str):
        from . import schema as schema_mod

        s = raw.strip()
        if not s:
            return None
        if inferred_type == schema_mod.INTEGER:
            try:
                return int(s)
            except ValueError:
                return None
        if inferred_type == schema_mod.REAL:
            try:
                return float(s)
            except ValueError:
                return None
        if inferred_type == schema_mod.BOOLEAN:
            return 1 if s.lower() == "true" else 0
        return s

    def execute_sql(self, sql: str) -> QueryResult:
        """Runs one or more ';'-separated statements. Only the last statement's
        result set (if it's a SELECT) is returned -- matches the app's
        'CREATE TABLE ...; SELECT * FROM ...;' one-shot workflow."""
        statements = [s.strip() for s in sql.split(";") if s.strip()]
        if not statements:
            return QueryResult(columns=[], rows=[], elapsed_ms=0.0)

        start = time.perf_counter()
        cur = self.conn.cursor()
        result = QueryResult(columns=[], rows=[], elapsed_ms=0.0)
        with self.conn:
            for stmt in statements:
                cur.execute(stmt)
                if cur.description:
                    result.columns = [d[0] for d in cur.description]
                    result.rows = [list(r) for r in cur.fetchall()]
                    result.rows_affected = len(result.rows)
                else:
                    result.columns = []
                    result.rows = []
                    result.rows_affected = cur.rowcount if cur.rowcount != -1 else 0
        result.elapsed_ms = (time.perf_counter() - start) * 1000.0
        return result

    def get_schema(self) -> list[TableInfo]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
        )
        tables = []
        for (name,) in cur.fetchall():
            col_cur = self.conn.cursor()
            col_cur.execute(f'PRAGMA table_info("{name}");')
            columns = [ColumnInfo(name=row[1], data_type=row[2]) for row in col_cur.fetchall()]
            tables.append(TableInfo(name=name, columns=columns))
        return tables
