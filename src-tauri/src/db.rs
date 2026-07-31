use duckdb::{Connection, types::Value};
use once_cell::sync::Lazy;
use serde::Serialize;
use std::sync::Mutex;
use std::time::Instant;
use thiserror::Error;

/// Single shared DuckDB connection for the app's lifetime.
/// DuckDB itself is not thread-safe across concurrent writers, so all
/// access goes through this mutex. For an analyst desktop tool this is a
/// non-issue — queries are user-driven and sequential.
pub static DB: Lazy<Mutex<Connection>> = Lazy::new(|| {
    let conn = Connection::open_in_memory().expect("failed to open DuckDB in-memory database");
    Mutex::new(conn)
});

#[derive(Debug, Error)]
pub enum DbError {
    #[error("database error: {0}")]
    Duck(#[from] duckdb::Error),
    #[error("lock poisoned")]
    Lock,
    #[error("table not found after import: {0}")]
    NotFound(String),
}

#[derive(Debug, Serialize)]
pub struct QueryResult {
    pub columns: Vec<String>,
    pub rows: Vec<Vec<serde_json::Value>>,
    pub rows_affected: usize,
    pub execution_ms: u128,
}

#[derive(Debug, Serialize)]
pub struct ColumnInfo {
    pub name: String,
    pub data_type: String,
}

#[derive(Debug, Serialize)]
pub struct TableInfo {
    pub name: String,
    pub columns: Vec<ColumnInfo>,
}

fn duckdb_value_to_json(v: &Value) -> serde_json::Value {
    match v {
        Value::Null => serde_json::Value::Null,
        Value::Boolean(b) => serde_json::Value::Bool(*b),
        Value::TinyInt(i) => serde_json::json!(i),
        Value::SmallInt(i) => serde_json::json!(i),
        Value::Int(i) => serde_json::json!(i),
        Value::BigInt(i) => serde_json::json!(i),
        Value::HugeInt(i) => serde_json::json!(i.to_string()),
        Value::UTinyInt(i) => serde_json::json!(i),
        Value::USmallInt(i) => serde_json::json!(i),
        Value::UInt(i) => serde_json::json!(i),
        Value::UBigInt(i) => serde_json::json!(i),
        Value::Float(f) => serde_json::json!(f),
        Value::Double(f) => serde_json::json!(f),
        Value::Text(s) => serde_json::json!(s),
        Value::Blob(b) => serde_json::json!(format!("<blob:{} bytes>", b.len())),
        other => serde_json::json!(format!("{:?}", other)),
    }
}

/// Executes arbitrary SQL (one or more statements separated by `;`) and
/// returns the result of the *last* statement. This matches the "select
/// what you highlighted / whole editor" behavior described in the spec:
/// DDL/DML statements run for their side effects, and a trailing SELECT
/// (if present) populates the results grid.
pub fn execute_sql(sql: &str) -> Result<QueryResult, DbError> {
    let start = Instant::now();
    let conn = DB.lock().map_err(|_| DbError::Lock)?;

    let mut columns: Vec<String> = Vec::new();
    let mut rows: Vec<Vec<serde_json::Value>> = Vec::new();
    let mut rows_affected: usize = 0;

    // duckdb-rs doesn't multi-statement-execute-with-results in one call
    // for arbitrary mixed DDL/DML/SELECT, so we split naively on `;` and
    // run each statement, capturing output only from the final one that
    // returns rows. A real SQL-aware splitter (respecting string literals
    // and comments) replaces this in Milestone 2+.
    let statements: Vec<&str> = sql
        .split(';')
        .map(|s| s.trim())
        .filter(|s| !s.is_empty())
        .collect();

    for (i, stmt) in statements.iter().enumerate() {
        let is_last = i == statements.len() - 1;
        let mut prepared = conn.prepare(stmt)?;

        if prepared.column_count() > 0 {
            // Statement returns rows (SELECT, PRAGMA, etc.)
            let col_names: Vec<String> = prepared
                .column_names()
                .into_iter()
                .map(|s| s.to_string())
                .collect();

            let mut result_rows = prepared.query([])?;
            let mut collected = Vec::new();
            while let Some(row) = result_rows.next()? {
                let mut out_row = Vec::with_capacity(col_names.len());
                for idx in 0..col_names.len() {
                    let val: Value = row.get(idx)?;
                    out_row.push(duckdb_value_to_json(&val));
                }
                collected.push(out_row);
            }

            if is_last {
                columns = col_names;
                rows_affected = collected.len();
                rows = collected;
            }
        } else {
            // DDL/DML — execute for side effects.
            let affected = prepared.execute([])?;
            if is_last {
                rows_affected = affected;
            }
        }
    }

    Ok(QueryResult {
        columns,
        rows,
        rows_affected,
        execution_ms: start.elapsed().as_millis(),
    })
}

/// A single column definition supplied by the frontend's import dialog
/// (Milestone 2: clipboard paste / manual paste-to-table).
#[derive(Debug, serde::Deserialize)]
pub struct ColumnDef {
    pub name: String,
    pub data_type: String,
}

fn quote_ident(s: &str) -> String {
    format!("\"{}\"", s.replace('"', "\"\""))
}

/// Renders a JSON value (as sent from the frontend's type-coerced import
/// payload) as a DuckDB SQL literal. Values are already coerced to the
/// right JS type client-side (numbers, booleans, strings, null), so this
/// only has to handle escaping — not re-inferring types.
///
/// Deliberately literal-based rather than parameter-bound: this sidesteps
/// depending on duckdb-rs's parameter-binding API surface, which nothing
/// elsewhere in this codebase exercises yet. Safe here because DuckPad is
/// a local single-user desktop tool with no untrusted network input —
/// this is not a general-purpose SQL-building utility.
fn json_value_to_sql_literal(v: &serde_json::Value) -> String {
    match v {
        serde_json::Value::Null => "NULL".to_string(),
        serde_json::Value::Bool(b) => if *b { "TRUE" } else { "FALSE" }.to_string(),
        serde_json::Value::Number(n) => n.to_string(),
        serde_json::Value::String(s) => format!("'{}'", s.replace('\'', "''")),
        other => format!("'{}'", other.to_string().replace('\'', "''")),
    }
}

/// Finds the next unused `scratch_N` name. Must be called with the DB
/// mutex already held (see `import_table`) — does not lock itself, so it
/// can be reused inside a call that's already holding the guard without
/// deadlocking on the same non-reentrant Mutex.
fn next_scratch_name_locked(conn: &Connection) -> Result<String, DbError> {
    let mut stmt = conn.prepare(
        "SELECT table_name FROM information_schema.tables \
         WHERE table_schema = 'main' AND table_name LIKE 'scratch\\_%' ESCAPE '\\'",
    )?;
    let names: Vec<String> = stmt
        .query_map([], |row| row.get::<_, String>(0))?
        .filter_map(|r| r.ok())
        .collect();
    let max_n = names
        .iter()
        .filter_map(|n| n.strip_prefix("scratch_").and_then(|s| s.parse::<u32>().ok()))
        .max()
        .unwrap_or(0);
    Ok(format!("scratch_{}", max_n + 1))
}

/// Public entry point for the frontend to preview the next scratch name
/// before the user has pasted anything (locks internally).
pub fn next_scratch_name() -> Result<String, DbError> {
    let conn = DB.lock().map_err(|_| DbError::Lock)?;
    next_scratch_name_locked(&conn)
}

/// Creates (replacing if it already exists) a table from column defs and
/// row data supplied by the frontend's paste/import dialog, then returns
/// its schema so the caller can render it immediately without a second
/// round trip.
pub fn import_table(
    table_name: Option<String>,
    columns: Vec<ColumnDef>,
    rows: Vec<Vec<serde_json::Value>>,
) -> Result<TableInfo, DbError> {
    let conn = DB.lock().map_err(|_| DbError::Lock)?;

    let name = match table_name {
        Some(n) if !n.trim().is_empty() => n.trim().to_string(),
        _ => next_scratch_name_locked(&conn)?,
    };

    let col_defs: Vec<String> = columns
        .iter()
        .map(|c| format!("{} {}", quote_ident(&c.name), c.data_type))
        .collect();

    conn.execute(&format!("DROP TABLE IF EXISTS {}", quote_ident(&name)), [])?;
    conn.execute(
        &format!("CREATE TABLE {} ({})", quote_ident(&name), col_defs.join(", ")),
        [],
    )?;

    if !rows.is_empty() {
        let rows_sql: Vec<String> = rows
            .iter()
            .map(|row| {
                let vals: Vec<String> = row.iter().map(json_value_to_sql_literal).collect();
                format!("({})", vals.join(", "))
            })
            .collect();
        let insert_sql = format!("INSERT INTO {} VALUES {}", quote_ident(&name), rows_sql.join(", "));
        conn.execute(&insert_sql, [])?;
    }

    drop(conn); // release before get_schema (which locks again) to avoid deadlock
    get_schema()?
        .into_iter()
        .find(|t| t.name == name)
        .ok_or_else(|| DbError::NotFound(name.clone()))
}

/// Introspects the current schema so the frontend's Schema Explorer can
/// re-render after every executed statement — no manual refresh.
pub fn get_schema() -> Result<Vec<TableInfo>, DbError> {
    let conn = DB.lock().map_err(|_| DbError::Lock)?;

    let mut table_stmt = conn.prepare(
        "SELECT table_name FROM information_schema.tables \
         WHERE table_schema = 'main' ORDER BY table_name",
    )?;
    let table_names: Vec<String> = table_stmt
        .query_map([], |row| row.get::<_, String>(0))?
        .filter_map(|r| r.ok())
        .collect();

    let mut tables = Vec::with_capacity(table_names.len());
    for name in table_names {
        let mut col_stmt = conn.prepare(
            "SELECT column_name, data_type FROM information_schema.columns \
             WHERE table_schema = 'main' AND table_name = ? ORDER BY ordinal_position",
        )?;
        let columns: Vec<ColumnInfo> = col_stmt
            .query_map([&name], |row| {
                Ok(ColumnInfo {
                    name: row.get(0)?,
                    data_type: row.get(1)?,
                })
            })?
            .filter_map(|r| r.ok())
            .collect();

        tables.push(TableInfo { name, columns });
    }

    Ok(tables)
}
