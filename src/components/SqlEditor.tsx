import { useRef } from "react";
import Editor, { OnMount } from "@monaco-editor/react";
import { Play, Loader2 } from "lucide-react";

interface Props {
  value: string;
  onChange: (v: string) => void;
  onExecute: (sql: string) => void;
  running: boolean;
}

export default function SqlEditor({ value, onChange, onExecute, running }: Props) {
  const editorRef = useRef<Parameters<OnMount>[0] | null>(null);

  const handleMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;

    // Ctrl+Enter (Cmd+Enter on mac) executes the selection if there is
    // one, otherwise the whole editor contents — matches the spec's
    // "Execute selected query" + "Ctrl+Enter execution" requirements.
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => {
      const model = editor.getModel();
      const selection = editor.getSelection();
      if (!model) return;
      const selectedText = selection ? model.getValueInRange(selection) : "";
      const textToRun = selectedText.trim().length > 0 ? selectedText : model.getValue();
      onExecute(textToRun);
    });
  };

  return (
    <div className="sql-editor-panel">
      <div className="sql-editor-toolbar">
        <button
          className="run-btn"
          onClick={() => onExecute(value)}
          disabled={running}
          title="Execute (Ctrl+Enter)"
        >
          {running ? <Loader2 className="spin" size={14} /> : <Play size={14} />}
          Run
        </button>
      </div>
      <Editor
        height="100%"
        defaultLanguage="sql"
        theme="vs-dark"
        value={value}
        onChange={(v) => onChange(v ?? "")}
        onMount={handleMount}
        options={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 14,
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          wordWrap: "on",
          automaticLayout: true,
        }}
      />
    </div>
  );
}
