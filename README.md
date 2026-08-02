# DuckPad Lite

A portable, single-file SQL playground. Paste tabular data — from Excel,
Google Sheets, a CSV, anything tab/comma/pipe/semicolon-delimited — and it's
instantly a queryable table (`table1`, `table2`, ...) with SQL ready to run.
No import wizard, no manual schema, no database connection dialog.

## Stack (and why it changed)

This project started as a Tauri + React + Monaco + AG Grid + DuckDB build
(see `legacy-tauri-attempt/` for that code, kept for reference, not maintained).
It's now **Python + tkinter + sqlite3/duckdb**, packaged into a single `.exe`
by PyInstaller. Reasoning:

- **tkinter and sqlite3 are both in Python's standard library.** Nothing to
  bundle, nothing to version-mismatch, nothing that can silently fail to
  register at runtime.
- **PyInstaller's `--onefile` mode is the most battle-tested "one exe, zero
  installs" packager that exists** — that's the actual ask.
- Every piece of this has been built and verified end-to-end in the same
  environment that wrote it: unit tests actually run (not just written), the
  GUI was launched headlessly (Xvfb) and driven through every flow described
  below, and the packaged `--onefile` binary (including the DuckDB backend)
  was launched and confirmed to stay alive.

## Milestone status (honest, mapped to the original spec)

**Milestone 1 — Foundation**: done except syntax highlighting is keyword-only
(no full tokenizer), and there's no autocomplete or bracket-matching yet.
Dark theme, SQL editor with line numbers + comment-toggle (Ctrl+/), Ctrl+Enter
execution, results grid — all working.

**Milestone 2 — Data Import**: done. Clipboard paste and "Open CSV" both
auto-detect delimiter/header/types and create `table1`/`table2`/... with zero
manual steps. "Open CSV" additionally shows an import dialog (table name,
header yes/no/auto, separator override, live preview) for when auto-detection
needs a nudge.

**Milestone 3 — Data Management**: done. Double-clicking a cell in a plain
`SELECT * FROM <table>` result generates and runs an
`UPDATE ... WHERE <first-column> = <value>` — this is a heuristic (treats the
first column as the key), not full primary-key introspection, so it's most
reliable on tables with an obvious ID column. CSV export works. Right-click
a table in the Tables panel for View Data / Rename / Duplicate / Export CSV /
Delete; right-click a column for Rename / Change Datatype / Delete.

**Milestone 4 — Productivity**: done at a basic level. Multiple SQL tabs,
query history (session-based, up to 200 entries), and saved queries
(persisted to a small JSON file in your home directory, so they survive
restarts). No workspace save/restore of full session state yet.

**Backend choice**: a startup dialog lets you pick SQLite or DuckDB per
session. SQLite is always available; DuckDB requires the `duckdb` package
(bundled into the `.exe` by CI, so the built binary has it either way).
DuckDB gives native DATE/TIMESTAMP/BOOLEAN types instead of SQLite's
text/integer affinity workarounds.

**Paste behavior**: `Ctrl+V` is normal text paste everywhere (SQL editor,
dialogs). `Ctrl+Shift+V` is "paste as table" — works no matter which panel
has focus, and always opens the import dialog first so you can rename the
table and override any column's name/datatype before anything is created
(same dialog "Open CSV" uses).

**Results grid**: columns size themselves from actual content (with a sane
floor/ceiling) and keep that width — a horizontal scrollbar appears instead
of every column getting squeezed illegibly when there are more than a few.

## What's still not here

- Full autocomplete, bracket-matching, find/replace in the SQL editor.
- Cell editing for JOINs/aggregated results (only plain single-table SELECTs
  are treated as editable).
- Workspace save/open (persisting which tabs + queries were open).

## Getting the exe

Push to `main` (or trigger the workflow manually) and check the **Actions**
tab: `build-windows-exe` produces `DuckPadLite.exe` as a downloadable
artifact. No Python, no installer, no admin rights needed to run it.

## Running from source

```bash
pip install duckdb   # optional -- only needed if you want the DuckDB engine option
python3 main.py
```

## Running tests

```bash
python3 -m unittest duckpad.tests.test_core -v
```

## Building the exe yourself

```bash
pip install pyinstaller duckdb
pyinstaller --onefile --windowed --name DuckPadLite --add-data "duckpad;duckpad" --hidden-import duckdb --icon "assets/icon.ico" main.py
```

(On Windows, use `;` as the `--add-data` separator as shown above; on
macOS/Linux it's `:`. The icon only embeds on Windows/macOS builds --
PyInstaller ignores `--icon` on Linux, which is expected.)

## License

MIT
