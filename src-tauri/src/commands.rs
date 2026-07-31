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

/// Payload shape sent by PasteImportDialog.tsx. `table_name` is always
/// populated by the dialog (pre-filled with a suggested scratch_N name
/// the user can edit), but stays optional here so a future caller could
/// omit it and let the backend assign one.
#[derive(serde::Deserialize)]
pub struct ImportTableRequest {
    pub table_name: Option<String>,
    pub columns: Vec<db::ColumnDef>,
    pub rows: Vec<Vec<serde_json::Value>>,
}

#[tauri::command]
pub fn import_table(req: ImportTableRequest) -> Result<db::TableInfo, ExecuteError> {
    db::import_table(req.table_name, req.columns, req.rows).map_err(|e| ExecuteError {
        message: e.to_string(),
    })
}

#[tauri::command]
pub fn next_scratch_name() -> Result<String, ExecuteError> {
    db::next_scratch_name().map_err(|e| ExecuteError {
        message: e.to_string(),
    })
}
