use crate::db;
use serde::Serialize;

#[derive(Serialize)]
pub struct ExecuteError {
    pub message: String,
}

/// Executes SQL text from the editor. Errors are returned as a structured
/// value (not a Rust panic) so the frontend can render them in the
/// Messages tab instead of crashing the app.
#[tauri::command]
pub fn execute_sql(sql: String) -> Result<db::QueryResult, ExecuteError> {
    db::execute_sql(&sql).map_err(|e| ExecuteError {
        message: e.to_string(),
    })
}

#[tauri::command]
pub fn get_schema() -> Result<Vec<db::TableInfo>, ExecuteError> {
    db::get_schema().map_err(|e| ExecuteError {
        message: e.to_string(),
    })
}
