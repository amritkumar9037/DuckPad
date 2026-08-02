"""DuckPad Lite -- a portable, single-file SQL playground.

Paste tabular data (Ctrl+V), it becomes a queryable table instantly
(table1, table2, ...), and you write SQL against it right away.

Built on Python's standard library (tkinter + sqlite3) plus an optional
DuckDB backend, so PyInstaller can package it into one .exe.
"""

from __future__ import annotations
import csv
import json
import os
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

from duckpad import parser, schema, db

APP_TITLE = "DuckPad Lite"
DEFAULT_SQL = "SELECT 'hello, duckpad' AS greeting, 42 AS answer;"
HISTORY_LIMIT = 200
SAVED_QUERIES_FILE = os.path.join(os.path.expanduser("~"), ".duckpad_lite_saved_queries.json")

BG = "#1e1e1e"
PANEL_BG = "#252526"
FG = "#d4d4d4"
ACCENT = "#0e639c"
MONO_FONT = ("Consolas", 11)
UI_FONT = ("Segoe UI", 10)

SQL_KEYWORDS = {
    "SELECT", "FROM", "WHERE", "GROUP", "BY", "ORDER", "HAVING", "JOIN", "LEFT",
    "RIGHT", "INNER", "OUTER", "ON", "AS", "AND", "OR", "NOT", "NULL", "INSERT",
    "INTO", "VALUES", "UPDATE", "SET", "DELETE", "CREATE", "TABLE", "DROP",
    "ALTER", "VIEW", "WITH", "UNION", "ALL", "INTERSECT", "EXCEPT", "LIMIT",
    "OFFSET", "DISTINCT", "CASE", "WHEN", "THEN", "ELSE", "END", "IN", "IS",
    "LIKE", "BETWEEN", "EXISTS", "COUNT", "SUM", "AVG", "MIN", "MAX", "OVER",
    "PARTITION", "ASC", "DESC",
}


# ----------------------------------------------------------------- Engine picker

def choose_engine(root: tk.Tk) -> str:
    """Modal dialog shown at startup: SQLite or DuckDB."""
    result = {"engine": db.ENGINE_SQLITE}
    dlg = tk.Toplevel(root)
    dlg.title("Choose SQL engine")
    dlg.configure(bg=PANEL_BG)
    dlg.resizable(False, False)
    dlg.grab_set()

    tk.Label(
        dlg, text="Which SQL engine should this session use?",
        bg=PANEL_BG, fg=FG, font=UI_FONT,
    ).pack(padx=20, pady=(16, 8))

    choice = tk.StringVar(value=db.ENGINE_SQLITE)

    def add_option(value, label, sub):
        frame = tk.Frame(dlg, bg=PANEL_BG)
        frame.pack(fill=tk.X, padx=20, anchor="w")
        tk.Radiobutton(
            frame, text=label, variable=choice, value=value,
            bg=PANEL_BG, fg=FG, selectcolor="#111111", activebackground=PANEL_BG,
            activeforeground=FG, font=UI_FONT,
        ).pack(anchor="w")
        tk.Label(frame, text=sub, bg=PANEL_BG, fg="#9a9a9a", font=("Segoe UI", 8)).pack(
            anchor="w", padx=22
        )

    add_option(db.ENGINE_SQLITE, "SQLite", "Always available. Full SQL, widely compatible.")
    duckdb_sub = (
        "Native DATE/TIMESTAMP/BOOLEAN types, analytical SQL extensions."
        if db.HAVE_DUCKDB else
        "Not installed in this build -- run 'pip install duckdb' to enable."
    )
    add_option(db.ENGINE_DUCKDB, "DuckDB", duckdb_sub)
    if not db.HAVE_DUCKDB:
        for child in dlg.winfo_children():
            pass  # radio buttons stay visible but selecting it will show an error on Continue

    def on_continue():
        if choice.get() == db.ENGINE_DUCKDB and not db.HAVE_DUCKDB:
            messagebox.showerror(
                "DuckDB not available",
                "The 'duckdb' Python package isn't installed in this build.\n"
                "Falling back to SQLite for this session.",
            )
            result["engine"] = db.ENGINE_SQLITE
        else:
            result["engine"] = choice.get()
        dlg.destroy()

    tk.Button(
        dlg, text="Continue", command=on_continue, bg=ACCENT, fg="white",
        relief=tk.FLAT, font=UI_FONT, padx=16, pady=6,
    ).pack(pady=16)

    dlg.protocol("WM_DELETE_WINDOW", on_continue)
    root.wait_window(dlg)
    return result["engine"]


# ----------------------------------------------------------------- Import dialog

TYPE_CHOICES = [schema.INTEGER, schema.REAL, schema.BOOLEAN, schema.DATE, schema.TIMESTAMP, schema.TEXT]


class ImportOptions:
    def __init__(self):
        self.table_name = ""
        self.has_header = True
        self.delimiter = "auto"
        self.column_names: list[str] = []
        self.column_types: list[str] = []


def show_import_dialog(root, raw_text: str, suggested_name: str) -> ImportOptions | None:
    """Import dialog: table name, header/separator toggle, live preview, and
    -- per the user's request -- an editable column list so the table name
    and every column's name/datatype can be overridden before import, not
    just auto-detected silently. Used for both 'Paste as Table' and
    'Open CSV'."""
    opts = ImportOptions()
    opts.table_name = suggested_name

    dlg = tk.Toplevel(root)
    dlg.title("Import options")
    dlg.configure(bg=PANEL_BG)
    dlg.geometry("720x620")
    dlg.minsize(520, 420)
    dlg.grab_set()

    result = {"ok": False}

    def on_import():
        opts.table_name = db.safe_identifier(name_var.get(), 1) or suggested_name
        opts.column_names = [db.safe_identifier(nv.get(), i + 1) for i, (nv, _) in enumerate(column_widgets)]
        opts.column_types = [tv.get() for _, tv in column_widgets]
        result["ok"] = True
        dlg.destroy()

    def on_cancel():
        dlg.destroy()

    # Import/Cancel live in their own fixed-height frame packed FIRST (side=TOP,
    # before any expanding content), so they stay visible no matter how the
    # dialog is resized -- they were getting squeezed off-screen at the bottom
    # when the window was shrunk, since pack() clips later-packed fixed-size
    # widgets first when space runs out.
    btn_row = tk.Frame(dlg, bg=PANEL_BG)
    btn_row.pack(side=tk.TOP, fill=tk.X, padx=12, pady=10)
    tk.Button(btn_row, text="Import", command=on_import, bg=ACCENT, fg="white", relief=tk.FLAT, font=UI_FONT).pack(
        side=tk.RIGHT, padx=4
    )
    tk.Button(btn_row, text="Cancel", command=on_cancel, bg=PANEL_BG, fg=FG, relief=tk.FLAT, font=UI_FONT).pack(
        side=tk.RIGHT, padx=4
    )
    ttk.Separator(dlg, orient="horizontal").pack(side=tk.TOP, fill=tk.X)

    top = tk.Frame(dlg, bg=PANEL_BG)
    top.pack(fill=tk.X, padx=12, pady=10)

    tk.Label(top, text="Table name:", bg=PANEL_BG, fg=FG, font=UI_FONT).grid(row=0, column=0, sticky="w")
    name_var = tk.StringVar(value=suggested_name)
    tk.Entry(top, textvariable=name_var, bg="#111111", fg=FG, insertbackground="white", font=UI_FONT, width=24).grid(
        row=0, column=1, sticky="w", padx=8
    )

    tk.Label(top, text="Header row:", bg=PANEL_BG, fg=FG, font=UI_FONT).grid(row=1, column=0, sticky="w", pady=(8, 0))
    header_var = tk.StringVar(value="auto")
    header_menu = ttk.Combobox(top, textvariable=header_var, values=["auto", "yes", "no"], width=10, state="readonly")
    header_menu.grid(row=1, column=1, sticky="w", padx=8, pady=(8, 0))

    tk.Label(top, text="Separator:", bg=PANEL_BG, fg=FG, font=UI_FONT).grid(row=2, column=0, sticky="w", pady=(8, 0))
    sep_var = tk.StringVar(value="auto")
    sep_menu = ttk.Combobox(
        top, textvariable=sep_var,
        values=["auto", "Comma", "Tab", "Pipe", "Semicolon", "Space"], width=10, state="readonly",
    )
    sep_menu.grid(row=2, column=1, sticky="w", padx=8, pady=(8, 0))

    tk.Label(dlg, text="Preview:", bg=PANEL_BG, fg=FG, font=UI_FONT, anchor="w").pack(
        fill=tk.X, padx=12, pady=(10, 0)
    )
    preview_tree = ttk.Treeview(dlg, show="headings", height=6)
    preview_tree.pack(fill=tk.BOTH, expand=False, padx=12, pady=(4, 8))

    tk.Label(dlg, text="Columns (edit name / datatype before importing):", bg=PANEL_BG, fg=FG, font=UI_FONT, anchor="w").pack(
        fill=tk.X, padx=12
    )
    columns_canvas_frame = tk.Frame(dlg, bg=PANEL_BG)
    columns_canvas_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 8))
    columns_canvas = tk.Canvas(columns_canvas_frame, bg=PANEL_BG, highlightthickness=0)
    columns_scrollbar = ttk.Scrollbar(columns_canvas_frame, orient="vertical", command=columns_canvas.yview)
    columns_inner = tk.Frame(columns_canvas, bg=PANEL_BG)
    columns_inner.bind("<Configure>", lambda e: columns_canvas.configure(scrollregion=columns_canvas.bbox("all")))
    columns_canvas.create_window((0, 0), window=columns_inner, anchor="nw")
    columns_canvas.configure(yscrollcommand=columns_scrollbar.set)
    columns_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    columns_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    sep_map = {"Comma": ",", "Tab": "\t", "Pipe": "|", "Semicolon": ";", "Space": " "}
    column_widgets: list[tuple[tk.StringVar, tk.StringVar]] = []  # (name_var, type_var) per column

    def rebuild_column_editor(headers: list[str], inferred_types: list[str]):
        for child in columns_inner.winfo_children():
            child.destroy()
        column_widgets.clear()

        tk.Label(columns_inner, text="Column name", bg=PANEL_BG, fg="#9a9a9a", font=UI_FONT).grid(
            row=0, column=0, sticky="w", padx=(2, 12)
        )
        tk.Label(columns_inner, text="Datatype", bg=PANEL_BG, fg="#9a9a9a", font=UI_FONT).grid(
            row=0, column=1, sticky="w"
        )
        for i, (h, t) in enumerate(zip(headers, inferred_types)):
            name_v = tk.StringVar(value=h)
            type_v = tk.StringVar(value=t)
            tk.Entry(
                columns_inner, textvariable=name_v, bg="#111111", fg=FG,
                insertbackground="white", font=UI_FONT, width=22,
            ).grid(row=i + 1, column=0, sticky="w", padx=(2, 12), pady=2)
            ttk.Combobox(
                columns_inner, textvariable=type_v, values=TYPE_CHOICES, width=12, state="readonly",
            ).grid(row=i + 1, column=1, sticky="w", pady=2)
            column_widgets.append((name_v, type_v))

    def refresh_preview(*_):
        delim = sep_map.get(sep_var.get(), None) or parser.detect_delimiter(raw_text)
        rows = parser.split_rows(raw_text, delim)
        if not rows:
            return
        header_choice = header_var.get()
        if header_choice == "auto":
            has_header = parser.detect_header(rows)
        else:
            has_header = header_choice == "yes"

        ncols = max(len(r) for r in rows)
        if has_header:
            raw_headers, data = rows[0], rows[1:]
        else:
            raw_headers, data = [f"col_{i + 1}" for i in range(ncols)], rows

        preview_tree.delete(*preview_tree.get_children())
        cols = [f"c{i}" for i in range(ncols)]
        preview_tree["columns"] = cols
        safe_headers = []
        inferred_types = []
        for i in range(ncols):
            label = raw_headers[i] if i < len(raw_headers) else f"col_{i + 1}"
            safe_headers.append(db.safe_identifier(label, i + 1))
            preview_tree.heading(cols[i], text=label)
            preview_tree.column(cols[i], width=100, anchor="w")
            values = [r[i] if i < len(r) else "" for r in data]
            inferred_types.append(schema.infer_column_type(values))
        for row in data[:20]:
            preview_tree.insert("", tk.END, values=row)

        opts.delimiter = delim
        opts.has_header = has_header
        rebuild_column_editor(safe_headers, inferred_types)

    sep_menu.bind("<<ComboboxSelected>>", refresh_preview)
    header_menu.bind("<<ComboboxSelected>>", refresh_preview)
    refresh_preview()

    root.wait_window(dlg)
    return opts if result["ok"] else None


# ----------------------------------------------------------------- SQL tab

class SqlTab(tk.Frame):
    """One SQL editor + results grid pane, hosted inside the app's Notebook."""

    def __init__(self, parent, app: "DuckPadApp", title: str):
        super().__init__(parent, bg=BG)
        self.app = app
        self.title = title
        self._last_result: db.QueryResult | None = None
        self._result_source_table: str | None = None
        self._result_pk_col: str | None = None

        pane = tk.PanedWindow(self, orient=tk.VERTICAL, bg=BG, sashwidth=4)
        pane.pack(fill=tk.BOTH, expand=True)

        editor_frame = tk.Frame(pane, bg=BG)
        gutter_row = tk.Frame(editor_frame, bg=BG)
        gutter_row.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.linenos = tk.Text(
            gutter_row, width=4, bg="#1a1a1a", fg="#6a6a6a", bd=0,
            font=MONO_FONT, state="disabled", takefocus=0,
        )
        self.linenos.pack(side=tk.LEFT, fill=tk.Y)

        self.sql_text = tk.Text(
            gutter_row, bg="#111111", fg="#d4d4d4", insertbackground="white",
            font=MONO_FONT, undo=True, wrap="none", height=8,
        )
        self.sql_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.sql_text.insert("1.0", DEFAULT_SQL)

        for tag, color in [
            ("kw", "#569cd6"), ("str", "#ce9178"), ("comment", "#6a9955"),
        ]:
            self.sql_text.tag_configure(tag, foreground=color)

        self.sql_text.bind("<KeyRelease>", self._on_editor_changed)
        self.sql_text.bind("<Control-slash>", self._toggle_comment)
        self.sql_text.bind("<Control-Return>", lambda e: (self.app.run_current_tab(), "break")[1])
        self._on_editor_changed()

        pane.add(editor_frame, minsize=140)

        results_frame = tk.Frame(pane, bg=BG)
        tk.Label(results_frame, text="Results", bg=BG, fg=FG, font=UI_FONT, anchor="w").grid(
            row=0, column=0, columnspan=2, sticky="ew", padx=6, pady=(4, 0)
        )
        results_frame.grid_rowconfigure(1, weight=1)
        results_frame.grid_columnconfigure(0, weight=1)

        self.results_tree = ttk.Treeview(results_frame, show="headings")
        results_vsb = ttk.Scrollbar(results_frame, orient="vertical", command=self.results_tree.yview)
        results_hsb = ttk.Scrollbar(results_frame, orient="horizontal", command=self.results_tree.xview)
        self.results_tree.configure(yscrollcommand=results_vsb.set, xscrollcommand=results_hsb.set)
        self.results_tree.grid(row=1, column=0, sticky="nsew", padx=(4, 0), pady=(4, 0))
        results_vsb.grid(row=1, column=1, sticky="ns", pady=(4, 0))
        results_hsb.grid(row=2, column=0, sticky="ew", padx=(4, 0), pady=(0, 4))
        self.results_tree.bind("<Double-1>", self._on_cell_double_click)
        pane.add(results_frame, minsize=150)

    def _on_editor_changed(self, event=None):
        # Line numbers gutter
        content = self.sql_text.get("1.0", tk.END)
        n_lines = content.count("\n") or 1
        self.linenos.configure(state="normal")
        self.linenos.delete("1.0", tk.END)
        self.linenos.insert("1.0", "\n".join(str(i) for i in range(1, n_lines + 1)))
        self.linenos.configure(state="disabled")
        self._highlight_syntax()

    def _highlight_syntax(self):
        text = self.sql_text
        for tag in ("kw", "str", "comment"):
            text.tag_remove(tag, "1.0", tk.END)
        content = text.get("1.0", tk.END)
        for match_start, word in _tokenize(content):
            if word.upper() in SQL_KEYWORDS:
                start_idx = f"1.0+{match_start}c"
                end_idx = f"1.0+{match_start + len(word)}c"
                text.tag_add("kw", start_idx, end_idx)
        for m in _STRING_RE.finditer(content):
            text.tag_add("str", f"1.0+{m.start()}c", f"1.0+{m.end()}c")
        for m in _COMMENT_RE.finditer(content):
            text.tag_add("comment", f"1.0+{m.start()}c", f"1.0+{m.end()}c")

    def _toggle_comment(self, event=None):
        try:
            start_line = int(self.sql_text.index("sel.first").split(".")[0])
            end_line = int(self.sql_text.index("sel.last").split(".")[0])
        except tk.TclError:
            start_line = end_line = int(self.sql_text.index("insert").split(".")[0])

        lines_commented = []
        for ln in range(start_line, end_line + 1):
            line_text = self.sql_text.get(f"{ln}.0", f"{ln}.end")
            lines_commented.append(line_text.lstrip().startswith("--"))
        should_uncomment = all(lines_commented) and lines_commented

        for ln in range(start_line, end_line + 1):
            line_text = self.sql_text.get(f"{ln}.0", f"{ln}.end")
            if should_uncomment:
                stripped = line_text.lstrip()
                prefix_len = len(line_text) - len(stripped)
                if stripped.startswith("-- "):
                    new_text = line_text[:prefix_len] + stripped[3:]
                elif stripped.startswith("--"):
                    new_text = line_text[:prefix_len] + stripped[2:]
                else:
                    new_text = line_text
            else:
                new_text = "-- " + line_text
            self.sql_text.delete(f"{ln}.0", f"{ln}.end")
            self.sql_text.insert(f"{ln}.0", new_text)

        self._on_editor_changed()
        return "break"

    def _on_cell_double_click(self, event):
        if not self._result_source_table or not self._result_pk_col:
            return  # editing only supported for a plain "SELECT * FROM <one table>" result
        row_id = self.results_tree.identify_row(event.y)
        col_id = self.results_tree.identify_column(event.x)
        if not row_id or not col_id:
            return
        col_index = int(col_id.replace("#", "")) - 1
        columns = list(self.results_tree["columns"])
        if col_index < 0 or col_index >= len(columns):
            return
        target_column = columns[col_index]
        current_values = list(self.results_tree.item(row_id)["values"])
        pk_index = columns.index(self._result_pk_col) if self._result_pk_col in columns else 0
        pk_value = current_values[pk_index]
        old_value = current_values[col_index]

        new_value = simpledialog.askstring(
            "Edit cell", f"{target_column}:", initialvalue=str(old_value), parent=self,
        )
        if new_value is None or new_value == str(old_value):
            return

        try:
            sql_ran = self.app.database.update_cell(
                self._result_source_table, self._result_pk_col, pk_value, target_column, new_value
            )
        except Exception as e:
            messagebox.showerror("Update failed", str(e))
            return

        self.app.add_history(sql_ran)
        current_values[col_index] = new_value
        self.results_tree.item(row_id, values=current_values)
        self.app.set_status(f"Updated {self._result_source_table}.{target_column}")

    def render_results(self, result: db.QueryResult, source_table: str | None, pk_col: str | None):
        self._last_result = result
        self._result_source_table = source_table
        self._result_pk_col = pk_col
        self.results_tree.delete(*self.results_tree.get_children())
        self.results_tree["columns"] = result.columns
        for i, col in enumerate(result.columns):
            sample_values = [row[i] for row in result.rows[:200] if i < len(row)]
            longest = max([len(col)] + [len(str(v)) for v in sample_values], default=len(col))
            width_px = min(max(longest * 8 + 16, 70), 320)  # readable floor/ceiling either way
            self.results_tree.heading(col, text=col)
            self.results_tree.column(col, width=width_px, minwidth=50, anchor="w", stretch=False)
        for row in result.rows:
            self.results_tree.insert("", tk.END, values=row)


_STRING_RE = __import__("re").compile(r"'[^']*'")
_COMMENT_RE = __import__("re").compile(r"--[^\n]*")
_WORD_RE = __import__("re").compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _tokenize(text: str):
    for m in _WORD_RE.finditer(text):
        yield m.start(), m.group(0)


# ----------------------------------------------------------------- Main app

class DuckPadApp:
    def __init__(self, root: tk.Tk, engine: str):
        self.root = root
        self.root.title(f"{APP_TITLE} [{engine}]")
        self.root.geometry("1150x760")
        self.root.configure(bg=BG)

        self.database = db.Database(engine=engine)
        self.history: list[str] = []
        self.saved_queries: dict[str, str] = self._load_saved_queries()

        self._build_style()
        self._build_toolbar()
        self._build_main_panes()
        self._build_status_bar()

        self.root.bind_all("<Control-Shift-V>", self._on_paste_as_table)
        self.root.bind_all("<Control-Shift-v>", self._on_paste_as_table)  # some platforms report lowercase

        self.new_tab()
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
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL_BG, foreground=FG, padding=[10, 4])
        style.map("TNotebook.Tab", background=[("selected", ACCENT)])

    def _build_toolbar(self):
        bar = tk.Frame(self.root, bg=PANEL_BG)
        bar.pack(side=tk.TOP, fill=tk.X)

        def btn(label, cmd):
            b = tk.Button(
                bar, text=label, command=cmd, bg=PANEL_BG, fg=FG,
                activebackground=ACCENT, activeforeground="white",
                relief=tk.FLAT, padx=8, pady=4, font=UI_FONT,
            )
            b.pack(side=tk.LEFT, padx=2, pady=2)
            return b

        btn("Paste as Table (Ctrl+Shift+V)", self._on_paste_as_table)
        btn("Open CSV", self._on_open_csv)
        btn("Run (Ctrl+Enter)", self.run_current_tab)
        btn("Export CSV", self._on_export_csv)
        btn("New Tab", self.new_tab)
        btn("Save Query", self._on_save_query)
        btn("Saved Queries", self._on_show_saved_queries)
        btn("History", self._on_show_history)

    def _build_main_panes(self):
        paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=BG, sashwidth=4)
        paned.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        left = tk.Frame(paned, bg=PANEL_BG)
        tk.Label(left, text="Tables", bg=PANEL_BG, fg=FG, font=UI_FONT, anchor="w").pack(fill=tk.X, padx=6, pady=4)
        self.schema_tree = ttk.Treeview(left, show="tree")
        self.schema_tree.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.schema_tree.bind("<Button-3>", self._on_schema_right_click)
        self._schema_item_map: dict[str, tuple] = {}  # iid -> ("table", name) or ("column", table, col)
        paned.add(left, minsize=180, width=220)

        self.notebook = ttk.Notebook(paned)
        paned.add(self.notebook, minsize=500)

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

    def current_tab(self) -> SqlTab | None:
        try:
            widget_name = self.notebook.select()
            if not widget_name:
                return None
            return self.notebook.nametowidget(widget_name)
        except (tk.TclError, KeyError):
            return None

    def new_tab(self):
        tab = SqlTab(self.notebook, self, f"Query {len(self.notebook.tabs()) + 1}")
        self.notebook.add(tab, text=tab.title)
        self.notebook.select(tab)
        return tab

    def add_history(self, sql: str):
        sql = sql.strip()
        if not sql:
            return
        if self.history and self.history[-1] == sql:
            return
        self.history.append(sql)
        if len(self.history) > HISTORY_LIMIT:
            self.history.pop(0)

    def _load_saved_queries(self) -> dict[str, str]:
        if os.path.exists(SAVED_QUERIES_FILE):
            try:
                with open(SAVED_QUERIES_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _persist_saved_queries(self):
        try:
            with open(SAVED_QUERIES_FILE, "w", encoding="utf-8") as f:
                json.dump(self.saved_queries, f, indent=2)
        except OSError:
            pass  # saved-queries persistence is best-effort, never fatal

    def _import_with_options(self, text: str, opts: ImportOptions):
        rows = parser.split_rows(text, opts.delimiter)
        if not rows:
            return
        data = rows[1:] if opts.has_header else rows
        columns = list(zip(opts.column_names, opts.column_types))

        try:
            info = self.database.import_table(opts.table_name, columns, data)
        except Exception as e:
            messagebox.showerror("Import failed", str(e))
            return

        tab = self.current_tab() or self.new_tab()
        tab.sql_text.delete("1.0", tk.END)
        select_sql = f"SELECT *\nFROM {info.name};"
        tab.sql_text.insert("1.0", select_sql)
        tab._on_editor_changed()
        self.refresh_schema()
        self._run_query_in_tab(tab, select_sql)
        self.set_status(f"Imported {len(data)} row(s) into {info.name}")

    def _on_paste_as_table(self, event=None):
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            self.set_status("Clipboard is empty or not text")
            return "break"
        if not text.strip():
            self.set_status("Clipboard is empty")
            return "break"
        suggested = self.database.next_scratch_name()
        opts = show_import_dialog(self.root, text, suggested)
        if opts is not None:
            self._import_with_options(text, opts)
        return "break"

    def _on_open_csv(self):
        path = filedialog.askopenfilename(
            filetypes=[("Tabular files", "*.csv *.tsv *.txt"), ("All files", "*.*")]
        )
        if not path:
            return
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()

        suggested = db.safe_identifier(os.path.splitext(os.path.basename(path))[0], 1) or self.database.next_scratch_name()
        opts = show_import_dialog(self.root, text, suggested)
        if opts is None:
            return
        self._import_with_options(text, opts)

    def run_current_tab(self, event=None):
        tab = self.current_tab()
        if tab is None:
            return
        sql = tab.sql_text.get("1.0", tk.END)
        self._run_query_in_tab(tab, sql)

    def _run_query_in_tab(self, tab: SqlTab, sql: str):
        self.set_status("Running…")
        self.root.update_idletasks()
        start = time.perf_counter()
        try:
            result = self.database.execute_sql(sql)
        except Exception as e:
            messagebox.showerror("SQL Error", str(e))
            self.set_status(f"Error: {e}")
            return
        elapsed = (time.perf_counter() - start) * 1000.0

        source_table, pk_col = _infer_single_table_and_pk(sql, result.columns)
        tab.render_results(result, source_table, pk_col)
        self.add_history(sql)
        self.refresh_schema()
        self.set_status(f"Ready   {len(result.rows)} row(s)   {elapsed:.1f} ms")

    def _on_export_csv(self):
        tab = self.current_tab()
        if not tab or not tab._last_result or not tab._last_result.columns:
            messagebox.showinfo("Export CSV", "Run a query first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(tab._last_result.columns)
            writer.writerows(tab._last_result.rows)
        self.set_status(f"Exported to {path}")

    def _on_save_query(self):
        tab = self.current_tab()
        if not tab:
            return
        sql = tab.sql_text.get("1.0", tk.END).strip()
        if not sql:
            return
        name = simpledialog.askstring("Save query", "Name for this query:", parent=self.root)
        if not name:
            return
        self.saved_queries[name] = sql
        self._persist_saved_queries()
        self.set_status(f"Saved query '{name}'")

    def _on_show_saved_queries(self):
        self._show_picker_dialog(
            "Saved queries", list(self.saved_queries.items()),
            on_pick=lambda sql: self._load_sql_into_tab(sql),
        )

    def _on_show_history(self):
        items = [(f"{i + 1}", sql) for i, sql in enumerate(reversed(self.history))]
        self._show_picker_dialog("Query history", items, on_pick=lambda sql: self._load_sql_into_tab(sql))

    def _load_sql_into_tab(self, sql: str):
        tab = self.current_tab() or self.new_tab()
        tab.sql_text.delete("1.0", tk.END)
        tab.sql_text.insert("1.0", sql)
        tab._on_editor_changed()

    def _show_picker_dialog(self, title: str, items: list[tuple[str, str]], on_pick):
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.configure(bg=PANEL_BG)
        dlg.geometry("500x400")

        listbox = tk.Listbox(dlg, bg="#111111", fg=FG, font=MONO_FONT, selectbackground=ACCENT)
        listbox.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        for name, sql in items:
            preview = sql.replace("\n", " ")[:80]
            listbox.insert(tk.END, f"{name}: {preview}")

        def on_select(event=None):
            sel = listbox.curselection()
            if not sel:
                return
            _, sql = items[sel[0]]
            on_pick(sql)
            dlg.destroy()

        listbox.bind("<Double-1>", on_select)
        tk.Button(
            dlg, text="Load", command=on_select, bg=ACCENT, fg="white", relief=tk.FLAT, font=UI_FONT
        ).pack(pady=(0, 8))

    def refresh_schema(self):
        self.schema_tree.delete(*self.schema_tree.get_children())
        self._schema_item_map = {}
        for table in self.database.get_schema():
            node = self.schema_tree.insert("", tk.END, text=table.name, open=True)
            self._schema_item_map[node] = ("table", table.name)
            for col in table.columns:
                col_iid = self.schema_tree.insert(node, tk.END, text=f"{col.name}   {col.data_type}")
                self._schema_item_map[col_iid] = ("column", table.name, col.name)

    def _on_schema_right_click(self, event):
        iid = self.schema_tree.identify_row(event.y)
        if not iid:
            return
        self.schema_tree.selection_set(iid)
        entry = self._schema_item_map.get(iid)
        if entry is None:
            return

        menu = tk.Menu(self.root, tearoff=0, bg=PANEL_BG, fg=FG, activebackground=ACCENT, activeforeground="white")
        if entry[0] == "table":
            table_name = entry[1]
            menu.add_command(label="View Data", command=lambda: self._table_view_data(table_name))
            menu.add_command(label="Rename Table...", command=lambda: self._table_rename(table_name))
            menu.add_command(label="Duplicate Table", command=lambda: self._table_duplicate(table_name))
            menu.add_command(label="Export CSV...", command=lambda: self._table_export_csv(table_name))
            menu.add_separator()
            menu.add_command(label="Delete Table", command=lambda: self._table_delete(table_name))
        else:
            _, table_name, col_name = entry
            menu.add_command(label="Rename Column...", command=lambda: self._column_rename(table_name, col_name))
            menu.add_command(label="Change Datatype...", command=lambda: self._column_change_type(table_name, col_name))
            menu.add_separator()
            menu.add_command(label="Delete Column", command=lambda: self._column_delete(table_name, col_name))

        menu.tk_popup(event.x_root, event.y_root)

    def _table_view_data(self, table_name: str):
        tab = self.current_tab() or self.new_tab()
        sql = f"SELECT * FROM {table_name};"
        tab.sql_text.delete("1.0", tk.END)
        tab.sql_text.insert("1.0", sql)
        tab._on_editor_changed()
        self._run_query_in_tab(tab, sql)

    def _table_rename(self, table_name: str):
        new_name = simpledialog.askstring("Rename table", "New name:", initialvalue=table_name, parent=self.root)
        if not new_name or new_name == table_name:
            return
        try:
            actual = self.database.rename_table(table_name, new_name)
        except Exception as e:
            messagebox.showerror("Rename failed", str(e))
            return
        self.refresh_schema()
        self.set_status(f"Renamed {table_name} -> {actual}")

    def _table_duplicate(self, table_name: str):
        suggested = f"{table_name}_copy"
        new_name = simpledialog.askstring("Duplicate table", "Name for the copy:", initialvalue=suggested, parent=self.root)
        if not new_name:
            return
        try:
            actual = self.database.duplicate_table(table_name, new_name)
        except Exception as e:
            messagebox.showerror("Duplicate failed", str(e))
            return
        self.refresh_schema()
        self.set_status(f"Duplicated {table_name} -> {actual}")

    def _table_delete(self, table_name: str):
        if not messagebox.askyesno("Delete table", f"Delete table '{table_name}'? This cannot be undone."):
            return
        try:
            self.database.drop_table(table_name)
        except Exception as e:
            messagebox.showerror("Delete failed", str(e))
            return
        self.refresh_schema()
        self.set_status(f"Deleted {table_name}")

    def _table_export_csv(self, table_name: str):
        try:
            result = self.database.execute_sql(f"SELECT * FROM {table_name};")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(result.columns)
            writer.writerows(result.rows)
        self.set_status(f"Exported {table_name} to {path}")

    def _column_rename(self, table_name: str, col_name: str):
        new_name = simpledialog.askstring("Rename column", "New name:", initialvalue=col_name, parent=self.root)
        if not new_name or new_name == col_name:
            return
        try:
            actual = self.database.rename_column(table_name, col_name, new_name)
        except Exception as e:
            messagebox.showerror("Rename failed", str(e))
            return
        self.refresh_schema()
        self.set_status(f"Renamed {table_name}.{col_name} -> {actual}")

    def _column_change_type(self, table_name: str, col_name: str):
        dlg = tk.Toplevel(self.root)
        dlg.title("Change datatype")
        dlg.configure(bg=PANEL_BG)
        dlg.grab_set()
        tk.Label(dlg, text=f"New datatype for {table_name}.{col_name}:", bg=PANEL_BG, fg=FG, font=UI_FONT).pack(
            padx=16, pady=(16, 6)
        )
        type_var = tk.StringVar(value=schema.TEXT)
        combo = ttk.Combobox(dlg, textvariable=type_var, values=TYPE_CHOICES, state="readonly", width=14)
        combo.pack(padx=16, pady=6)

        def on_confirm():
            try:
                self.database.change_column_type(table_name, col_name, type_var.get())
            except Exception as e:
                messagebox.showerror("Change datatype failed", str(e))
                dlg.destroy()
                return
            self.refresh_schema()
            self.set_status(f"Changed {table_name}.{col_name} to {type_var.get()}")
            dlg.destroy()

        btn_row = tk.Frame(dlg, bg=PANEL_BG)
        btn_row.pack(pady=(6, 16))
        tk.Button(btn_row, text="Cancel", command=dlg.destroy, bg=PANEL_BG, fg=FG, relief=tk.FLAT, font=UI_FONT).pack(
            side=tk.RIGHT, padx=4
        )
        tk.Button(btn_row, text="Change", command=on_confirm, bg=ACCENT, fg="white", relief=tk.FLAT, font=UI_FONT).pack(
            side=tk.RIGHT, padx=4
        )

    def _column_delete(self, table_name: str, col_name: str):
        if not messagebox.askyesno("Delete column", f"Delete column '{col_name}' from '{table_name}'? This cannot be undone."):
            return
        try:
            self.database.drop_column(table_name, col_name)
        except Exception as e:
            messagebox.showerror("Delete failed", str(e))
            return
        self.refresh_schema()
        self.set_status(f"Deleted column {col_name} from {table_name}")


def _infer_single_table_and_pk(sql: str, result_columns: list[str]) -> tuple[str | None, str | None]:
    """Best-effort detection of 'this result came straight from one table,
    editable via its first column as a pseudo-key' -- powers double-click
    cell editing. Deliberately conservative: only a plain single-table
    SELECT (no JOIN, no aggregation) is treated as editable."""
    import re

    stripped = sql.strip().rstrip(";")
    m = re.match(r"(?is)^select\s+\*\s+from\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:where\s+.*)?$", stripped)
    if not m:
        return None, None
    table = m.group(1)
    if not result_columns:
        return None, None
    return table, result_columns[0]


def main():
    root = tk.Tk()
    root.withdraw()
    engine = choose_engine(root)
    root.deiconify()
    DuckPadApp(root, engine)
    root.mainloop()


if __name__ == "__main__":
    main()
