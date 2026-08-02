# DuckPad Lite

A portable, single-file SQL playground. Paste tabular data — from Excel,
Google Sheets, a CSV, anything tab/comma/pipe/semicolon-delimited — and it's
instantly a queryable table (`table1`, `table2`, ...) with SQL ready to run.
No import wizard, no manual schema, no database connection dialog.

## Stack (and why it changed)

This project started as a Tauri + React + Monaco + AG Grid + DuckDB build
(see `legacy-tauri-attempt/` for that code, kept for reference, not maintained).
It's now **Python + tkinter + sqlite3**, packaged into a single `.exe` by
PyInstaller. Reasoning:

- **tkinter and sqlite3 are both in Python's standard library.** Nothing to
  bundle, nothing to version-mismatch, nothing that can silently fail to
  register at runtime.
- **PyInstaller's `--onefile` mode is the most battle-tested "one exe, zero
  installs" packager that exists** — that's the actual ask.
- Every piece of this was built and verified end-to-end in the same
  environment that wrote it: the parsing/type-inference/SQL logic has real
  passing unit tests, and the GUI itself was launched headlessly (Xvfb),
  driven through the exact "paste Excel data -> table1 created -> SQL
  pre-filled -> results shown" flow, and confirmed not to crash -- not asserted,
  actually run. The packaged `--onefile` binary was also launched and
  confirmed to stay alive. That's a materially stronger guarantee than the
  Tauri attempt ever got, because that stack couldn't be compiled or rendered
  in the environment building it.

## What works (verified)

- Delimiter auto-detection: tab, comma, pipe, semicolon, or space-separated.
- Header row auto-detection (works even with just 2 data rows).
- Column type inference: INTEGER -> REAL, BOOLEAN, DATE/TIMESTAMP -> TEXT
  fallback, smallest-safe-type first.
- Paste (Ctrl+V) or Open CSV -> auto-creates `table1`/`table2`/... in an
  in-memory SQLite database, no manual steps.
- SQL editor with Ctrl+Enter / Run button -- full SQLite SQL (joins, CTEs,
  window functions, etc.).
- Results grid, schema explorer (auto-refreshes after DDL), CSV export.
- 17 unit tests covering parser/schema/db logic, run on every push via CI.

## What's NOT here yet

- Cell editing / undo-redo, right-click context menus, multi-tab workspace,
  query history, autocomplete, syntax highlighting.
- The original spec's DuckDB backend (this uses SQLite -- full SQL, but not
  DuckDB's analytical-query extensions like `PIVOT`/`QUALIFY`).

## Getting the exe

Push to `main` (or trigger the workflow manually) and check the **Actions**
tab: `build-windows-exe` produces `DuckPadLite.exe` as a downloadable
artifact. No Python, no installer, no admin rights needed to run it.

## Running from source

```bash
python3 main.py
```

## Running tests

```bash
python3 -m unittest duckpad.tests.test_core -v
```

## Building the exe yourself

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name DuckPadLite --add-data "duckpad;duckpad" main.py
```

(On Windows, use `;` as the `--add-data` separator as shown above; on
macOS/Linux it's `:`.)

## License

MIT
