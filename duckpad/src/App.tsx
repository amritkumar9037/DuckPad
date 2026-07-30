import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import SqlEditor from "./components/SqlEditor";
import ResultsGrid from "./components/ResultsGrid";
import SchemaExplorer from "./components/SchemaExplorer";
import StatusBar from "./components/StatusBar";

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

  useEffect(() => {
    refreshSchema();
  }, [refreshSchema]);

  return (
    <div className="app-shell">
      <header className="titlebar">
        <span className="brand">DuckPad</span>
        <span className="titlebar-status">
          <span className="dot dot-green" /> DuckDB
        </span>
      </header>

      <div className="main-layout">
        <SchemaExplorer tables={tables} />

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
    </div>
  );
}
