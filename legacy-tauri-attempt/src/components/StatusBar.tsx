interface Props {
  tableCount: number;
  rowCount: number;
  executionMs?: number;
  running: boolean;
}

export default function StatusBar({ tableCount, rowCount, executionMs, running }: Props) {
  return (
    <footer className="status-bar">
      <span>{running ? "Running…" : "Ready"}</span>
      <span>{tableCount} Tables</span>
      <span>{rowCount} Rows</span>
      {executionMs !== undefined && <span>{executionMs} ms</span>}
    </footer>
  );
}
