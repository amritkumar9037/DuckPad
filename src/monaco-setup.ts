// Wires @monaco-editor/react to the locally-bundled `monaco-editor` package
// instead of its default behavior of fetching Monaco from a CDN at runtime.
// DuckPad is offline-first and portable — it must never reach the network.
//
// Import this module ONCE, before any <Editor /> is rendered (see main.tsx).

import * as monaco from "monaco-editor";
import { loader } from "@monaco-editor/react";

import editorWorker from "monaco-editor/editor/editor.worker.js?worker";

// Monaco's core editor needs a web worker for tokenization/model sync.
// SQL has no dedicated language worker (unlike TS/JSON/CSS), so every
// language — including "sql" — falls back to the generic editor worker.
self.MonacoEnvironment = {
  getWorker() {
    return new editorWorker();
  },
};

// Point @monaco-editor/react at the monaco instance we imported locally,
// instead of letting it lazy-load from https://cdn.jsdelivr.net.
loader.config({ monaco });
