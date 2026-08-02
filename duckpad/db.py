"""Database layer: in-memory SQLite or DuckDB backend, selectable per session.

Both engines expose the same public API (import_table, execute_sql,
get_schema, next_scratch_name, update_cell) so the UI layer never has to
know which one is active.
"""

from __future__ import annotations
import re
import time
from dataclasses import dataclass, field

import sqlite3

try:
    import duckdb
    HAVE_DUCKDB = True
except ImportError:
    HAVE_DUCKDB = False

from . import schema as schema_mod

ENGINE_SQLITE = "sqlite"
ENGINE_DUCKDB = "duckdb"


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


class EngineNotAvailableError(RuntimeError):
    pass


class Database:
    """Wraps one in-memory connection -- SQLite or DuckDB, chosen at
    construction time. The app talks to one of these per session; switching
    engines means creating a new Database (and losing in-memory data, since
    neither engine's in-memory mode persists across connections)."""

    def __init__(self, engine: str = ENGINE_SQLITE):
        if engine == ENGINE_DUCKDB and not HAVE_DUCKDB:
            raise EngineNotAvailableError(
                "The 'duckdb' package is not installed. Run: pip install duckdb"
            )
        self.engine = engine
        if engine == ENGINE_DUCKDB:
            self.conn = duckdb.connect(":memory:")
        else:
            self.conn = sqlite3.connect(":memory:")
            self.conn.execute("PRAGMA foreign_keys = ON;")

    # ------------------------------------------------------------- schema

    def next_scratch_name(self) -> str:
        """Finds the next unused table1/table2/... name."""
        existing = {t.name for t in self.get_schema()}
        n = 1
        while f"table{n}" in existing:
            n += 1
        return f"table{n}"

    def get_schema(self) -> list[TableInfo]:
        if self.engine == ENGINE_DUCKDB:
            return self._get_schema_duckdb()
        return self._get_schema_sqlite()

    def _get_schema_sqlite(self) -> list[TableInfo]:
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

    def _get_schema_duckdb(self) -> list[TableInfo]:
        rows = self.conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main' ORDER BY table_name;"
        ).fetchall()
        tables = []
        for (name,) in rows:
            col_rows = self.conn.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = ? ORDER BY ordinal_position;",
                [name],
            ).fetchall()
            columns = [ColumnInfo(name=c, data_type=t) for c, t in col_rows]
            tables.append(TableInfo(name=name, columns=columns))
        return tables

    # ------------------------------------------------------------- import

    def import_table(
        self,
        table_name: str | None,
        columns: list[tuple[str, str]],  # (identifier, inferred_type)
        rows: list[list[str]],
    ) -> TableInfo:
        """Creates (or replaces) a table and inserts all rows."""
        name = table_name or self.next_scratch_name()
        safe_name = safe_identifier(name, 1) or name

        col_defs = ", ".join(
            f'"{col_name}" {schema_mod.native_type(inferred, self.engine)}'
            for col_name, inferred in columns
        )
        self.conn.execute(f'DROP TABLE IF EXISTS "{safe_name}";')
        self.conn.execute(f'CREATE TABLE "{safe_name}" ({col_defs});')

        placeholders = ", ".join("?" for _ in columns)
        insert_sql = f'INSERT INTO "{safe_name}" VALUES ({placeholders})'
        coerced_rows = [
            [
                self._coerce(row[i] if i < len(row) else "", columns[i][1])
                for i in range(len(columns))
            ]
            for row in rows
        ]

        if self.engine == ENGINE_DUCKDB:
            self.conn.executemany(insert_sql, coerced_rows)
        else:
            with self.conn:
                self.conn.executemany(insert_sql, coerced_rows)

        return TableInfo(
            name=safe_name,
            columns=[ColumnInfo(name=c, data_type=t) for c, t in columns],
        )

    def _coerce(self, raw: str, inferred_type: str):
        s = raw.strip()
        if not s:
            return None
        if self.engine == ENGINE_DUCKDB:
            # DuckDB casts strings into the target column type automatically
            # via bound parameters (verified: INTEGER/DOUBLE/BOOLEAN/DATE/
            # TIMESTAMP all auto-cast from a plain string), so just pass it.
            return s
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

    # ------------------------------------------------------------- query

    def execute_sql(self, sql: str) -> QueryResult:
        """Runs one or more ';'-separated statements. Only the last statement's
        result set (if it's a SELECT) is returned."""
        statements = [s.strip() for s in sql.split(";") if s.strip()]
        if not statements:
            return QueryResult(columns=[], rows=[], elapsed_ms=0.0)

        start = time.perf_counter()
        result = QueryResult(columns=[], rows=[], elapsed_ms=0.0)

        if self.engine == ENGINE_DUCKDB:
            for stmt in statements:
                self.conn.execute(stmt)
                if self.conn.description:
                    result.columns = [d[0] for d in self.conn.description]
                    result.rows = [list(r) for r in self.conn.fetchall()]
                    result.rows_affected = len(result.rows)
                else:
                    result.columns, result.rows, result.rows_affected = [], [], 0
        else:
            cur = self.conn.cursor()
            with self.conn:
                for stmt in statements:
                    cur.execute(stmt)
                    if cur.description:
                        result.columns = [d[0] for d in cur.description]
                        result.rows = [list(r) for r in cur.fetchall()]
                        result.rows_affected = len(result.rows)
                    else:
                        result.columns, result.rows = [], []
                        result.rows_affected = cur.rowcount if cur.rowcount != -1 else 0

        result.elapsed_ms = (time.perf_counter() - start) * 1000.0
        return result

    # -------------------------------------------------------- cell editing

    def update_cell(
        self, table: str, pk_column: str, pk_value, target_column: str, new_value: str
    ) -> str:
        """Generates and runs an UPDATE for a single cell edit. Returns the
        SQL that was executed (so the UI/history can show it)."""
        sql = (
            f'UPDATE "{table}" SET "{target_column}" = ? WHERE "{pk_column}" = ?;'
        )
        if self.engine == ENGINE_DUCKDB:
            self.conn.execute(sql, [new_value, pk_value])
        else:
            with self.conn:
                self.conn.execute(sql, [new_value, pk_value])
        return sql.replace("?", "{}").format(repr(new_value), repr(pk_value))

    # ----------------------------------------------------- table/column management

    def rename_table(self, old_name: str, new_name: str) -> str:
        new_name = safe_identifier(new_name, 1)
        sql = f'ALTER TABLE "{old_name}" RENAME TO "{new_name}";'
        self._exec_ddl(sql)
        return new_name

    def drop_table(self, name: str):
        self._exec_ddl(f'DROP TABLE "{name}";')

    def duplicate_table(self, name: str, new_name: str | None = None) -> str:
        new_name = safe_identifier(new_name, 1) if new_name else self.next_scratch_name()
        self._exec_ddl(f'CREATE TABLE "{new_name}" AS SELECT * FROM "{name}";')
        return new_name

    def rename_column(self, table: str, old_col: str, new_col: str) -> str:
        new_col = safe_identifier(new_col, 1)
        self._exec_ddl(f'ALTER TABLE "{table}" RENAME COLUMN "{old_col}" TO "{new_col}";')
        return new_col

    def drop_column(self, table: str, col: str):
        self._exec_ddl(f'ALTER TABLE "{table}" DROP COLUMN "{col}";')

    def change_column_type(self, table: str, col: str, new_inferred_type: str):
        """Changes one column's datatype. DuckDB supports ALTER COLUMN ... TYPE
        directly (with an automatic cast). SQLite has no such statement, so we
        rebuild the table: create a copy with the new type, cast the target
        column's data across, drop the original, rename the copy into place."""
        native = schema_mod.native_type(new_inferred_type, self.engine)
        if self.engine == ENGINE_DUCKDB:
            self._exec_ddl(f'ALTER TABLE "{table}" ALTER COLUMN "{col}" TYPE {native};')
            return

        tables = {t.name: t for t in self._get_schema_sqlite()}
        info = tables[table]
        col_defs = []
        select_exprs = []
        for c in info.columns:
            if c.name == col:
                col_defs.append(f'"{c.name}" {native}')
                select_exprs.append(f'CAST("{c.name}" AS {native})')
            else:
                col_defs.append(f'"{c.name}" {c.data_type}')
                select_exprs.append(f'"{c.name}"')

        tmp_name = f"__tmp_{table}_retype"
        with self.conn:
            self.conn.execute(f'DROP TABLE IF EXISTS "{tmp_name}";')
            self.conn.execute(f'CREATE TABLE "{tmp_name}" ({", ".join(col_defs)});')
            self.conn.execute(
                f'INSERT INTO "{tmp_name}" SELECT {", ".join(select_exprs)} FROM "{table}";'
            )
            self.conn.execute(f'DROP TABLE "{table}";')
            self.conn.execute(f'ALTER TABLE "{tmp_name}" RENAME TO "{table}";')

    def _exec_ddl(self, sql: str):
        if self.engine == ENGINE_DUCKDB:
            self.conn.execute(sql)
        else:
            with self.conn:
                self.conn.execute(sql)
