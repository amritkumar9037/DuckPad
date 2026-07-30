import { useMemo, useState } from "react";
import { AgGridReact } from "ag-grid-react";
import type { ColDef } from "ag-grid-community";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-alpine.css";
import type { QueryResult } from "../App";

interface Props {
  result: QueryResult | null;
  error: string | null;
}

type Tab = "results" | "messages";

export default function ResultsGrid({ result, error }: Props) {
  const [tab, setTab] = useState<Tab>("results");

  const columnDefs: ColDef[] = useMemo(
    () =>
      (result?.columns ?? []).map((c) => ({
        field: c,
        headerName: c,
        sortable: true,
        filter: true,
        resizable: true,
        editable: true, // cell edit UI is wired here; Milestone 3 adds the UPDATE-on-edit command
      })),
    [result?.columns]
  );

  const rowData = useMemo(
    () =>
      (result?.rows ?? []).map((row) => {
        const obj: Record<string, unknown> = {};
        result?.columns.forEach((col, i) => {
          obj[col] = row[i];
        });
        return obj;
      }),
    [result]
  );

  return (
    <div className="results-panel">
      <div className="results-tabs">
        <button className={tab === "results" ? "active" : ""} onClick={() => setTab("results")}>
          Results
        </button>
        <button className={tab === "messages" ? "active" : ""} onClick={() => setTab("messages")}>
          Messages
        </button>
      </div>

      {tab === "results" && (
        <div className="ag-theme-alpine-dark results-grid">
          <AgGridReact rowData={rowData} columnDefs={columnDefs} animateRows={false} />
        </div>
      )}

      {tab === "messages" && (
        <div className="messages-panel">
          {error ? (
            <pre className="message-error">{error}</pre>
          ) : result ? (
            <pre className="message-ok">
              {`Rows affected: ${result.rows_affected}\nExecution time: ${result.execution_ms} ms\nWarnings: none`}
            </pre>
          ) : (
            <p className="message-empty">Run a query to see messages.</p>
          )}
        </div>
      )}
    </div>
  );
}
