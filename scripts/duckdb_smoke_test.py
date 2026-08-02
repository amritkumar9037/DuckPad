"""CI smoke test -- NOT part of the app itself.

Runs the real duckpad.db.Database class against the DuckDB engine, exercising
every operation the GUI performs (import, query, schema introspection, cell
update). This gets packaged into its own tiny PyInstaller exe with the exact
same --hidden-import flags as the real build, specifically to catch bugs that
only appear once frozen -- like duckdb needing Python's 'uuid' module at
runtime even though nothing in our code ever imports it directly, which
PyInstaller's static analysis has no way to see and silently drops from the
bundle.

Exits 0 and prints DUCKDB_SMOKE_OK on success. Any exception propagates with
a non-zero exit code, which fails the CI step.
"""

from duckpad import db, schema

d = db.Database(engine=db.ENGINE_DUCKDB)

# Import with a renamed table/column, mirroring the exact user-reported flow
# (paste data, rename table and a column in the import dialog, click Import).
info = d.import_table(
    "my_custom_table",
    [("employee_id", schema.TEXT), ("name", schema.TEXT), ("hired", schema.DATE)],
    [["1", "Alice", "2024-01-01"], ["2", "Bob", "2024-02-15"]],
)
assert info.name == "my_custom_table"

result = d.execute_sql("SELECT * FROM my_custom_table ORDER BY employee_id;")
assert result.rows[0][1] == "Alice", result.rows

schema_info = d.get_schema()
assert any(t.name == "my_custom_table" for t in schema_info), schema_info

d.update_cell("my_custom_table", "employee_id", "1", "name", "Alicia")
result2 = d.execute_sql("SELECT name FROM my_custom_table WHERE employee_id = '1';")
assert result2.rows == [["Alicia"]], result2.rows

d.execute_sql("CREATE TABLE temp_check(x INTEGER); DROP TABLE temp_check;")

print("DUCKDB_SMOKE_OK")
