// Prevents an extra console window from appearing on Windows in release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod db;

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            commands::execute_sql,
            commands::get_schema,
            commands::import_table,
            commands::next_scratch_name,
        ])
        .run(tauri::generate_context!())
        .expect("error while running DuckPad");
}
