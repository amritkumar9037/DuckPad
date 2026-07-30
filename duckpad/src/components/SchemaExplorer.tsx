import { useState } from "react";
import { Table2, ChevronRight, ChevronDown } from "lucide-react";
import type { TableInfo } from "../App";

interface Props {
  tables: TableInfo[];
}

function TableNode({ table }: { table: TableInfo }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="table-node">
      <button className="table-node-header" onClick={() => setOpen((o) => !o)}>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <Table2 size={14} />
        <span>{table.name}</span>
      </button>
      {open && (
        <ul className="column-list">
          {table.columns.map((col) => (
            <li key={col.name}>
              <span className="col-name">{col.name}</span>
              <span className="col-type">{col.data_type}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function SchemaExplorer({ tables }: Props) {
  return (
    <aside className="schema-explorer">
      <div className="schema-header">Tables</div>
      <div className="schema-list">
        {tables.length === 0 ? (
          <p className="schema-empty">No tables yet — run a CREATE TABLE to get started.</p>
        ) : (
          tables.map((t) => <TableNode key={t.name} table={t} />)
        )}
      </div>
    </aside>
  );
}
