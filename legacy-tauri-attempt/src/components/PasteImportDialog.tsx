import { useMemo, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { X } from "lucide-react";
import {
  DUCK_TYPES,
  DuckType,
  coerceCell,
  detectDelimiter,
  inferSchema,
  parseDelimited,
  sanitizeHeaders,
} from "../lib/importParsing";
import type { TableInfo } from "../App";

interface Props {
  initialText: string;
  suggestedName: string;
  onClose: () => void;
  onImported: (table: TableInfo) => void;
}

const DELIMITER_OPTIONS: { label: string; value: string | "auto" }[] = [
  { label: "Auto", value: "auto" },
  { label: "Comma", value: "," },
  { label: "Tab", value: "\t" },
  { label: "Pipe", value: "|" },
  { label: "Semicolon", value: ";" },
];

const PREVIEW_ROWS = 8;

export default function PasteImportDialog({ initialText, suggestedName, onClose, onImported }: Props) {
  const [text, setText] = useState(initialText);
  const [tableName, setTableName] = useState(suggestedName);
  const [hasHeader, setHasHeader] = useState(true);
  const [delimiterChoice, setDelimiterChoice] = useState<string | "auto">("auto");
  const [typeOverrides, setTypeOverrides] = useState<Record<string, DuckType>>({});
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const delimiter = delimiterChoice === "auto" ? detectDelimiter(text) : delimiterChoice;

  const parsed = useMemo(() => {
    const allRows = parseDelimited(text, delimiter);
    if (allRows.length === 0) return { headers: [] as string[], dataRows: [] as string[][] };

    const headers = hasHeader
      ? sanitizeHeaders(allRows[0])
      : allRows[0].map((_, i) => `column_${i + 1}`);
    const dataRows = hasHeader ? allRows.slice(1) : allRows;
    return { headers, dataRows };
  }, [text, delimiter, hasHeader]);

  const inferred = useMemo(
    () => inferSchema(parsed.headers, parsed.dataRows),
    [parsed.headers, parsed.dataRows]
  );

  const effectiveColumns = inferred.map((c) => ({
    name: c.name,
    data_type: typeOverrides[c.name] ?? c.data_type,
  }));

  const handleImport = async () => {
    if (parsed.headers.length === 0) {
      setError("Nothing to import — paste some tabular data first.");
      return;
    }
    if (!tableName.trim()) {
      setError("Table name can't be empty.");
      return;
    }

    setImporting(true);
    setError(null);
    try {
      const rows = parsed.dataRows.map((row) =>
        effectiveColumns.map((col, i) => coerceCell(row[i] ?? "", col.data_type))
      );
      const table = await invoke<TableInfo>("import_table", {
        req: {
          table_name: tableName.trim(),
          columns: effectiveColumns,
          rows,
        },
      });
      onImported(table);
      onClose();
    } catch (e) {
      const err = e as { message?: string };
      setError(err.message ?? String(e));
    } finally {
      setImporting(false);
    }
  };

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog-panel" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-header">
          <span>Import table</span>
          <button className="dialog-close" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>

        <div className="dialog-body">
          <label className="dialog-field">
            <span>Table name</span>
            <input value={tableName} onChange={(e) => setTableName(e.target.value)} />
          </label>

          <div className="dialog-row">
            <label className="dialog-field">
              <span>Header row</span>
              <select
                value={hasHeader ? "yes" : "no"}
                onChange={(e) => setHasHeader(e.target.value === "yes")}
              >
                <option value="yes">Yes</option>
                <option value="no">No</option>
              </select>
            </label>

            <label className="dialog-field">
              <span>Separator</span>
              <select value={delimiterChoice} onChange={(e) => setDelimiterChoice(e.target.value)}>
                {DELIMITER_OPTIONS.map((o) => (
                  <option key={o.label} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <label className="dialog-field">
            <span>Data (paste with Ctrl+V, or type/edit directly)</span>
            <textarea
              className="dialog-textarea"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={"Name\tAge\tSalary\nJohn\t30\t50000\nMary\t28\t60000"}
              rows={6}
            />
          </label>

          {parsed.headers.length > 0 && (
            <div className="dialog-preview">
              <div className="dialog-preview-label">
                Preview — {parsed.dataRows.length} row{parsed.dataRows.length === 1 ? "" : "s"} detected
              </div>
              <table className="preview-table">
                <thead>
                  <tr>
                    {inferred.map((c) => (
                      <th key={c.name}>
                        <div className="preview-col-name">{c.name}</div>
                        <select
                          className="preview-type-select"
                          value={typeOverrides[c.name] ?? c.data_type}
                          onChange={(e) =>
                            setTypeOverrides((prev) => ({
                              ...prev,
                              [c.name]: e.target.value as DuckType,
                            }))
                          }
                        >
                          {DUCK_TYPES.map((t) => (
                            <option key={t} value={t}>
                              {t}
                            </option>
                          ))}
                        </select>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {parsed.dataRows.slice(0, PREVIEW_ROWS).map((row, ri) => (
                    <tr key={ri}>
                      {inferred.map((_, ci) => (
                        <td key={ci}>{row[ci] ?? ""}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {error && <div className="dialog-error">{error}</div>}
        </div>

        <div className="dialog-footer">
          <button className="dialog-btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button className="dialog-btn-primary" onClick={handleImport} disabled={importing}>
            {importing ? "Importing…" : "Import"}
          </button>
        </div>
      </div>
    </div>
  );
}
