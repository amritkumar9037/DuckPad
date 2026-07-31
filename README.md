# DuckPad

> The fastest path from tabular data to SQL.

DuckPad is an offline, portable SQL playground. Copy tabular data, paste it,
and it becomes a queryable DuckDB table instantly — no database creation,
no CSV import wizard, no setup.

This repo contains the **Milestone 1** build: Tauri shell + React/TypeScript
frontend + embedded DuckDB + Monaco SQL editor + results grid, with
execute-and-display working end to end.

---

## ⚠️ Important note on what's included

This code was generated in a sandboxed environment with **no internet
access**, so it could not be compiled, `npm install`ed, or packaged into an
`.exe` here. Every file below is real, complete source — not a mockup — but
you need to build it on your own machine (or CI) to get a running app and a
portable executable. Setup and build steps are below and are the same steps
a developer would run day one on this project.

---

## Architecture

```
┌─────────────────────────────────────────────┐
│              Tauri Shell (Rust)              │
│  ┌─────────────┐        ┌─────────────────┐ │
│  │  DuckDB      │◄──────►│ Command Layer   │ │
│  │  (embedded,  │        │ (execute_sql,   │ │
│  │  in-process) │        │  get_schema,    │ │
│  │              │        │  paste_to_table)│ │
│  └─────────────┘        └────────┬────────┘ │
└───────────────────────────────────┼──────────┘
                                     │ IPC (invoke)
┌───────────────────────────────────▼──────────┐
│              React + TypeScript UI            │
│  SchemaExplorer │ SqlEditor(Monaco) │ Grid    │
│                 │  StatusBar                  │
└─────────────────────────────────────────────┘
```

- **Rust backend** owns the DuckDB connection, clipboard/CSV parsing, and
  schema introspection. Frontend never touches SQL execution directly —
  it always goes through a Tauri command, so behavior stays consistent
  and testable.
- **Frontend** is presentation + editor state only. It calls `invoke()`
  and renders what comes back.
- State (current workspace, tables) lives in Rust; the frontend re-fetches
  schema after every executed statement rather than trying to keep its
  own copy in sync — simpler, and correctness matters more than a diff.

## Folder structure

```
duckpad/
├── src-tauri/                 # Rust backend (Tauri)
│   ├── Cargo.toml
│   ├── tauri.conf.json
│   └── src/
│       ├── main.rs            # app entrypoint, command registration
│       ├── db.rs              # DuckDB connection + query execution
│       └── commands.rs        # Tauri commands exposed to the frontend
├── src/                       # React frontend
│   ├── main.tsx
│   ├── App.tsx
│   ├── components/
│   │   ├── SqlEditor.tsx      # Monaco wrapper
│   │   ├── ResultsGrid.tsx    # AG Grid wrapper
│   │   ├── SchemaExplorer.tsx # left panel, live table/column tree
│   │   └── StatusBar.tsx
│   └── styles/
│       └── globals.css
├── index.html
├── package.json
├── tsconfig.json
└── vite.config.ts
```

## Setup (run locally)

Prerequisites: Node.js 18+, Rust stable + `cargo`, and the Tauri 2.x system
dependencies for your OS (see https://v2.tauri.app/start/prerequisites/).

```bash
npm install
npm install @tauri-apps/cli@^2 --save-dev
cd src-tauri && cargo fetch && cd ..
```

## Development

```bash
npm run tauri dev
```

This launches the app with hot reload on the frontend and the Rust backend
compiled in debug mode.

## Building the portable executable (Windows)

```bash
npm run tauri build -- --bundles none
```

`--bundles none` skips the MSI/NSIS installer and just produces the raw
executable at:

```
src-tauri/target/release/duckpad.exe
```

Copy that alongside the DuckDB shared library (statically linked by default
with the `bundled` feature used in `Cargo.toml`, so no separate `.dll` is
needed) into a folder, e.g.:

```
DuckPad/
├── DuckPad.exe
└── (no other files needed — DuckDB is statically linked)
```

Zip that folder → `DuckPad.zip`. That's the portable package: extract,
double-click `DuckPad.exe`, no installer, no admin rights, no registry
writes (Tauri does not require them for a portable build).

## Testing strategy

- **Rust**: `cargo test` in `src-tauri` — unit tests for `db.rs` covering
  scratch-table naming, type inference, and SQL execution against an
  in-memory DuckDB instance (fast, no file I/O).
- **Frontend**: Vitest + React Testing Library for component behavior
  (e.g., `SqlEditor` fires execute on Ctrl+Enter); Playwright/Tauri driver
  for a smoke E2E test once Milestone 2 lands paste-to-table.
- Milestone 1 acceptance test: paste `CREATE TABLE t(x INT); INSERT INTO t
  VALUES (1),(2); SELECT * FROM t;` into the editor, Ctrl+Enter, assert the
  grid shows 2 rows and the schema explorer lists `t`.

## Roadmap

See milestone breakdown in the original spec — this build covers
**Milestone 1 only** (foundation: Tauri + DuckDB + Monaco + execute +
display). Milestones 2–5 (scratch tables/clipboard paste, cell editing,
query history/tabs, profiling) are intentionally not implemented yet; the
command layer (`commands.rs`) is structured so `paste_to_table` and
`update_cell` can be added as new commands without touching the frontend's
IPC pattern.
