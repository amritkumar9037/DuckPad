"""DuckPad Lite -- a portable, single-file SQL playground.

Paste tabular data (Ctrl+V), it becomes a queryable table instantly
(table1, table2, ...), and you write SQL against it right away.

Built on Python's standard library only (tkinter + sqlite3), so PyInstaller
can package it into one .exe with no external runtime requirements.
"""

from __future__ import annotations
import sqlite3
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from duckpad import parser, schema, db

APP_TITLE = "DuckPad Lite"
DEFAULT_SQL = "SELECT 'hello, duckpad' AS greeting, 42 AS answer;"

BG = "#1e1e1e"
PANEL_BG = "#252526"
FG = "#d4d4d4"
ACCENT = "#0e639c"
MONO_FONT = ("Consolas", 11)
UI_FONT = ("Segoe UI", 10)


class DuckPadApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1100x720")
        self.root.configure(bg=BG)

        self.database = db.Database()
        self._build_style()
        self._build_toolbar()
        self._build_main_panes()
        self._build_status_bar()

        self.root.bind_all("<Control-v>", self._on_paste)
        self.root.bind_all("<Control-Return>", self._on_run)

        self.refresh_schema()
        self.set_status("Ready")

    # ---------------------------------------------------------------- UI setup

    def _build_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Treeview", background=PANEL_BG, fieldbackground=PANEL_BG, foreground=FG, borderwidth=0)
        style.configure("Treeview.Heading", background="#333333", foreground=FG, relief="flat")
        style.map("Treeview", background=[("selected", ACCENT)])

    def _build_toolbar(self):
        bar = tk.Frame(self.root, bg=PANEL_BG)
        bar.pack(side=tk.TOP, fill=tk.X)

        def btn(label, cmd):
            b = tk.Button(
                bar, text=label, command=cmd, bg=PANEL_BG, fg=FG,
                activebackground=ACCENT, activeforeground="white",
                relief=tk.FLAT, padx=10, pady=4, font=UI_FONT,
            )
            b.pack(side=tk.LEFT, padx=2, pady=2)
            return b

        btn("Paste (Ctrl+V)", self._on_paste)
        btn("Open CSV", self._on_open_csv)
        btn("Run (Ctrl+Enter)", self._on_run)
        btn("Export CSV", self._on_export_csv)

    def _build_main_panes(self):
        paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=BG, sashwidth=4)
        paned.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Left: schema explorer
        left = tk.Frame(paned, bg=PANEL_BG)
        tk.Label(left, text="Tables", bg=PANEL_BG, fg=FG, font=UI_FONT, anchor="w").pack(fill=tk.X, padx=6, pady=4)
        self.schema_tree = ttk.Treeview(left, show="tree")
        self.schema_tree.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        paned.add(left, minsize=180, width=220)

        # Right: SQL editor (top) + results (bottom), stacked
        right = tk.PanedWindow(paned, orient=tk.VERTICAL, bg=BG, sashwidth=4)
        paned.add(right, minsize=400)

        editor_frame = tk.Frame(right, bg=BG)
        tk.Label(editor_frame, text="SQL Editor", bg=BG, fg=FG, font=UI_FONT, anchor="w").pack(fill=tk.X, padx=6, pady=(4, 0))
        self.sql_text = tk.Text(
            editor_frame, bg="#111111", fg="#d4d4d4", insertbackground="white",
            font=MONO_FONT, undo=True, wrap="none", height=8,
        )
        self.sql_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.sql_text.insert("1.0", DEFAULT_SQL)
        right.add(editor_frame, minsize=120)

        results_frame = tk.Frame(right, bg=BG)
        tk.Label(results_frame, text="Results", bg=BG, fg=FG, font=UI_FONT, anchor="w").pack(fill=tk.X, padx=6, pady=(4, 0))
        self.results_tree = ttk.Treeview(results_frame, show="headings")
        vsb = ttk.Scrollbar(results_frame, orient="vertical", command=self.results_tree.yview)
        self.results_tree.configure(yscrollcommand=vsb.set)
        self.results_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 0), pady=4)
        vsb.pack(side=tk.RIGHT, fill=tk.Y, pady=4)
        right.add(results_frame, minsize=150)

    def _build_status_bar(self):
        self.status_var = tk.StringVar(value="Ready")
        bar = tk.Frame(self.root, bg=PANEL_BG)
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Label(bar, textvariable=self.status_var, bg=PANEL_BG, fg=FG, font=UI_FONT, anchor="w").pack(
            side=tk.LEFT, padx=8, pady=3
        )

    # ------------------------------------------------------------- behaviour

    def set_status(self, text: str):
        self.status_var.set(text)

    def _import_text(self, text: str, table_name: str | None = None):
        if not text.strip():
            return
        delim = parser.detect_delimiter(text)
        rows = parser.split_rows(text, delim)
        if not rows:
            return
        has_header = parser.detect_header(rows)
        ncols = max(len(r) for r in rows)

        if has_header:
            header, data = rows[0], rows[1:]
        else:
            header, data = [f"col_{i + 1}" for i in range(ncols)], rows

        columns = []
        for i in range(ncols):
            col_name = db.safe_identifier(header[i] if i < len(header) else "", i + 1)
            values = [r[i] if i < len(r) else "" for r in data]
            inferred = schema.infer_column_type(values)
            columns.append((col_name, inferred))

        try:
            info = self.database.import_table(table_name, columns, data)
        except sqlite3.Error as e:
            messagebox.showerror("Import failed", str(e))
            return

        self.sql_text.delete("1.0", tk.END)
        self.sql_text.insert("1.0", f"SELECT *\nFROM {info.name};")
        self.refresh_schema()
        self._run_query(f"SELECT * FROM {info.name};")
        self.set_status(f"Imported {len(data)} row(s) into {info.name}")

    def _on_paste(self, event=None):
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            self.set_status("Clipboard is empty or not text")
            return "break"
        self._import_text(text)
        return "break"  # prevent tkinter's default paste-into-focused-widget behavior

    def _on_open_csv(self):
        path = filedialog.askopenfilename(
            filetypes=[("Tabular files", "*.csv *.tsv *.txt"), ("All files", "*.*")]
        )
        if not path:
            return
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        self._import_text(text)

    def _on_run(self, event=None):
        sql = self.sql_text.get("1.0", tk.END)
        self._run_query(sql)
        return "break"

    def _run_query(self, sql: str):
        self.set_status("Running…")
        self.root.update_idletasks()
        start = time.perf_counter()
        try:
            result = self.database.execute_sql(sql)
        except sqlite3.Error as e:
            messagebox.showerror("SQL Error", str(e))
            self.set_status(f"Error: {e}")
            return
        elapsed = (time.perf_counter() - start) * 1000.0

        self._render_results(result)
        self.refresh_schema()
        self.set_status(f"Ready   {len(result.rows)} row(s)   {elapsed:.1f} ms")

    def _render_results(self, result: db.QueryResult):
        self.results_tree.delete(*self.results_tree.get_children())
        self.results_tree["columns"] = result.columns
        for col in result.columns:
            self.results_tree.heading(col, text=col)
            self.results_tree.column(col, width=120, anchor="w")
        for row in result.rows:
            self.results_tree.insert("", tk.END, values=row)
        self._last_result = result

    def _on_export_csv(self):
        if not getattr(self, "_last_result", None) or not self._last_result.columns:
            messagebox.showinfo("Export CSV", "Run a query first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        import csv

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(self._last_result.columns)
            writer.writerows(self._last_result.rows)
        self.set_status(f"Exported to {path}")

    def refresh_schema(self):
        self.schema_tree.delete(*self.schema_tree.get_children())
        for table in self.database.get_schema():
            node = self.schema_tree.insert("", tk.END, text=table.name, open=True)
            for col in table.columns:
                self.schema_tree.insert(node, tk.END, text=f"{col.name}   {col.data_type}")


def main():
    root = tk.Tk()
    DuckPadApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
