// Infers DuckDB column types from raw string cell values, for the
// clipboard-paste and CSV-import flows (Milestone 2).
//
// This is intentionally a simple, explainable heuristic — not a general
// CSV-sniffing library. Per-column type can always be overridden by the
// user in the import dialog before the table is created.

export type DuckType =
  | "INTEGER"
  | "BIGINT"
  | "DOUBLE"
  | "BOOLEAN"
  | "DATE"
  | "TIMESTAMP"
  | "VARCHAR";

export const DUCK_TYPES: DuckType[] = [
  "INTEGER",
  "BIGINT",
  "DOUBLE",
  "BOOLEAN",
  "DATE",
  "TIMESTAMP",
  "VARCHAR",
];

const INT_RE = /^[+-]?\d+$/;
const FLOAT_RE = /^[+-]?(\d+\.\d*|\.\d+)$/;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const TIMESTAMP_RE = /^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/;
const BOOL_VALUES = new Set(["true", "false"]);

const NUMERIC_RANK: DuckType[] = ["BOOLEAN", "INTEGER", "BIGINT", "DOUBLE"];

function inferCellType(raw: string): DuckType | "NULL" {
  const v = raw.trim();
  if (v === "") return "NULL";
  if (BOOL_VALUES.has(v.toLowerCase())) return "BOOLEAN";
  if (TIMESTAMP_RE.test(v)) return "TIMESTAMP";
  if (DATE_RE.test(v)) return "DATE";
  if (INT_RE.test(v)) {
    const n = Number(v);
    return Number.isSafeInteger(n) ? "INTEGER" : "BIGINT";
  }
  if (FLOAT_RE.test(v)) return "DOUBLE";
  return "VARCHAR";
}

function widen(a: DuckType | "NULL", b: DuckType | "NULL"): DuckType | "NULL" {
  if (a === b) return a;
  if (a === "NULL") return b;
  if (b === "NULL") return a;

  const ai = NUMERIC_RANK.indexOf(a);
  const bi = NUMERIC_RANK.indexOf(b);
  if (ai !== -1 && bi !== -1) return NUMERIC_RANK[Math.max(ai, bi)];

  if ((a === "DATE" && b === "TIMESTAMP") || (a === "TIMESTAMP" && b === "DATE")) {
    return "TIMESTAMP";
  }
  return "VARCHAR";
}

/** Infers a single column's type by widening across every value in it. */
export function inferColumnType(values: string[]): DuckType {
  let current: DuckType | "NULL" = "NULL";
  for (const v of values) {
    current = widen(current, inferCellType(v));
  }
  // An all-empty / all-null column has no evidence either way — default
  // to VARCHAR rather than leaving a non-SQL "NULL" type on the wire.
  return current === "NULL" ? "VARCHAR" : current;
}

export interface InferredColumn {
  name: string;
  data_type: DuckType;
}

export function inferSchema(headers: string[], rows: string[][]): InferredColumn[] {
  return headers.map((name, i) => ({
    name,
    data_type: inferColumnType(rows.map((r) => r[i] ?? "")),
  }));
}

/** Converts a raw string cell to the JSON value DuckDB should receive,
 *  given the column's chosen type. Empty string always means NULL. */
export function coerceCell(raw: string, type: DuckType): unknown {
  const v = raw.trim();
  if (v === "") return null;
  switch (type) {
    case "INTEGER":
    case "BIGINT":
    case "DOUBLE":
      return Number(v);
    case "BOOLEAN":
      return v.toLowerCase() === "true";
    default:
      return v;
  }
}

/** Best-guess delimiter for pasted/typed tabular text: picks whichever of
 *  tab/comma/pipe/semicolon appears most often in the first line. Tab wins
 *  ties since that's what Excel/Sheets clipboard copies use. */
export function detectDelimiter(text: string): string {
  const firstLine = text.split(/\r\n|\n/)[0] ?? "";
  const candidates: [string, number][] = [
    ["\t", (firstLine.match(/\t/g) || []).length],
    [",", (firstLine.match(/,/g) || []).length],
    ["|", (firstLine.match(/\|/g) || []).length],
    [";", (firstLine.match(/;/g) || []).length],
  ];
  candidates.sort((a, b) => b[1] - a[1]);
  return candidates[0][1] > 0 ? candidates[0][0] : "\t";
}

/** Naive delimited-text parser: splits on the delimiter with no quoted-
 *  field handling. Fine for the plain tab-separated data Excel/Sheets
 *  puts on the clipboard; a quote-aware parser is a Milestone 3+ upgrade
 *  once real CSV files (which do use quoted fields) come into scope. */
export function parseDelimited(text: string, delimiter: string): string[][] {
  return text
    .split(/\r\n|\n/)
    .filter((line) => line.length > 0)
    .map((line) => line.split(delimiter));
}

/** Produces safe, unique-enough SQL identifiers from raw header text
 *  (spaces, punctuation, leading digits, duplicates). */
export function sanitizeHeaders(headers: string[]): string[] {
  const seen = new Map<string, number>();
  return headers.map((raw, i) => {
    let clean = raw
      .trim()
      .replace(/[^a-zA-Z0-9_]/g, "_")
      .replace(/^(\d)/, "_$1");
    if (clean === "") clean = `column_${i + 1}`;
    const count = seen.get(clean) ?? 0;
    seen.set(clean, count + 1);
    return count === 0 ? clean : `${clean}_${count + 1}`;
  });
}
