import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import SqlEditor from "./components/SqlEditor";
import ResultsGrid from "./components/ResultsGrid";
import SchemaExplorer from "./components/SchemaExplorer";
import StatusBar from "./components/StatusBar";
import PasteImportDialog from "./components/PasteImportDialog";

export interface QueryResult {
  columns: string[];
  rows: unknown[][];
  rows_affected: number;
  execution_ms: number;
}

export interface ColumnInfo {
  name: string;
  data_type: string;
}

export interface TableInfo {
  name: string;
  columns: ColumnInfo[];
}

const DEFAULT_SQL = `-- Welcome to DuckPad.
-- Paste data anywhere, or write SQL straight away. Ctrl+Enter to run.

SELECT 'hello, duckpad' AS greeting, 42 AS answer;`;

export default function App() {
  const [sql, setSql] = useState(DEFAULT_SQL);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [running, setRunning] = useState(false);

  // Milestone 2: paste-to-scratch-table dialog state. `dialogText` holds
  // whatever we already have (clipboard contents, or empty for a manual
  // "+ Import CSV" open) so the dialog opens pre-filled when possible.
  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogText, setDialogText] = useState("");

  const refreshSchema = useCallback(async () => {
    try {
      const schema = await invoke<TableInfo[]>("get_schema");
      setTables(schema);
    } catch (e) {
      // Schema refresh failing shouldn't block the editor — surface it
      // quietly in the console rather than stealing focus with an error.
      console.error("schema refresh failed", e);
    }
  }, []);

  const runQuery = useCallback(
    async (text: string) => {
      setRunning(true);
      setError(null);
      try {
        const res = await invoke<QueryResult>("execute_sql", { sql: text });
        setResult(res);
        await refreshSchema();
      } catch (e) {
        const err = e as { message?: string };
        setError(err.message ?? String(e));
        setResult(null);
      } finally {
        setRunning(false);
      }
    },
    [refreshSchema]
  );

  const openImportDialog = useCallback((text: string) => {
    setDialogText(text);
    setDialogOpen(true);
  }, []);

  // "+ Scratch" button and Ctrl+Shift+V both try to read the OS clipboard
  // directly via the browser Clipboard API first (fastest path — no manual
  // paste needed). If that's denied or unsupported in this webview, we
  // fall back to opening the dialog empty; the dialog's own textarea
  // always accepts a normal Ctrl+V paste regardless of Clipboard API
  // permissions, so this never leaves the user stuck.
  const tryReadClipboard = useCallback(async () => {
    try {
      const text = await navigator.clipboard.readText();
      openImportDialog(text);
    } catch (e) {
      console.warn("clipboard read denied/unavailable, opening blank import dialog", e);
      openImportDialog("");
    }
  }, [openImportDialog]);

  useEffect(() => {
    refreshSchema();
  }, [refreshSchema]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === "v") {
        e.preventDefault();
        tryReadClipboard();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [tryReadClipboard]);

  const nextScratchNameGuess = `scratch_${tables.filter((t) => /^scratch_\d+$/.test(t.name)).length + 1}`;

  return (
    <div className="app-shell">
      <header className="titlebar">
        <span className="brand">DuckPad</span>
        <span className="titlebar-status">
          <span className="dot dot-green" /> DuckDB
        </span>
      </header>

      <div className="main-layout">
        <SchemaExplorer
          tables={tables}
          onPasteClick={tryReadClipboard}
          onImportClick={() => openImportDialog("")}
        />

        <div className="editor-and-results">
          <SqlEditor value={sql} onChange={setSql} onExecute={runQuery} running={running} />
          <ResultsGrid result={result} error={error} />
        </div>
      </div>

      <StatusBar
        tableCount={tables.length}
        rowCount={result?.rows_affected ?? 0}
        executionMs={result?.execution_ms}
        running={running}
      />

      {dialogOpen && (
        <PasteImportDialog
          initialText={dialogText}
          suggestedName={nextScratchNameGuess}
          onClose={() => setDialogOpen(false)}
          onImported={() => refreshSchema()}
        />
      )}
    </div>
  );
}
