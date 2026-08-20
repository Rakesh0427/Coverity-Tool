#!/usr/bin/env python3
"""
Coverity Triage Pro - Modern Desktop GUI
Workflow: Setup -> Analysis -> Results
"""
import csv, json, os, sys, threading, queue, re, time

# --- Tcl/Tk path fix for frozen (PyInstaller) and regular installs ---
# Fixes "can't find package Tk" / Tcl errors when running as exe or when
# Python's tcl is in a non-standard location. Works on Windows, Linux, macOS.
import sys as _sys
if getattr(_sys, 'frozen', False):
    # Running as PyInstaller bundle: Tcl/Tk is in _MEIPASS/tcl
    _meipass = getattr(_sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    for _tcl_candidate in [
        os.path.join(_meipass, "tcl", "tcl8.6"),
        os.path.join(_meipass, "_internal", "tcl", "tcl8.6"),
        os.path.join(_meipass, "tcl8.6"),
        os.path.join(os.path.dirname(_sys.executable), "tcl", "tcl8.6"),
    ]:
        if os.path.isdir(_tcl_candidate):
            os.environ["TCL_LIBRARY"] = _tcl_candidate
            break
    for _tk_candidate in [
        os.path.join(_meipass, "tcl", "tk8.6"),
        os.path.join(_meipass, "_internal", "tcl", "tk8.6"),
        os.path.join(_meipass, "tk8.6"),
        os.path.join(os.path.dirname(_sys.executable), "tcl", "tk8.6"),
    ]:
        if os.path.isdir(_tk_candidate):
            os.environ["TK_LIBRARY"] = _tk_candidate
            break
elif os.name == 'nt':
    # Regular Windows Python: try sysconfig path, but don't fail if not found
    try:
        import sysconfig as _sc
        _py_data = _sc.get_path("data")
        _tcl_lib = os.path.join(_py_data, "tcl", "tcl8.6")
        if os.path.isdir(_tcl_lib):
            os.environ.setdefault("TCL_LIBRARY", _tcl_lib)
            os.environ.setdefault("TK_LIBRARY", os.path.join(_py_data, "tcl", "tk8.6"))
    except Exception:
        pass
# --- end Tcl fix ---

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from html_report_parser import parse_index_only, parse_detail_page, parse_coverity_excel, write_pull_excel
from heuristic_analyzer import analyze_defect
from code_extractor import extract_enclosing_function, find_function_line_by_name
from context_builder import build_defect_context, warm_workspace_index
from coverity_soap_client import CoveritySOAPClient, zeep_available, CLASSIFICATION_MAP
import coverity_push as cpush
import cov_cli

from checker_categories import (
    category_for_checker,
    group_results_by_category,
)


# -- Colour palette (light professional theme) ------------------------------
C_BG        = "#F0F2F5"
C_PANEL     = "#FFFFFF"
C_CARD      = "#F8F9FB"
C_ACCENT    = "#2563EB"
C_ACCENT2   = "#1D4ED8"
C_TEXT      = "#1E293B"
C_SUBTEXT   = "#64748B"
C_BUG       = "#DC2626"
C_FP        = "#16A34A"
C_INTENT    = "#D97706"
C_REVIEW    = "#0891B2"
C_ACCEPTED  = "#059669"
C_HIGH      = "#DC2626"
C_MED       = "#D97706"
C_LOW       = "#16A34A"
C_BORDER    = "#CBD5E1"

# Checkers whose analysis is function-scoped and therefore still reliable when
# the report line is 'Various' (unknown). For these we analyse the whole
# function and cap the confidence (the comment is annotated with the 'Various'
# caveat). Memory-safety checkers are deliberately NOT listed so that without a
# concrete line they still route to manual review rather than guessing the wrong
# access.
_LINE_AGNOSTIC_CHECKERS = frozenset({
    'CHECKED_RETURN', 'CHECKED_QRS', 'UNUSED_VALUE', 'DEADCODE', 'MISSING_BREAK',
    'NO_BREAK', 'CONSTANT_EXPRESSION_RESULT', 'IDENTICAL_BRANCHES', 'NEGATIVE_RETURNS',
    'SIZEOF_MISMATCH', 'ARRAY_VS_SINGLETON', 'STRING_NULL', 'SHIFT_OVERFLOW',
    'UNREACHABLE', 'MISSING_LOCK', 'INTEGER_OVERFLOW',
})
C_HDR_BG    = "#1E3A5F"
C_HDR_TEXT  = "#F1F5F9"

CLASS_COLOR = {
    "Bug":            C_BUG,
    "False positive": C_FP,
    "Intentional":    C_INTENT,
    "Needs review":   C_REVIEW,
    "Accepted":       C_ACCEPTED,
}

SEV_COLOR = {"High": C_HIGH, "Medium": C_MED, "Low": C_LOW}

APP_NAME    = "Coverity Findings Analyzer"
APP_VERSION = "1.4"
ICON_CHAR   = "\U0001f50d"


# -- Helpers ------------------------------------------------------------------
def hex2rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _defect_text(defect, mode="summary"):
    """Render a defect dict as a clipboard-ready text block.

    mode: 'summary' | 'comment' | 'fix' | 'meta' | 'full'
    """
    d = defect or {}
    empty = ""

    def _g(key, default=""):
        v = d.get(key, default)
        return default if v is None else v

    line_display = "Various" if d.get("line_is_various") else _g("line")
    try:
        conf_str = f"{int(float(d.get('confidence', 0.0)) * 100)}%"
    except Exception:
        conf_str = str(_g("confidence", ""))

    classification = d.get("classification", "Needs review")
    if d.get("accepted"):
        classification = "Accepted"

    if mode == "comment":
        return str(_g("comment")).strip()
    if mode == "fix":
        return str(_g("fix")).strip()
    if mode == "meta":
        return "\n".join([
            f"ID:             {_g('cid')}",
            f"Checker:        {_g('checker')}",
            f"File:           {_g('file')}",
            f"Line:           {line_display}",
            f"Function:       {_g('function')}",
            f"Severity:       {_g('severity')}",
            f"Classification: {classification}",
            f"Confidence:     {conf_str}",
        ]).strip()

    parts = [
        f"ID: {_g('cid')}  |  Checker: {_g('checker')}  |  Classification: {classification}",
        f"File: {_g('file')}  :  line {line_display}",
        f"Function: {_g('function')}  |  Severity: {_g('severity')}  |  Confidence: {conf_str}",
    ]
    cm = _g("comment")
    if cm:
        parts.append(f"Comment: {cm}")
    if mode == "full":
        fix = _g("fix")
        if fix:
            parts.append(f"Proposed Fix:\n{fix}")
        src = _g("source_code", "")
        if src:
            parts.append("Source:\n" + str(src).rstrip("\n"))
        return "\n".join(parts).strip()


def _iid_safe(text):
    """Return a Treeview-safe iid string derived from ``text``."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(text)) or "item"


def _copy_selected_text(widget, app, label="selected text", event=None):
    """Copy the currently selected text from a Tkinter Text widget to the clipboard.

    Works even on ``state="disabled"`` widgets (where the built-in ``<<Copy>>``
    virtual event is suppressed) so the user can copy any highlighted text with
    the standard Ctrl+C shortcut.
    """
    try:
        sel = widget.get("sel.first", "sel.last")
    except tk.TclError:
        sel = ""
    if sel:
        app.copy_to_clipboard(sel, label)
    return "break"


def _select_all_text(event):
    """Select every character in a Text widget (works even when disabled).

    Disabled Text widgets ignore ordinary keyboard input, so an explicit
    handler is needed to let Ctrl+A select-all before Ctrl+C copies.
    """
    try:
        event.widget.tag_add("sel", "1.0", "end")
    except tk.TclError:
        pass
    return "break"


# -- Main application ---------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME}  v{APP_VERSION}")
        self.geometry("1180x740")
        self.minsize(900, 600)
        self.configure(bg=C_BG)
        self._q = queue.Queue()
        self._defects  = []
        self._results  = []
        self._stop_evt = threading.Event()
        self._setup_styles()
        self._build_header()
        self._container = tk.Frame(self, bg=C_BG)
        self._container.pack(fill="both", expand=True)
        self._frames = {}
        for Cls in (SetupPage, AnalysisPage, ResultsPage):
            f = Cls(self._container, self)
            self._frames[Cls] = f
            f.place(relwidth=1, relheight=1)
        self.show(SetupPage)
        self.after(100, self._poll_queue)

    def _setup_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".",
            background=C_BG, foreground=C_TEXT,
            fieldbackground=C_PANEL, borderwidth=0, relief="flat")
        s.configure("TFrame", background=C_BG)
        s.configure("Panel.TFrame", background=C_PANEL)
        s.configure("Card.TFrame", background=C_CARD)
        s.configure("TLabel", background=C_BG, foreground=C_TEXT, font=("Segoe UI", 10))
        s.configure("Title.TLabel", font=("Segoe UI", 22, "bold"), foreground=C_ACCENT)
        s.configure("Sub.TLabel", font=("Segoe UI", 10), foreground=C_SUBTEXT)
        s.configure("Head.TLabel", font=("Segoe UI", 12, "bold"), foreground=C_TEXT)
        s.configure("Accent.TButton",
            background=C_ACCENT, foreground="#FFFFFF",
            font=("Segoe UI", 11, "bold"), padding=(20, 8), relief="flat")
        s.map("Accent.TButton",
            background=[("active", C_ACCENT2), ("pressed", "#1E40AF")])
        s.configure("Flat.TButton",
            background=C_CARD, foreground=C_TEXT,
            font=("Segoe UI", 10), padding=(12, 6), relief="flat")
        s.map("Flat.TButton",
            background=[("active", C_BORDER)])
        s.configure("TEntry",
            fieldbackground="#FFFFFF", foreground=C_TEXT,
            insertcolor=C_TEXT, font=("Segoe UI", 10), padding=6)
        s.configure("TCombobox",
            fieldbackground="#FFFFFF", foreground=C_TEXT, font=("Segoe UI", 10))
        s.configure("Horizontal.TProgressbar",
            troughcolor=C_BORDER, background=C_ACCENT,
            thickness=10, relief="flat")
        s.configure("Treeview",
            background="#FFFFFF", foreground=C_TEXT,
            fieldbackground="#FFFFFF", rowheight=27,
            font=("Segoe UI", 9))
        s.configure("Treeview.Heading",
            background=C_HDR_BG, foreground=C_HDR_TEXT,
            font=("Segoe UI", 9, "bold"), relief="flat")
        s.map("Treeview",
            background=[("selected", C_ACCENT)],
            foreground=[("selected", "#FFFFFF")])

    def _build_header(self):
        hdr = tk.Frame(self, bg=C_HDR_BG, height=54)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text=ICON_CHAR, font=("Segoe UI", 24), bg=C_HDR_BG,
                 fg="#93C5FD").pack(side="left", padx=(18, 6), pady=6)
        tk.Label(hdr, text=APP_NAME, font=("Segoe UI", 15, "bold"),
                 bg=C_HDR_BG, fg=C_HDR_TEXT).pack(side="left", pady=10)
        tk.Label(hdr, text=f"v{APP_VERSION}", font=("Segoe UI", 9),
                 bg=C_HDR_BG, fg="#94A3B8").pack(side="left", padx=4, pady=14)
        self._breadcrumb = tk.Label(hdr, text="Setup", font=("Segoe UI", 10),
                                    bg=C_HDR_BG, fg="#93C5FD")
        self._breadcrumb.pack(side="right", padx=20)
        tk.Button(hdr, text="⬆  Push to Coverity",
                  command=lambda: PushDialog(self, self),
                  bg="#1D4ED8", fg="#FFFFFF", relief="flat",
                  font=("Segoe UI", 9, "bold"), padx=10, pady=5,
                  cursor="hand2", activebackground="#1E40AF"
                  ).pack(side="right", padx=(0, 6), pady=10)

    def _notify(self, message, kind="info"):
        """Show a transient toast-style notification in the top-right corner.

        kind: 'info' | 'success' | 'warn' | 'error'
        """
        colors = {"info": C_ACCENT, "success": C_FP,
                  "warn": C_INTENT, "error": C_BUG}
        bg = colors.get(kind, C_ACCENT)
        lbl = tk.Label(self, text=message, bg=bg, fg="#FFFFFF",
                       font=("Segoe UI", 10, "bold"), padx=14, pady=8,
                       relief="flat", bd=0)
        lbl.place(relx=1.0, x=-16, y=64, anchor="ne")
        lbl.lift()

        def _dismiss(widget=lbl):
            try:
                widget.destroy()
            except tk.TclError:
                pass
        self.after(2800, _dismiss)

    def copy_to_clipboard(self, text, what="Data"):
        """Put `text` on the system clipboard and confirm with a toast."""
        ref = getattr(self, "_notify_count", 0) + 1
        self._notify_count = ref
        self.clipboard_clear()
        self.clipboard_append(str(text or ""))
        try:
            self.update()          # some platforms need a pump to keep clipboard
        except Exception:
            pass
        self._notify(f"\u2713 Copied {what} to clipboard", "success")

    def show(self, cls, **kw):
        f = self._frames[cls]
        f.on_show(**kw)
        f.lift()
        names = {SetupPage: "Setup", AnalysisPage: "Analysing...", ResultsPage: "Results"}
        self._breadcrumb.configure(text=names.get(cls, ""))

    def _poll_queue(self):
        for _ in range(50):
            if self._q.empty():
                break
            msg = self._q.get_nowait()
            self._frames[AnalysisPage].handle_msg(msg)
        self.after(30, self._poll_queue)


class Page(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, style="TFrame")
        self.app = app
    def on_show(self, **kw): pass


# -- Setup Page (with optional Source Root) -----------------------------------
class SetupPage(Page):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._input_var   = tk.StringVar()
        self._src_root_var = tk.StringVar()
        self._output_var = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Documents"))
        self._lang_var   = tk.StringVar(value="cpp")
        self._build()

    def _build(self):
        outer = ttk.Frame(self, style="TFrame")
        outer.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(outer, text=ICON_CHAR, font=("Segoe UI", 56),
                 bg=C_BG, fg=C_ACCENT).pack(pady=(0, 4))
        tk.Label(outer, text=APP_NAME,
                 font=("Segoe UI", 26, "bold"), bg=C_BG, fg=C_TEXT).pack()
        tk.Label(outer, text="Automated defect triage for Coverity reports",
                 font=("Segoe UI", 11), bg=C_BG, fg=C_SUBTEXT).pack(pady=(2, 24))

        card = tk.Frame(outer, bg=C_PANEL, bd=0)
        card.pack(ipadx=28, ipady=20)

        def input_row(parent, label, var, browse_cmd, row_idx, extra_text=None,
                      extra_cmd=None):
            tk.Label(parent, text=label, font=("Segoe UI", 10, "bold"),
                     bg=C_PANEL, fg=C_SUBTEXT, anchor="w").grid(
                row=row_idx, column=0, columnspan=2, sticky="w", pady=(10, 2), padx=4)
            e = tk.Entry(parent, textvariable=var, width=48,
                         bg=C_CARD, fg=C_TEXT, insertbackground=C_TEXT,
                         relief="flat", font=("Segoe UI", 10))
            e.grid(row=row_idx+1, column=0, padx=(4, 4), ipady=7, sticky="ew")
            btn = tk.Button(parent, text="Browse...", command=browse_cmd,
                            bg=C_CARD, fg=C_ACCENT, relief="flat",
                            font=("Segoe UI", 9, "bold"), cursor="hand2",
                            activebackground=C_BORDER, activeforeground=C_TEXT)
            btn.grid(row=row_idx+1, column=1, padx=(0, 4), ipady=6, sticky="ew")
            if extra_text and extra_cmd:
                ex = tk.Button(parent, text=extra_text, command=extra_cmd,
                               bg=C_ACCENT, fg="#FFFFFF", relief="flat",
                               font=("Segoe UI", 9, "bold"), cursor="hand2",
                               activebackground=C_ACCENT2, activeforeground="#FFFFFF")
                ex.grid(row=row_idx+1, column=2, padx=(0, 4), ipady=6, sticky="ew")

        input_row(card, "Coverity Report (HTML folder or Excel file)",
                  self._input_var, self._browse_input, 0,
                  extra_text="⬇ Pull from Coverity", extra_cmd=self._open_pull_dialog)
        input_row(card, "Source Code Root (required)",
                  self._src_root_var, self._browse_src_root, 2)
        input_row(card, "Output Folder",
                  self._output_var, self._browse_output, 4)

        tk.Label(card, text="Code Language", font=("Segoe UI", 10, "bold"),
                 bg=C_PANEL, fg=C_SUBTEXT, anchor="w").grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(10, 2), padx=4)
        lang_f = tk.Frame(card, bg=C_PANEL)
        lang_f.grid(row=7, column=0, columnspan=2, sticky="w", padx=4)
        for val, txt in [("cpp", "C++ (.cpp / .c)"), ("c", "C only (.c)")]:
            tk.Radiobutton(lang_f, text=txt, variable=self._lang_var, value=val,
                           bg=C_PANEL, fg=C_TEXT, selectcolor=C_CARD,
                           activebackground=C_PANEL, activeforeground=C_TEXT,
                           font=("Segoe UI", 10)).pack(side="left", padx=(0, 18))

        card.columnconfigure(0, weight=1)

        # Step 0 — the stream may be empty. Upload already-analysed results
        # (an intermediate directory) before there is anything to pull.
        seed_f = tk.Frame(outer, bg=C_BG)
        seed_f.pack(pady=(16, 0))
        tk.Label(seed_f,
                 text="Defects not in Coverity Connect yet?",
                 font=("Segoe UI", 9), bg=C_BG, fg=C_SUBTEXT
                 ).pack(side="left", padx=(0, 8))
        tk.Button(seed_f, text="\u2b06  Commit Defects to Coverity",
                  command=self._open_commit_dialog,
                  bg=C_CARD, fg=C_ACCENT, relief="flat",
                  font=("Segoe UI", 9, "bold"), padx=12, pady=5,
                  cursor="hand2", activebackground=C_BORDER).pack(side="left")

        start = tk.Button(outer, text="  ▶  Start Disposition",
                          command=self._start,
                          bg=C_ACCENT, fg="#FFFFFF",
                          font=("Segoe UI", 13, "bold"),
                          relief="flat", cursor="hand2",
                          activebackground=C_ACCENT2, activeforeground="#FFFFFF",
                          padx=28, pady=12)
        start.pack(pady=(22, 0))

    def _browse_input(self):
        """Browse for either HTML folder or Excel file."""
        f = filedialog.askopenfilename(
            title="Select Coverity Report (HTML or Excel)",
            filetypes=[
                ("All supported", "*.html *.xlsx *.xls"),
                ("HTML files", "*.html"),
                ("Excel files", "*.xlsx *.xls"),
                ("All files", "*.*")
            ])
        if f:
            self._input_var.set(f)
            return
        d = filedialog.askdirectory(title="Select Coverity HTML Report Folder")
        if d:
            self._input_var.set(d)

    def _browse_src_root(self):
        d = filedialog.askdirectory(title="Select Source Code Root Folder")
        if d:
            self._src_root_var.set(d)

    def _browse_output(self):
        d = filedialog.askdirectory(title="Select Output Folder")
        if d:
            self._output_var.set(d)

    def _open_commit_dialog(self):
        """Upload existing analysis results (an idir) via cov-commit-defects."""
        CommitDefectsDialog(self, self.app)

    def _open_pull_dialog(self):
        dlg = PullDialog(self, self.app)
        self.wait_window(dlg)            # block until dialog closes
        if dlg.result_excel_path:        # dialog sets this on success
            self._input_var.set(dlg.result_excel_path)

    def _start(self):
        inp = self._input_var.get().strip()
        src_root = self._src_root_var.get().strip()
        out = self._output_var.get().strip()

        if not inp:
            messagebox.showwarning("Missing Input",
                "Please select a Coverity HTML report folder or Excel file.")
            return

        # Auto-detect input type
        input_path = ""
        input_mode = "html"

        if os.path.isfile(inp):
            ext = os.path.splitext(inp)[1].lower()
            if ext in ('.xlsx', '.xls'):
                input_mode = "excel"
                input_path = inp
            elif ext == '.html':
                input_mode = "html"
                input_path = inp
            else:
                messagebox.showwarning("Invalid File",
                    "Please select an HTML file, Excel file (.xlsx/.xls), or a folder.")
                return
        elif os.path.isdir(inp):
            index_path = os.path.join(inp, "index.html")
            if not os.path.isfile(index_path):
                messagebox.showerror("Invalid Report",
                    f"No index.html found in:\n{inp}\n\n"
                    "Please select a valid Coverity HTML report folder.")
                return
            input_path = inp
            input_mode = "html"
        else:
            messagebox.showerror("Not Found", f"Path not found:\n{inp}")
            return

        # Source root is required
        if not src_root:
            messagebox.showwarning("Missing Input",
                "Please select the Source Code Root folder.\n\n"
                "Local source files are required for accurate analysis.")
            return
        if not os.path.isdir(src_root):
            messagebox.showerror("Not Found", f"Source code root not found:\n{src_root}")
            return

        # Sanity check
        src_root_abs = os.path.abspath(src_root)
        input_abs = os.path.abspath(input_path)
        if src_root_abs == os.path.dirname(input_abs) or src_root_abs == input_abs:
            messagebox.showerror("Wrong Folder Selected",
                "The Source Code Root cannot be the same as the input report.\n\n"
                "Please select the folder that contains your actual C/C++ source files.")
            return

        if os.path.isfile(os.path.join(src_root, "index.html")):
            msg = ("The selected Source Code Root contains 'index.html'.\n\n"
                   "This looks like the Coverity HTML report folder, not your source code.\n"
                   "Are you sure you want to continue?")
            if not messagebox.askyesno("Suspicious Source Root", msg):
                return

        # Quick scan for source files
        src_count = 0
        html_count = 0
        for root, dirs, files in os.walk(src_root):
            for f in files:
                if f.endswith(('.c', '.cpp', '.h', '.hpp', '.cc', '.cxx')):
                    src_count += 1
                elif f.endswith('.html'):
                    html_count += 1
            if src_count > 5:
                break

        if src_count == 0 and html_count > 0:
            messagebox.showerror("Wrong Folder Selected",
                f"No C/C++ source files found in:\n{src_root}\n\n"
                f"Found {html_count} HTML files instead.\n"
                "Please select the folder with your project's .c / .cpp / .h files.")
            return
        elif src_count == 0:
            messagebox.showwarning("No Source Files",
                f"No .c / .cpp / .h files found in:\n{src_root}")
            return

        if not os.path.isdir(out):
            messagebox.showerror("Not Found", f"Output folder not found:\n{out}")
            return

        self.app.show(AnalysisPage,
                      input_path=input_path,
                      input_mode=input_mode,
                      src_root=src_root,
                      output_folder=out,
                      language=self._lang_var.get())


# -- Analysis Page -------------------------------------------------------------
class AnalysisPage(Page):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._input_path = ""
        self._input_mode = "html"
        self._src_root = ""
        self._out_folder = ""
        self._language = "cpp"
        self._build()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        hdr = tk.Frame(self, bg=C_PANEL, height=60)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="Running Disposition Analysis",
                 font=("Segoe UI", 14, "bold"), bg=C_PANEL, fg=C_TEXT).pack(
            side="left", padx=20, pady=12)

        pbar_f = tk.Frame(self, bg=C_BG)
        pbar_f.pack(fill="x", padx=30, pady=(20, 6))
        self._pbar_label = tk.Label(pbar_f, text="Initialising...",
                                    font=("Segoe UI", 10), bg=C_BG, fg=C_SUBTEXT)
        self._pbar_label.pack(anchor="w")
        self._pbar = ttk.Progressbar(pbar_f, style="Horizontal.TProgressbar",
                                     mode="indeterminate", length=600)
        self._pbar.pack(fill="x", pady=4)

        time_row = tk.Frame(pbar_f, bg=C_BG)
        time_row.pack(fill="x")
        self._pbar_stat = tk.Label(time_row, text="",
                                   font=("Segoe UI", 9), bg=C_BG, fg=C_SUBTEXT)
        self._pbar_stat.pack(side="left")
        self._pbar_time = tk.Label(time_row, text="",
                                   font=("Segoe UI", 9, "bold"), bg=C_BG, fg=C_ACCENT)
        self._pbar_time.pack(side="right")
        self._start_time = None
        self._defect_start_time = None
        self._index_secs = 0.0
        self._ticker_id  = None

        self._log = scrolledtext.ScrolledText(self,
            bg=C_CARD, fg=C_TEXT, insertbackground=C_TEXT,
            font=("Consolas", 9), relief="flat", state="disabled",
            wrap="none")
        self._log.pack(fill="both", expand=True, padx=20, pady=(0,10))
        self._log.bind("<Control-c>",
            lambda e: _copy_selected_text(self._log, self.app, "log output"))
        self._log.bind("<Control-a>", _select_all_text)

        btn_f = tk.Frame(self, bg=C_BG)
        btn_f.pack(fill="x", padx=20, pady=(0, 16))
        self._cancel_btn = tk.Button(btn_f, text="Cancel",
                                     command=self._cancel,
                                     bg=C_CARD, fg=C_BUG, relief="flat",
                                     font=("Segoe UI", 10), padx=14, pady=6,
                                     cursor="hand2")
        self._cancel_btn.pack(side="right")

        self._log.tag_configure("info",    foreground=C_SUBTEXT)
        self._log.tag_configure("ok",      foreground=C_FP)
        self._log.tag_configure("warn",    foreground=C_INTENT)
        self._log.tag_configure("error",   foreground=C_BUG)
        self._log.tag_configure("head",    foreground=C_ACCENT,
                                font=("Consolas", 9, "bold"))

    def _log_insert(self, tag, text):
        self._log.configure(state="normal")
        self._log.insert("end", text, tag)
        self._log.see("end")
        self._log.configure(state="disabled")

    def on_show(self, input_path="", input_mode="html", src_root="", output_folder="", language="cpp"):
        self._input_path = input_path
        self._input_mode = input_mode
        self._src_root   = src_root
        self._out_folder = output_folder
        self._language   = language
        self._log_clear()
        self._eta_str    = "calculating..."
        self._start_time = None

        # Pre-flight validation
        self._preflight_ok = True
        if self._input_mode == "html":
            if os.path.isdir(input_path):
                index_file = os.path.join(input_path, "index.html")
                if not os.path.isfile(index_file):
                    self._log_insert("error", f"ERROR: No index.html found in {input_path}\n")
                    self._log_insert("error", "Please select a valid Coverity HTML report folder.\n")
                    self._preflight_ok = False
                else:
                    self._log_insert("info", f"✓ Found index.html\n")
            elif os.path.isfile(input_path):
                self._log_insert("info", f"✓ Using HTML file: {os.path.basename(input_path)}\n")
        else:
            self._log_insert("info", f"✓ Using Excel file: {os.path.basename(input_path)}\n")

            # Local source files are the only source of truth — no Code/ folder needed

        if src_root and os.path.isdir(src_root):
            src_files = []
            for root, dirs, files in os.walk(src_root):
                src_files.extend([f for f in files if f.endswith(('.c', '.cpp', '.h', '.hpp'))])
                if len(src_files) > 100:  # Don't walk forever
                    break
            self._log_insert("info", f"✓ Found {len(src_files)} source files in {src_root}\n")
            if len(src_files) == 0:
                self._log_insert("warn", "⚠ No .c/.cpp/.h files found in source root!\n")
                self._log_insert("warn", "Please verify the source code root path.\n")
        else:
            self._log_insert("error", "✗ No source code root provided. Local source files are required.\n")
            self._preflight_ok = False

        if not self._preflight_ok:
            self._pbar_label.configure(text="Pre-flight check failed")
            self._pbar.stop()
            messagebox.showerror("Pre-flight Error", 
                "Cannot start analysis. Please check the log for details.\n\n"
                "Common issues:\n"
                "• Selected folder does not contain index.html\n"
                "• Source code root path is incorrect\n"
                "• Coverity report export was incomplete")
            self.app.show(SetupPage)
            return

        out_csv = os.path.join(output_folder, "coverity_dispositions.csv")
        try:
            with open(out_csv, "w", encoding="utf-8") as _f:
                pass
        except PermissionError:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_csv = os.path.join(output_folder,
                                   f"coverity_dispositions_{ts}.csv")
        self._out_csv = out_csv

        # New project / defect set loaded -> start a fresh final-decisions file
        # so decisions from a previously reviewed project do not carry over.
        try:
            f_dec = os.path.join(output_folder, "coverity_final_decisions.csv")
            if os.path.isfile(f_dec):
                os.remove(f_dec)
        except Exception:
            pass

        self._pbar.configure(mode="indeterminate")
        self._pbar.start(10)
        self._pbar_label.configure(text="Reading index.html...")
        self._pbar_stat.configure(text="")
        self._pbar_time.configure(text="Elapsed  0:00:00     ETC  ---")
        if self._ticker_id:
            self.after_cancel(self._ticker_id)
            self._ticker_id = None
        if not getattr(self, '_preflight_ok', True):
            return  # Don't start analysis if preflight failed
        self.app._stop_evt.clear()
        self.app._results = []
        t = threading.Thread(target=self._run, daemon=True)
        t.start()
        self.after(200, self._start_ticker)

    def _start_ticker(self):
        if self._start_time is None:
            self._start_time = time.time()
        self._defect_start_time = None
        self._index_secs = 0.0
        self._eta_str = "indexing..."
        self._tick_timer()

    def _tick_timer(self):
        if self._start_time is None:
            return
        elapsed = time.time() - self._start_time
        e_str   = str(timedelta(seconds=int(elapsed)))
        # During indexing show ETC as indexing, after defects started show real ETC
        if self._defect_start_time is None:
            eta_str = "indexing..."
        else:
            eta_str = getattr(self, "_eta_str", "calculating...")
        self._pbar_time.configure(
            text=f"Elapsed  {e_str}     ETC  {eta_str}")
        self._ticker_id = self.after(500, self._tick_timer)

    def _find_source_file(self, relative_path):
        """Search for a source file – source root first, then HTML folder.

        Handles both relative and absolute paths from Coverity reports.
        For absolute paths, extracts the relative portion and searches in src_root.
        """
        if not relative_path:
            return ""

        roots = []
        if self._src_root:
            roots.append(self._src_root)
        roots.append(self._input_path)
        parent = os.path.dirname(self._input_path)
        if parent and parent != self._input_path:
            roots.append(parent)

        def _suffix_score(cand: str, rel: str) -> int:
            """Count how many trailing path components match the defect path."""
            p = [x.lower() for x in cand.replace("\\", "/").split("/") if x]
            r = [x.lower() for x in rel.replace("\\", "/").split("/") if x]
            s = 0
            for a, b in zip(reversed(p), reversed(r)):
                if a == b:
                    s += 1
                else:
                    break
            return s

        rel_norm = relative_path.strip(os.sep) if os.path.isabs(relative_path) else relative_path
        best_path = ""
        best_score = -1
        # Cache of filename(lower) -> [paths] per root, built at most once per root,
        # so we never re-walk the whole source tree for every defect.
        if not hasattr(self, "_fn_index_cache"):
            self._fn_index_cache = {}

        for base in roots:
            if not base or not os.path.isdir(base):
                continue

            # 1) Direct join first (works for relative paths)
            candidate = os.path.join(base, relative_path)
            if os.path.isfile(candidate):
                return candidate

            # 2) For absolute paths, try progressively shorter suffixes, keeping
            #    the LONGEST match (fewest renamed parents) as the best.
            rel_parts = rel_norm.split(os.sep)
            for i in range(len(rel_parts)):
                tail_path = os.path.join(base, *rel_parts[i:])
                if os.path.isfile(tail_path):
                    score = len(rel_parts) - i
                    if score > best_score:
                        best_score = score
                        best_path = tail_path

            # 3) Basename match as a last resort, using a cached filename->paths
            #    index (one walk per root, not per defect). Among same-named files,
            #    pick the one whose directory path best preserves the defect's
            #    relative path, case-insensitively.
            basename = os.path.basename(rel_norm)
            if basename:
                bl = basename.lower()
                if base not in self._fn_index_cache:
                    idx = {}
                    for root, _dirs, fnames in os.walk(base):
                        for fn in fnames:
                            idx.setdefault(fn.lower(), []).append(os.path.join(root, fn))
                    self._fn_index_cache[base] = idx
                for cand in self._fn_index_cache[base].get(bl, []):
                    score = _suffix_score(cand, rel_norm)
                    if score > best_score:
                        best_score = score
                        best_path = cand
        return best_path

    def _find_function_line(self, filepath: str, func_name: str) -> int:
        """Use tree-sitter AST to find the exact line of a function definition."""
        if not filepath or not os.path.isfile(filepath) or not func_name:
            return 0
        return find_function_line_by_name(filepath, func_name, language=self._language)


    def _run(self):
        q    = self.app._q
        stop = self.app._stop_evt
        try:
            if self._input_mode == "excel":
                q.put(("head", f"Reading Excel: {self._input_path}\n"))
                try:
                    defects = parse_coverity_excel(self._input_path)
                except Exception as e:
                    q.put(("error", f"Failed to parse Excel: {e}\n"))
                    return
            else:
                q.put(("head", f"Reading index: {self._input_path}\n"))
                defects = parse_index_only(self._input_path)
            total   = len(defects)

            # Validate defects were found
            if total == 0:
                q.put(("error", "No defects found in index.html. Please verify this is a valid Coverity report.\n"))
                return

            # Check how many defects have valid detail files
            with_details = sum(1 for d in defects if d.get("detail_file") and os.path.isfile(d.get("detail_file", "")))
            q.put(("info", f"Found {total} defects. ({with_details} have detail pages)\n"))
            if with_details < total:
                q.put(("warn", f"Warning: {total - with_details} defects missing detail pages. Report may be incomplete.\n"))

            # Filter defects by language selection
            lang = self._language.lower()
            filtered_defects = []
            skipped_exts = set()
            for d in defects:
                fpath = d.get("file", "")
                ext = os.path.splitext(fpath)[1].lower()
                if lang == "c":
                    # C-only mode: skip .cpp, .cxx, .cc, .hpp, .hh
                    if ext in (".cpp", ".cxx", ".cc", ".hpp", ".hh", ".c++"):
                        skipped_exts.add(ext)
                        continue
                filtered_defects.append(d)

            if skipped_exts:
                q.put(("info", f"Language filter ('{lang}'): skipped {len(defects) - len(filtered_defects)} non-matching files ({', '.join(sorted(skipped_exts))})\n"))

            defects = filtered_defects
            total = len(defects)
            q.put(("progress_start", total))

            # Warm the one-time workspace index up front so the first defect does
            # not silently stall the whole run for tens of seconds, and so the
            # per-defect ETA below excludes this one-time indexing cost.
            if self._src_root and os.path.isdir(self._src_root):
                q.put(("info", "Indexing source tree once (cached for this run)…\n"))
                _idx_t0 = time.time()
                try:
                    warm_workspace_index(self._src_root, self._language)
                except Exception as exc:
                    q.put(("warn", f"  [Index] Workspace index skipped: {exc}\n"))
                q.put(("ready", total, time.time() - _idx_t0))
            else:
                q.put(("ready", total, 0.0))

            results = []
            out_csv = self._out_csv

            with open(out_csv, "w", newline="", encoding="utf-8") as csvf:
                writer = csv.writer(csvf)
                writer.writerow(["CID", "Checker", "Type", "Severity",
                                  "File", "Line", "Function",
                                  "Classification", "Comment", "Fix", "Timestamp",
                                  "Category"])

                _log_buf = []
                for i, defect in enumerate(defects):
                    if stop.is_set():
                        q.put(("warn", "Cancelled by user.\n"))
                        break

                    cid      = defect["cid"]
                    checker  = defect["checker"]
                    type_val = defect.get("type", "")
                    sev      = defect.get("severity", "")
                    filepath = defect.get("file", "")
                    line     = defect.get("line", 0)
                    func     = defect.get("function", "")
                    if func and func.lower() == "unclassified":
                        func = ""

                    # ---- Source code: real file first ----
                    src_code = ""
                    source_status = "none"
                    real_path = self._find_source_file(filepath) if filepath else ""

                    start_line = 1  # default until we extract code
                    # Decide how to anchor the analysis. Excel exports normally carry
                    # only file / function / line / checker — there is no Coverity event
                    # trace — so the analysis must be driven by the defect line, checker
                    # type and the file/function from the sheet. When the sheet reports the
                    # line as "Various" (or the line is missing/invalid) we cannot anchor a
                    # reliable analysis, so those rows are routed straight to "Needs review"
                    # and the user supplies the actual defect line number.
                    line_is_various   = defect.get("line_is_various", False)
                    manual_line_review = (self._input_mode == "excel"
                                          and (line <= 0 or line_is_various))
                    # Anchor extraction to function name when available — SOAP lines can
                    # be off from the web UI line due to SOAP v9 API limitations.
                    extract_line = line
                    if func and real_path and os.path.isfile(real_path):
                        found_line = self._find_function_line(real_path, func)
                        if found_line > 0:
                            extract_line = found_line
                            if line <= 0 or line_is_various:
                                q.put(("info", f"  [Various] Located '{func}' at line {found_line}\n"))
                        elif line <= 0 or line_is_various:
                            q.put(("warn", f"  [Various] Could not locate function '{func}' in source\n"))

                    if real_path and os.path.isfile(real_path):
                        q.put(("ok", f"  [Source] Loading: {os.path.basename(real_path)}\n"))
                        try:
                            result = extract_enclosing_function(
                                real_path, extract_line, language=self._language)
                            if isinstance(result, tuple) and len(result) >= 2:
                                code = result[0]
                                start_line = result[1] if len(result) >= 2 else 1
                            else:
                                code = result
                                start_line = 1
                            if code:
                                src_code = code
                                source_status = "function"
                            else:
                                with open(real_path, "r", encoding="utf-8", errors="replace") as f:
                                    src_code = f.read()
                                start_line = 1
                                source_status = "file"
                        except Exception as e:
                            q.put(("warn", f"  [Source] Error reading {os.path.basename(real_path)}: {e}\n"))
                            src_code = ""
                            start_line = 1

                    if not src_code:
                        q.put(("warn", f"  [Source] File not found: {filepath}\n"))

                    # Parse events (always from detail page)
                    _, events = parse_detail_page(defect.get("detail_file", ""))
                    if not events:
                        events = [{"step": 1, "type": checker,
                                   "description": type_val,
                                   "file": filepath, "line": line}]

                    # Function name extraction (AST or embedded)
                    if not func and filepath:
                        if not real_path or not os.path.isfile(real_path):
                            real_path = self._find_source_file(filepath)
                        if real_path and os.path.isfile(real_path):
                            try:
                                result = extract_enclosing_function(
                                    real_path, extract_line, language=self._language)
                                if isinstance(result, tuple):
                                    code = result[0]
                                else:
                                    code = result
                                if code:
                                    m = re.search(r'(?:\b(?:\w+\s+)+)?(\w+)\s*\(', code.strip())
                                    if m:
                                        func = m.group(1)
                            except Exception:
                                pass
                        # Last resort: from source code (strip line numbers if present)
                        if not func and src_code:
                            for line_text in src_code.splitlines()[:5]:
                                cleaned = re.sub(r'^\s*\d+\s+', '', line_text).strip()
                                m = re.search(r'(?:\b(?:\w+\s+)+)?(\w+)\s*\(', cleaned)
                                if m:
                                    func = m.group(1)
                                    break
                        defect["function"] = func

                    # Build rich cross-function context (callees, callers, signatures)
                    rich_ctx = {}
                    if self._src_root and os.path.isdir(self._src_root):
                        try:
                            # Pass real_path (resolved local file) so build_defect_context
                            # can extract the correct function and absolute line numbers
                            path_for_ctx = real_path if real_path else filepath
                            rich_ctx = build_defect_context(
                                {"events": events, "file": path_for_ctx, "line": line, "function": func},
                                self._src_root, self._language)
                            rich_ctx.pop("function_code", None)  # keep our own extraction
                        except Exception as e:
                            q.put(("warn", f"  [Context] Rich context build failed: {e}\n"))
                    # Preserve local start_line and src_code; rich_ctx provides callees/tree
                    context = {
                        **rich_ctx,
                        "function_code": src_code,
                        "source_code": src_code,
                        "code_start_line": start_line,
                    }
                    # Line "Various" is handled above: for Excel exports without a concrete
                    # line we route straight to "Needs review" so the user supplies the
                    # actual defect line; otherwise run the normal code-anchored analysis.
                    analyze_error = None
                    if manual_line_review:
                        # Excel gave no concrete line. For function-scoped checkers
                        # (CHECKED_RETURN, UNUSED_VALUE, DEADCODE, ...) we can still
                        # produce a reasoned verdict from the whole function — the
                        # confidence is capped and the comment is annotated with the
                        # 'Various' caveat. Memory-safety checkers are kept manual so
                        # we never guess the wrong access.
                        if (src_code and func
                                and checker.upper() in _LINE_AGNOSTIC_CHECKERS):
                            manual_line_review = False
                            line = 0
                        else:
                            classification = "Needs review"
                            comment = (
                                f"The Excel export lists {checker} in "
                                f"{func or filepath or '(unknown file)'} but does not include a "
                                f"concrete defect line (reported as "
                                f"{'Various' if line_is_various else 'missing/invalid'}). "
                                f"Please review the source shown above and enter the actual defect "
                                f"line number so this finding can be re-analysed."
                            )
                            fix = "Manual review required — provide the actual line number."
                            confidence = 0.0
                    if not manual_line_review:
                        try:
                            classification, comment, fix, confidence = analyze_defect(
                                context, checker, events, sub_checker=type_val,
                                file=filepath, line=line, function=func,
                                line_is_various=line_is_various,
                                tree=context.get("function_tree"))
                        except Exception as ex:
                            # Last-resort safety net only; keep the exception text and
                            # preserve the extracted source context for the reviewer.
                            analyze_error = ex
                            classification = "Needs review"
                            comment        = f"Automatic analysis raised an error: {ex}"
                            fix            = "Manual review required."
                            confidence     = 0.0

                    # Phase 0 instrumentation: why did this land in Needs review?
                    needs_review_reason = ""
                    if classification == "Needs review":
                        if manual_line_review:
                            needs_review_reason = "excel_line_missing"
                        elif analyze_error is not None:
                            needs_review_reason = "exception"
                        elif line_is_various:
                            needs_review_reason = "line_various"
                        elif not src_code:
                            needs_review_reason = "no_code"
                        else:
                            needs_review_reason = "low_confidence_or_unhandled"

                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    writer.writerow([cid, checker, type_val, sev, filepath, line,
                                     func, classification, comment, fix, ts,
                                     category_for_checker(checker)])
                    csvf.flush()

                    results.append({
                        "cid": cid, "checker": checker, "type": type_val,
                        "severity": sev, "file": filepath, "line": line,
                        "line_is_various": line_is_various,
                        "function": func, "classification": classification,
                        "comment": comment, "fix": fix, "confidence": confidence,
                        "source_code": src_code,
                        "source_origin": source_status,
                        "needs_review_reason": needs_review_reason,
                        "events": events,
                        "accepted": False,
                        "accepted_by": "",
                        "accepted_at": "",
                    })

                    tag = {"Bug": "error", "False positive": "ok",
                           "Intentional": "warn", "Needs review": "info"}.get(
                        classification, "info")
                    _log_buf.append((tag,
                        f"ID {cid:5d}  [{checker:<20s}]  "
                        f"{classification:<16s}  {comment[:55]}"
                        + (f"  <reason={needs_review_reason}>" if needs_review_reason else "")
                        + "\n"))

                    q.put(("tick", i + 1, total, _log_buf[:]))
                    _log_buf.clear()

            self.app._results = results

            # Persist a per-run Needs-review breakdown so the exact cause is easy
            # to inspect (classification vs. reason vs. checker) without re-running.
            try:
                from collections import Counter
                brk = [
                    "Classification counts:",
                    "  " + ", ".join(f"{k}: {v}" for k, v in Counter(
                        r.get("classification", "?") for r in results).most_common()),
                    "",
                    f"Needs review rows: {sum(1 for r in results if r.get('classification') == 'Needs review')}",
                    "  by reason: " + ", ".join(f"{k}: {v}" for k, v in Counter(
                        r.get("needs_review_reason", "other") for r in results
                        if r.get("classification") == "Needs review").most_common()),
                    "  by checker: " + ", ".join(f"{k}: {v}" for k, v in Counter(
                        r.get("checker", "?") for r in results
                        if r.get("classification") == "Needs review").most_common(10)),
                    "  by category: " + ", ".join(f"{k}: {v}" for k, v in Counter(
                        category_for_checker(r.get("checker", "")) for r in results
                        if r.get("classification") == "Needs review").most_common()),
                ]
                fdir = self.app._frames[SetupPage]._output_var.get().strip()
                if not fdir or not os.path.isdir(fdir):
                    fdir = os.path.join(os.path.expanduser("~"), "Documents")
                with open(os.path.join(fdir, "needs_review_breakdown.txt"), "w", encoding="utf-8") as _f:
                    _f.write("\n".join(brk) + "\n")
            except Exception:
                pass

            q.put(("done", out_csv))

        except Exception as ex:
            q.put(("error", f"Fatal error: {ex}\n"))

    def handle_msg(self, msg):
        kind = msg[0]
        if kind == "progress_start":
            total = msg[1]
            self._pbar.stop()
            self._pbar.configure(mode="determinate", maximum=total, value=0)
            self._pbar_label.configure(text=f"0 / {total}   analysing...")
            self._pbar_stat.configure(text="0%   (0 / " + str(total) + " defects)")
            self._eta_str = "calculating..."
        elif kind == "ready":
            _, total, idx_secs = msg
            self._pbar.stop()
            self._pbar.configure(mode="determinate", maximum=total or 1, value=0)
            self._pbar_label.configure(text=f"0 / {total}   analysing...")
            self._pbar_stat.configure(text="0%   (0 / " + str(total) + " defects)")
            # Keep total elapsed running, but start defect-loop timing for ETA
            self._index_secs = idx_secs
            self._defect_start_time = time.time()
            self._eta_str = "calculating..."
            # Show total elapsed including indexing rather than resetting to 0
            total_elapsed = time.time() - self._start_time if self._start_time else idx_secs
            e_str = str(timedelta(seconds=int(total_elapsed)))
            self._pbar_time.configure(text=f"Elapsed  {e_str}     ETC  calculating...")
            self._log.configure(state="normal")
            self._log.insert("end",
                             f"Workspace indexed in {idx_secs:.1f}s — starting per-defect analysis.\n",
                             "ok")
            self._log.see("end")
            self._log.configure(state="disabled")
        elif kind == "tick":
            _, done, total, log_lines = msg
            pct = int(done / total * 100) if total else 0
            self._pbar["maximum"] = total
            self._pbar["value"]   = done
            self._pbar_label.configure(
                text=f"{done} / {total}   —   analysing...")
            self._pbar_stat.configure(
                text=f"{pct}%   ({done} / {total} defects)")
            # ETA based on defect loop only (indexing excluded) for realistic estimate
            def_start = getattr(self, "_defect_start_time", None) or self._start_time
            if def_start and done > 1:
                elapsed   = time.time() - def_start
                rate      = done / elapsed if elapsed > 0 else 0
                remaining = (total - done) / rate if rate > 0 else 0
                # Cap ETC at reasonable bound (avoid showing 100h for slow start)
                remaining = min(remaining, 48 * 3600)
                self._eta_str = str(timedelta(seconds=int(remaining)))
                # Warn if analysis is suspiciously fast (< 50ms per defect on average)
                avg_ms = (elapsed / done) * 1000 if elapsed > 0 else 0
                if avg_ms < 50 and done > 5:
                    self._pbar_label.configure(
                        text=f"{done} / {total}   —   WARNING: Analysis very fast ({avg_ms:.0f}ms/defect). Source files may not be loading.")
            self._log.configure(state="normal")
            for tag, text in log_lines:
                self._log.insert("end", text, tag)
            self._log.see("end")
            self._log.configure(state="disabled")
        elif kind in ("log", "info", "warn", "error", "head", "ok"):
            tag  = kind if kind != "log" else msg[1]
            text = msg[1] if kind != "log" else msg[2]
            self._log.configure(state="normal")
            self._log.insert("end", text, tag)
            self._log.see("end")
            self._log.configure(state="disabled")
        elif kind == "done":
            out_csv = msg[1]
            self._pbar["value"] = self._pbar["maximum"]
            if self._ticker_id:
                self.after_cancel(self._ticker_id)
                self._ticker_id = None
            elapsed = time.time() - self._start_time if self._start_time else 0
            # Include indexing time in final elapsed (already included via _start_time)
            e_str   = str(timedelta(seconds=int(elapsed)))
            self._pbar_label.configure(text="Analysis complete!")
            self._pbar_time.configure(
                text=f"Elapsed  {e_str}     ETC  Done \u2713")
            self._start_time = None
            self._defect_start_time = None
            self._eta_str    = "Done"

            # Count source loading statistics
            local_count = sum(1 for r in self.app._results if r.get("source_code") and len(r.get("source_code", "")) > 50)
            no_src_count = len(self.app._results) - local_count

            # Count "Various" line number defects
            various_total = sum(1 for r in self.app._results if r.get("line_is_various"))

            msg_text = f"Analysis complete in {e_str}!\n\n"
            msg_text += f"Results saved to:\n{out_csv}\n\n"
            msg_text += f"Source loading:\n"
            msg_text += f"  • Local files loaded: {local_count}\n"
            msg_text += f"  • Source not found: {no_src_count}"

            if various_total > 0:
                msg_text += f"\n\n  • Line number 'Various': {various_total} findings (manual review required)"

            if elapsed < 5 and len(self.app._results) > 50:
                msg_text += "\n\n⚠ WARNING: Analysis completed very quickly."
                msg_text += "\nSource files may not be loading correctly."
                msg_text += "\nPlease verify your Source Code Root path."

            messagebox.showinfo("Done", msg_text)
            self.app._notify(
                f"Analysis complete \u2713  {len(self.app._results)} defects ready",
                "success")
            self.app.show(ResultsPage)
        elif kind == "error":
            if self._ticker_id:
                self.after_cancel(self._ticker_id)
                self._ticker_id = None
            self._pbar.stop()
            messagebox.showerror("Error", msg[1])

    def _cancel(self):
        self.app._stop_evt.set()
        self.app.show(SetupPage)

    def _log_clear(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")


# -- Results Page --------------------------------------------------------------
class ResultsPage(Page):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._all_results  = []
        self._sel_idx      = None
        self._active_cls   = "All"
        self._active_cat   = "All"
        self._soap_client  = None
        self._conn_tested  = False
        # Server settings StringVars — created before _build() uses them
        self._sv_host      = tk.StringVar()
        self._sv_port      = tk.StringVar(value="443")
        self._sv_user      = tk.StringVar()
        self._sv_pass      = tk.StringVar()
        self._sv_store     = tk.StringVar(value="Default")
        self._sv_ssl       = tk.BooleanVar(value=True)
        self._sv_verify_ssl = tk.BooleanVar(value=True)  # secure by default (verify on) — previously False
        self._sv_push_mode = tk.StringVar(value="all")
        self._build()

    def _build(self):
        # -- Top toolbar --
        tb = tk.Frame(self, bg=C_PANEL, height=52)
        tb.pack(fill="x")
        tb.pack_propagate(False)

        tk.Label(tb, text="Disposition Results",
                 font=("Segoe UI", 13, "bold"), bg=C_PANEL, fg=C_TEXT).pack(
            side="left", padx=20, pady=12)

        self._filter_var = tk.StringVar(value="All")
        for label in ["All", "Bug", "False positive", "Intentional", "Needs review", "Accepted"]:
            color = CLASS_COLOR.get(label, C_SUBTEXT)
            tk.Button(tb, text=label, relief="flat",
                      bg=C_CARD, fg=color,
                      font=("Segoe UI", 9, "bold"),
                      padx=10, pady=4, cursor="hand2",
                      activebackground=C_BORDER,
                      command=lambda l=label: self._filter(l)).pack(
                side="left", padx=2, pady=10)

        # Category filter dropdown — narrows the tree by checker category while
        # preserving any active classification filter.
        tk.Label(tb, text="Category:", bg=C_PANEL, fg=C_SUBTEXT,
                 font=("Segoe UI", 9, "bold")).pack(
            side="left", padx=(16, 4), pady=10)
        self._cat_var = tk.StringVar(value="All")
        self._cat_combo = ttk.Combobox(tb, textvariable=self._cat_var,
                                       state="readonly", width=26,
                                       values=["All"], font=("Segoe UI", 9))
        self._cat_combo.pack(side="left", padx=(0, 4), pady=10)
        self._cat_combo.bind("<<ComboboxSelected>>",
            lambda e: self._filter_cat(self._cat_var.get()))


        tk.Button(tb, text="?  New Analysis",
                  command=lambda: self.app.show(SetupPage),
                  bg=C_CARD, fg=C_ACCENT, relief="flat",
                  font=("Segoe UI", 9), padx=10, pady=4,
                  cursor="hand2").pack(side="right", padx=12, pady=10)

        # Push the defects currently in this table straight to Coverity
        # Connect — no CSV export/re-import round trip.
        tk.Button(tb, text="\u2b06  Push these to Coverity",
                  command=self._open_direct_push,
                  bg="#1D4ED8", fg="#FFFFFF", relief="flat",
                  font=("Segoe UI", 9, "bold"), padx=10, pady=4,
                  cursor="hand2", activebackground="#1E40AF"
                  ).pack(side="right", padx=(0, 4), pady=10)

        # -- Summary chips --
        self._summary_f = tk.Frame(self, bg=C_BG)
        self._summary_f.pack(fill="x", padx=16, pady=(8, 4))


        # -- Main Paned: 3 columns horizontal --
        pane = tk.PanedWindow(self, orient="horizontal",
                              bg=C_BORDER, sashwidth=4, relief="flat")
        pane.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # ---- COLUMN 1: Minimal tree (ID + Class) ----
        left = tk.Frame(pane, bg=C_BG, width=200)
        left.pack_propagate(False)
        pane.add(left, minsize=160, width=200)

        self._tree = ttk.Treeview(left, columns=("ID", "Class"), show="headings",
                                   selectmode="browse")
        self._tree.column("ID",    width=45,  anchor="center", stretch=False)
        self._tree.column("Class", width=150, anchor="w",      stretch=True)
        self._tree.heading("ID",    text="ID",    anchor="w")
        self._tree.heading("Class", text="Class", anchor="w")

        vsb = ttk.Scrollbar(left, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)

        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Double-1>", self._on_double_click)

        for cls, col in CLASS_COLOR.items():
            self._tree.tag_configure(cls, foreground=col)
        self._tree.tag_configure("pushed",    foreground="#16A34A")
        self._tree.tag_configure("push_fail", foreground="#DC2626")
        self._tree.tag_configure("conf_high", foreground="#16A34A")
        self._tree.tag_configure("conf_med",  foreground="#D97706")
        self._tree.tag_configure("conf_low",  foreground="#DC2626")
        self._tree.tag_configure("cat_header", font=("Segoe UI", 9, "bold"),
                                 foreground=C_ACCENT, background="#EAF1FB")

        # ---- COLUMN 2: Info panel ----
        mid = tk.Frame(pane, bg=C_PANEL, width=420)
        mid.pack_propagate(False)
        pane.add(mid, minsize=350, width=420)

        self._detail_id = tk.Text(mid, height=2, bg=C_PANEL,
            font=("Segoe UI", 13, "bold"), relief="flat", wrap="word",
            borderwidth=0, highlightthickness=0, state="disabled",
            fg=C_ACCENT)
        self._detail_id.bind("<Control-c>",
            lambda e: _copy_selected_text(self._detail_id, self.app, "id / checker"))
        self._detail_id.bind("<Control-a>", _select_all_text)
        self._detail_id.pack(anchor="w", padx=14, pady=(14, 0))

        self._detail_meta = tk.Text(mid, height=3, bg=C_PANEL,
            font=("Segoe UI", 9), relief="flat", wrap="word",
            borderwidth=0, highlightthickness=0, state="disabled",
            fg=C_SUBTEXT)
        self._detail_meta.bind("<Control-c>",
            lambda e: _copy_selected_text(self._detail_meta, self.app, "metadata"))
        self._detail_meta.bind("<Control-a>", _select_all_text)
        self._detail_meta.pack(fill="x", padx=14, pady=(2, 0))

        self._detail_class = tk.Text(mid, height=1, bg=C_PANEL,
            font=("Segoe UI", 12, "bold"), relief="flat", wrap="word",
            borderwidth=0, highlightthickness=0, state="disabled",
            fg=C_FP)
        self._detail_class.tag_configure("cls", foreground=C_FP)
        self._detail_class.bind("<Control-c>",
            lambda e: _copy_selected_text(self._detail_class, self.app, "classification"))
        self._detail_class.bind("<Control-a>", _select_all_text)
        self._detail_class.pack(fill="x", padx=14, pady=(10, 0))

        self._detail_comment = tk.Text(mid, height=4, bg=C_PANEL, fg=C_TEXT,
            font=("Segoe UI", 10), relief="flat", wrap="word",
            borderwidth=0, highlightthickness=0, state="disabled")
        self._detail_comment.bind("<Control-c>",
            lambda e: _copy_selected_text(self._detail_comment, self.app, "comment"))
        self._detail_comment.bind("<Control-a>", _select_all_text)
        self._detail_comment.pack(fill="both", expand=True, padx=14, pady=(2, 6))

        self._fix_label = tk.Label(mid, text="Proposed Fix",
                 font=("Segoe UI", 9, "bold"), bg=C_PANEL, fg=C_ACCENT)
        self._fix_box = tk.Text(mid,
            height=4, bg="#EFF6FF", fg=C_TEXT, font=("Consolas", 9),
            relief="flat", state="disabled", wrap="word",
            borderwidth=1, highlightthickness=1, highlightbackground=C_ACCENT)
        self._fix_box.bind("<Control-c>",
            lambda e: _copy_selected_text(self._fix_box, self.app, "selected fix"))
        self._fix_box.bind("<Control-a>", _select_all_text)

        sep = tk.Frame(mid, bg=C_BORDER, height=1)
        sep.pack(fill="x", padx=14, pady=4)

        # Buttons
        btn_f = tk.Frame(mid, bg=C_PANEL)
        btn_f.pack(fill="x", padx=14, pady=(4, 10))

        def mk_btn(txt, bg, cmd, disabled_fg="#FFFFFF"):
            return tk.Button(btn_f, text=txt, command=cmd,
                             bg=bg, fg="#FFFFFF",
                             disabledforeground=disabled_fg,
                             font=("Segoe UI", 9, "bold"),
                             relief="flat", padx=10, pady=6,
                             cursor="hand2",
                             activebackground=C_BORDER)

        self._open_btn     = mk_btn("\u26F6  Full code view",  C_ACCENT,   self._open_detail_window)
        self._accept_btn   = mk_btn("\u2714  Accept",      "#16A34A",  self._accept)
        self._override_btn = mk_btn("\u270E  Override",    "#D97706",  self._override)
        self._open_btn.pack(side="left", padx=(0, 6))
        self._accept_btn.pack(side="left", padx=(0, 6))
        self._override_btn.pack(side="left")


        # ---- COLUMN 3: Source code viewer (highlighted area) ----
        code_f = tk.Frame(pane, bg="#1E1E1E")
        pane.add(code_f, minsize=300)

        code_hdr = tk.Frame(code_f, bg="#252526", height=28)
        code_hdr.pack(fill="x")
        code_hdr.pack_propagate(False)
        tk.Label(code_hdr, text="\U0001f4c4  Source",
            font=("Segoe UI", 9, "bold"), bg="#252526", fg="#CCCCCC"
        ).pack(side="left", padx=10, pady=4)
        self._code_fname_lbl = tk.Label(code_hdr, text="",
            font=("Consolas", 8), bg="#252526", fg="#808080"
        )
        self._code_fname_lbl.pack(side="right", padx=10, pady=4)

        self._code_box = scrolledtext.ScrolledText(code_f,
            bg="#1E1E1E", fg="#D4D4D4",
            font=("Consolas", 9), relief="flat", wrap="none",
            insertbackground="#D4D4D4", selectbackground="#264F78",
            state="disabled")
        self._code_box.pack(fill="both", expand=True, padx=0, pady=0)
        self._code_box.bind("<Control-c>",
            lambda e: _copy_selected_text(self._code_box, self.app, "selected source"))
        self._code_box.bind("<Control-a>", _select_all_text)

        self._code_box.tag_configure("lineno", foreground="#858585")
        self._code_box.tag_configure("error_line", background="#5A1D1D")


    # ------------------------------------------------------------------
    def on_show(self):
        self._all_results = list(self.app._results)
        # Reset classification + category filters on each visit to the page.
        self._active_cls = "All"
        self._active_cat = "All"
        self._filter_var.set("All")
        self._cat_var.set("All")
        categories = [cat for cat, _items in group_results_by_category(self._all_results).items()]
        self._cat_combo.configure(values=["All"] + categories)
        self._populate(self._all_results)
        self._update_summary(self._all_results)

    def _populate(self, results):
        self._tree.delete(*self._tree.get_children())
        groups = group_results_by_category(results)
        for cat, items in groups.items():
            parent = self._tree.insert("", "end", iid=f"cat-{_iid_safe(cat)}",
                                       values=("", f"{cat} ({len(items)})"),
                                       tags=("cat_header",))
            for r in items:
                if r.get("accepted", False):
                    cls = "Accepted"
                else:
                    cls = r.get("classification", "Needs review")
                push_status = r.get("push_status", "")
                push_tag = "pushed" if push_status == "✓" else ("push_fail" if push_status == "✗" else cls)
                conf = r.get("confidence", 0.0)
                # Color tag based on confidence level
                if conf >= 0.8:
                    conf_tag = "conf_high"
                elif conf >= 0.6:
                    conf_tag = "conf_med"
                else:
                    conf_tag = "conf_low"
                self._tree.insert(parent, "end", tags=(push_tag, conf_tag), values=(
                    r["cid"],
                    cls,
                ))

    def _update_summary(self, results):
        for w in self._summary_f.winfo_children():
            w.destroy()
        from collections import Counter
        counts = Counter()
        for r in results:
            if r.get("accepted", False):
                counts["Accepted"] += 1
            else:
                counts[r.get("classification", "Needs review")] += 1
        total = len(results)
        tk.Label(self._summary_f, text=f"Total: {total}",
                 font=("Segoe UI", 10, "bold"), bg=C_BG, fg=C_TEXT).pack(
            side="left", padx=(0, 16))
        for cls, count in counts.most_common():
            col = CLASS_COLOR.get(cls, C_SUBTEXT)
            chip = tk.Frame(self._summary_f, bg=col, padx=8, pady=3)
            chip.pack(side="left", padx=4)
            tk.Label(chip, text=f"{cls}  {count}",
                     font=("Segoe UI", 9, "bold"),
                     bg=col, fg="#11111B").pack()

        # Phase 0 instrumentation: show why remaining Needs-review rows stayed there.
        need_reasons = Counter(
            r.get("needs_review_reason") or "other" for r in results
            if r.get("classification") == "Needs review")
        if need_reasons:
            reason_str = "Review due to: " + ", ".join(
                f"{k}:{v}" for k, v in need_reasons.most_common())
            tk.Label(self._summary_f, text=f"  {reason_str}",
                     font=("Segoe UI", 8), bg=C_BG, fg="#94A3B8").pack(
                side="left", padx=(8, 0))

    def _filter(self, label):
        self._active_cls = label
        self._apply_filters()

    def _filter_cat(self, category):
        self._active_cat = category
        self._apply_filters()

    def _apply_filters(self, _event=None):
        # Clear previous selection and panels
        self._tree.selection_remove(*self._tree.selection())
        self._sel_idx = None
        self._detail_id.configure(state="normal")
        self._detail_id.delete(1.0, tk.END)
        self._detail_id.insert(tk.END, "Select a defect")
        self._detail_id.configure(state="disabled")
        self._detail_meta.configure(state="normal")
        self._detail_meta.delete(1.0, tk.END)
        self._detail_meta.configure(state="disabled")
        self._detail_class.configure(state="normal")
        self._detail_class.delete(1.0, tk.END)
        self._detail_class.configure(state="disabled")
        self._detail_comment.configure(state="normal")
        self._detail_comment.delete(1.0, tk.END)
        self._detail_comment.configure(state="disabled")
        self._fix_label.pack_forget()
        self._fix_box.pack_forget()
        self._accept_btn.configure(text="✔  Accept", bg="#16A34A", command=self._accept)
        self._code_box.configure(state="normal")
        self._code_box.delete("1.0", "end")
        self._code_box.configure(state="disabled")
        self._code_fname_lbl.configure(text="")

        results = self._all_results
        if self._active_cls == "Accepted":
            results = [r for r in results if r.get("accepted", False)]
        elif self._active_cls != "All":
            results = [r for r in results
                       if not r.get("accepted", False)
                       and r.get("classification") == self._active_cls]
        if self._active_cat != "All":
            results = [r for r in results
                       if category_for_checker(r.get("checker", "")) == self._active_cat]
        self._populate(results)

    def _sort(self, col):
        data = [(self._tree.set(k, col), k)
                for k in self._tree.get_children("")]
        data.sort()
        for idx, (_, k) in enumerate(data):
            self._tree.move(k, "", idx)

    def _select_by_id(self, cid):
        def _walk(parent=""):
            for child in self._tree.get_children(parent):
                vals = self._tree.item(child)["values"]
                if vals and vals[0] == cid:
                    return child
                found = _walk(child)
                if found:
                    return found
            return None
        item = _walk()
        if item:
            self._tree.selection_set(item)
            self._tree.see(item)
            self._on_select()

    def _on_select(self, _event=None):
        sel = self._tree.selection()
        if not sel:
            return
        child = sel[0]
        # Category header row — expand/collapse it rather than treat as a defect.
        if self._tree.parent(child) == "":
            self._toggle_category(child)
            return
        shown_cid = self._tree.item(child)["values"][0]
        defect = next((r for r in self._all_results if r["cid"] == shown_cid), None)
        if not defect:
            return
        self._sel_idx = defect

        is_accepted = defect.get("accepted", False)
        if is_accepted:
            cls = "Accepted"
            col = C_ACCEPTED
        else:
            cls = defect.get("classification", "Needs review")
            col = CLASS_COLOR.get(cls, C_TEXT)

        self._detail_id.configure(state="normal")
        self._detail_id.delete(1.0, tk.END)
        cat = category_for_checker(defect.get("checker", ""))
        self._detail_id.insert(tk.END, f"ID {defect['cid']}  —  {defect['checker']}  ({cat})")
        self._detail_id.configure(state="disabled")
        line_display = "Various" if defect.get("line_is_various") else defect.get("line", "")
        conf = defect.get('confidence', 0.0)
        conf_str = f"{int(conf*100)}%"
        conf_col = "#16A34A" if conf >= 0.8 else ("#D97706" if conf >= 0.6 else "#DC2626")
        self._detail_meta.configure(state="normal", fg=conf_col)
        self._detail_meta.delete(1.0, tk.END)
        self._detail_meta.insert(tk.END,
            f"{defect.get('file', '')}  :  line {line_display}   |   "
            f"Function: {defect.get('function') or 'N/A'}   •   "
            f"Severity: {defect.get('severity', 'N/A')}   •   "
            f"Confidence: {conf_str}")
        self._detail_meta.configure(state="disabled")
        self._detail_class.configure(state="normal")
        self._detail_class.delete(1.0, tk.END)
        self._detail_class.tag_configure("cls", foreground=col)
        self._detail_class.insert(tk.END, cls, "cls")
        self._detail_class.configure(state="disabled")

        if is_accepted:
            comment_text = f"Accepted by {defect.get('accepted_by', 'unknown')} at {defect.get('accepted_at', '')}. {defect.get('comment', '')}"
        else:
            comment_text = defect.get("comment", "")
        self._detail_comment.configure(state="normal")
        self._detail_comment.delete(1.0, tk.END)
        self._detail_comment.insert(tk.END, comment_text)
        self._detail_comment.configure(state="disabled")

        cls_for_fix = defect.get("classification", "")
        fix_text = defect.get("fix", "")
        if cls_for_fix in ("Bug", "Needs review") and fix_text and fix_text not in ("No fix required.", "Manual review required.", ""):
            self._fix_label.pack(anchor="w", padx=14, pady=(4, 2))
            self._fix_box.pack(fill="both", expand=True, padx=14, pady=(0, 6))
            self._fix_box.configure(state="normal")
            self._fix_box.delete("1.0", "end")
            self._fix_box.insert("end", fix_text)
            self._fix_box.configure(state="disabled")
        else:
            self._fix_label.pack_forget()
            self._fix_box.pack_forget()

        # -- Populate source code viewer --
        self._populate_code_viewer(defect)

        if is_accepted:
            self._accept_btn.configure(
                text="\u2714  Accepted",
                bg=C_ACCEPTED,
                fg="#FFFFFF",
                activebackground=C_ACCEPTED,
                command=self._show_already_accepted
            )
        else:
            self._accept_btn.configure(
                text="\u2714  Accept",
                bg="#16A34A",
                fg="#FFFFFF",
                activebackground="#16A34A",
                command=self._accept
            )

    def _populate_code_viewer(self, defect):
        """Load source code into the right-side code viewer."""
        src_root = self.app._frames[SetupPage]._src_root_var.get().strip()
        file_path = defect.get("file", "")
        raw_lines = []
        origin = "none"

        # Try local file first
        if file_path and src_root:
            search_path = file_path
            if not os.path.isabs(search_path):
                search_path = os.path.join(src_root, search_path)
            if os.path.isabs(file_path) and not os.path.isfile(search_path):
                rel_parts = file_path.strip(os.sep).split(os.sep)
                for i in range(len(rel_parts)):
                    tail_path = os.path.join(src_root, *rel_parts[i:])
                    if os.path.isfile(tail_path):
                        search_path = tail_path
                        break
            if not os.path.isfile(search_path):
                for root, dirs, files in os.walk(src_root):
                    if os.path.basename(file_path) in files:
                        search_path = os.path.join(root, os.path.basename(file_path))
                        break
            if os.path.isfile(search_path):
                try:
                    with open(search_path, "r", encoding="utf-8", errors="replace") as f:
                        raw_lines = f.readlines()
                    origin = "local"
                except Exception:
                    pass

        # Fallback to embedded source
        if not raw_lines:
            embedded = defect.get("source_code", "")
            if embedded:
                raw_lines = embedded.splitlines(keepends=True)
                origin = "html"

        if not raw_lines:
            raw_lines = ["(No source code available)"]
            origin = "none"

        self._code_box.configure(state="normal")
        self._code_box.delete("1.0", "end")

        error_line = defect.get("line", 0)
        total = len(raw_lines)

        for i, line in enumerate(raw_lines):
            lno = i + 1
            display = line.rstrip("\n").rstrip("\r")
            self._code_box.insert("end", f"{lno:>6}  ", "lineno")
            self._code_box.insert("end", display + "\n")
            if lno == error_line:
                line_start = self._code_box.index("end-2l linestart")
                line_end = self._code_box.index("end-1l lineend")
                self._code_box.tag_add("error_line", line_start, line_end)

        # Scroll to error line with padding to center it
        if error_line and 1 <= error_line <= total:
            self._code_box.see(f"{error_line}.0")
        self._code_box.configure(state="disabled")

        fname = os.path.basename(file_path) if file_path else ""
        if origin == "local":
            self._code_fname_lbl.configure(text=f"✓ {fname}", fg="#4EC9B0")
        elif origin == "html":
            self._code_fname_lbl.configure(text=f"⚠ {fname}", fg="#FFCC00")
        else:
            self._code_fname_lbl.configure(text="No source", fg="#F44747")

    def _open_detail_window(self, defect=None):
        d = defect or self._sel_idx
        if not d:
            messagebox.showinfo("No selection", "Click a row first.")
            return
        src_root = self.app._frames[SetupPage]._src_root_var.get().strip()
        DetailWindow(self, d, self.app, src_root=src_root)

    def _on_double_click(self, _event=None):
        sel = self._tree.selection()
        if not sel:
            return
        item = sel[0]
        # Category header row — toggle expand/collapse instead of opening a defect.
        if self._tree.parent(item) == "":
            self._toggle_category(item)
            return
        shown_cid = self._tree.item(item)["values"][0]
        defect = next((r for r in self._all_results if r["cid"] == shown_cid), None)
        if defect:
            self._open_detail_window(defect)

    def _toggle_category(self, item):
        try:
            open_state = bool(self._tree.item(item, "open"))
        except tk.TclError:
            return
        self._tree.item(item, open=(not open_state))
        self._tree.selection_remove(*self._tree.selection())
        self._sel_idx = None

    def _accept(self):
        if not self._sel_idx:
            return
        if self._sel_idx.get("accepted", False):
            messagebox.showinfo("Already Accepted", "This defect has already been accepted.")
            return

        self._sel_idx["accepted"] = True
        try:
            self._sel_idx["accepted_by"] = os.getlogin()
        except Exception:
            self._sel_idx["accepted_by"] = os.environ.get("USERNAME", "unknown")
        self._sel_idx["accepted_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self._save_decision(
            self._sel_idx,
            self._sel_idx.get("classification", "Needs review"),
            self._sel_idx.get("comment", ""),
            accepted=True)

        self._accept_btn.configure(
            text="\u2714  Accepted",
            bg=C_ACCEPTED,
            fg="#FFFFFF",
            activebackground=C_ACCEPTED,
            command=self._show_already_accepted
        )

        saved_cid = self._sel_idx["cid"]
        self._filter(self._filter_var.get())
        self._update_summary(self._all_results)

        for child in self._tree.get_children():
            if self._tree.item(child)["values"][0] == saved_cid:
                self._tree.selection_set(child)
                self._tree.see(child)
                break
        self._on_select()
        messagebox.showinfo("Saved", "Decision accepted and recorded.\nStatus updated to 'Accepted'.")

    def _open_direct_push(self):
        """Open the direct-push dialog for the defects in this results table."""
        if not self._all_results:
            messagebox.showinfo(
                "Nothing to Push",
                "Run an analysis first — there are no defects in the table.",
                parent=self)
            return
        DirectPushDialog(self, self.app, self._all_results,
                         on_complete=self._refresh_after_push)

    def _refresh_after_push(self):
        """Repaint the tree so push_status colouring (green/red) shows up."""
        self._apply_filters()
        self._update_summary(self._all_results)

    def _show_already_accepted(self):
        if self._sel_idx:
            msg = f"ID {self._sel_idx['cid']} was already accepted"
            reviewer = self._sel_idx.get('accepted_by', 'unknown')
            ts = self._sel_idx.get('accepted_at', '')
            if reviewer and ts:
                msg += f" by {reviewer} at {ts}"
            messagebox.showinfo("Already Accepted", msg + ".")

    def _override(self):
        if not self._sel_idx:
            return
        win = tk.Toplevel(self)
        win.title("Override Disposition")
        win.geometry("460x280")
        win.configure(bg=C_BG)
        win.grab_set()

        tk.Label(win, text="Override Classification",
                 font=("Segoe UI", 13, "bold"), bg=C_BG, fg=C_TEXT).pack(
            pady=(20, 10), padx=20, anchor="w")

        cls_var = tk.StringVar(value=self._sel_idx.get("classification", "Bug"))
        cls_f = tk.Frame(win, bg=C_BG)
        cls_f.pack(fill="x", padx=20, pady=4)
        for val in ["Bug", "False positive", "Intentional", "Needs review"]:
            col = CLASS_COLOR.get(val, C_TEXT)
            tk.Radiobutton(cls_f, text=val, variable=cls_var, value=val,
                           bg=C_BG, fg=col, selectcolor=C_CARD,
                           activebackground=C_BG, activeforeground=col,
                           font=("Segoe UI", 10)).pack(side="left", padx=(0, 14))

        tk.Label(win, text="Comment", font=("Segoe UI", 10, "bold"),
                 bg=C_BG, fg=C_SUBTEXT).pack(anchor="w", padx=20, pady=(12, 2))
        cmt = tk.Text(win, height=4, bg=C_CARD, fg=C_TEXT,
                      insertbackground=C_TEXT, relief="flat",
                      font=("Segoe UI", 10))
        cmt.pack(fill="x", padx=20)
        cmt.insert("end", self._sel_idx.get("comment", ""))

        def _submit():
            classification = cls_var.get()
            comment = cmt.get("1.0", "end-1c").strip() or "Manually overridden"
            self._sel_idx["classification"] = classification
            self._sel_idx["comment"] = comment
            self._sel_idx["accepted"] = False
            # Overrides are a deliberate reviewer decision, so they count as
            # "reviewed" for the Accepted/overridden push selection mode.
            self._sel_idx["overridden"] = True
            self._sel_idx["accepted_by"] = ""
            self._sel_idx["accepted_at"] = ""
            self._save_decision(self._sel_idx, classification, comment, accepted=False)
            win.destroy()
            self._filter(self._filter_var.get())
            self._update_summary(self._all_results)
            messagebox.showinfo("Saved", "Override recorded.\nStatus updated.")

        tk.Button(win, text="Save Override", command=_submit,
                  bg=C_ACCENT, fg="#FFF", relief="flat",
                  font=("Segoe UI", 11, "bold"),
                  padx=18, pady=8, cursor="hand2").pack(pady=16)

    def _save_decision(self, defect, classification, comment, fix="", accepted=False):
        try:
            reviewer = os.getlogin()
        except Exception:
            reviewer = os.environ.get("USERNAME", "unknown")
        out_dir = self.app._frames[SetupPage]._output_var.get().strip()
        if not out_dir or not os.path.isdir(out_dir):
            out_dir = os.path.join(os.path.expanduser("~"), "Documents")
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, "coverity_final_decisions.csv")

        header = ["CID", "Checker", "File", "Line",
                  "FinalClassification", "FinalComment", "Fix",
                  "Reviewer", "Timestamp", "Status", "Category"]

        status = "Accepted" if accepted else "Overridden"
        new_row = {
            "CID": defect.get("cid", ""),
            "Checker": defect.get("checker", ""),
            "File": defect.get("file", ""),
            "Line": defect.get("line", ""),
            "FinalClassification": classification,
            "FinalComment": comment,
            "Fix": defect.get("fix", ""),
            "Reviewer": reviewer,
            "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Status": status,
            "Category": category_for_checker(defect.get("checker", "")),
        }

        # Load any existing rows keyed by CID so we keep exactly ONE decision
        # row per defect. Duplicate/multiple entries for the same CID (which can
        # arise when the same defect is saved from both the results detail panel
        # and the DetailWindow popup, or via repeated actions) collapse to the
        # most recent user action instead of piling up.
        rows = {}
        if os.path.isfile(out_file):
            try:
                with open(out_file, "r", newline="", encoding="utf-8") as f:
                    for r in csv.DictReader(f):
                        cid = str(r.get("CID", "")).strip()
                        if cid:
                            rows[cid] = r
            except Exception:
                rows = {}

        cid_key = str(new_row["CID"]).strip()
        if cid_key:
            rows[cid_key] = new_row
        else:
            # No usable CID (shouldn't happen) — fall back to appending so a
            # decision is never lost.
            with open(out_file, "a", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=header)
                if not os.path.isfile(out_file) or os.path.getsize(out_file) == 0:
                    w.writeheader()
                w.writerow(new_row)
            return

        with open(out_file, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=header)
            w.writeheader()
            for r in rows.values():
                w.writerow(r)



class DetailWindow(tk.Toplevel):
    def __init__(self, parent, defect, app, src_root=""):
        super().__init__(parent)
        self.defect = defect
        self.app    = app
        self.src_root = src_root

        is_accepted = defect.get("accepted", False)
        if is_accepted:
            cls = "Accepted"
            cls_col = C_ACCEPTED
        else:
            cls = defect.get("classification", "Needs review")
            cls_col = CLASS_COLOR.get(cls, C_TEXT)

        self.title(f"ID {defect['cid']}  \u2014  {defect['checker']}  |  {cls}")
        self.geometry("1300x820")
        self.configure(bg=C_BG)
        self.state("zoomed")

        # -- Top bar --
        top = tk.Frame(self, bg=C_HDR_BG, height=54)
        top.pack(fill="x")
        top.pack_propagate(False)

        tk.Label(top,
            text=f"ID {defect['cid']}",
            font=("Segoe UI", 14, "bold"), bg=C_HDR_BG, fg=C_HDR_TEXT
        ).pack(side="left", padx=(20, 6), pady=10)
        tk.Label(top,
            text=defect["checker"],
            font=("Segoe UI", 13), bg=C_HDR_BG, fg="#93C5FD"
        ).pack(side="left", pady=10)

        badge = tk.Label(top, text=f"  {cls}  ",
            font=("Segoe UI", 11, "bold"),
            bg=cls_col, fg="#FFFFFF", padx=6, pady=2)
        badge.pack(side="left", padx=14, pady=12)

        if is_accepted:
            tk.Label(top, text=f"\u2714 Accepted by {defect.get('accepted_by', 'unknown')}",
                font=("Segoe UI", 10), bg=C_HDR_BG, fg="#86EFAC"
            ).pack(side="left", padx=4, pady=12)

        tk.Button(top, text="\u2715  Close", command=self.destroy,
            bg="#374151", fg="#F9FAFB", relief="flat",
            font=("Segoe UI", 10), padx=14, pady=6, cursor="hand2"
        ).pack(side="right", padx=16, pady=10)

        # -- Main paned: left=info, right=code --
        pane = tk.PanedWindow(self, orient="horizontal",
                              bg=C_BORDER, sashwidth=5, relief="flat")
        pane.pack(fill="both", expand=True, padx=0, pady=0)

        # -- Left: metadata + events + actions --
        left = tk.Frame(pane, bg=C_PANEL)
        pane.add(left, minsize=380)

        # Analysis paragraph
        tk.Label(left, text="Analysis",
            font=("Segoe UI", 10, "bold"), bg=C_PANEL, fg=C_TEXT
        ).pack(anchor="w", padx=16, pady=(10, 2))
        cmt_box = tk.Text(left, height=6, bg=C_PANEL, fg=C_TEXT,
            font=("Segoe UI", 9), relief="flat", wrap="word",
            borderwidth=0, highlightthickness=0)
        cmt_box.insert("1.0", defect.get("comment", ""))
        cmt_box.configure(state="disabled")
        cmt_box.bind("<Control-c>",
            lambda e: _copy_selected_text(cmt_box, self.app, "comment"))
        cmt_box.bind("<Control-a>", _select_all_text)
        cmt_box.pack(fill="x", padx=16, pady=(0, 4))

        # Proposed Fix -- Bug only; non-scrollable auto-height box that sizes
        # to fit its wrapped text and uses the remaining width but does not
        # stretch to fill all the free space.
        if not is_accepted and cls in ("Bug", "Needs review"):
            fix_text = defect.get("fix", "")
            if fix_text and fix_text not in ("No fix required.", "Manual review required."):
                tk.Label(left, text="Proposed Fix",
                    font=("Segoe UI", 10, "bold"), bg=C_PANEL, fg=C_ACCENT
                ).pack(anchor="w", padx=16, pady=(6, 2))
                fix_frame = tk.Frame(left, bg="#EFF6FF")
                fix_frame.pack(fill="x", padx=16, pady=(0, 6))
                fix_lbl = tk.Text(fix_frame, height=4, bg="#EFF6FF", fg=C_TEXT,
                    font=("Consolas", 9), relief="flat", wrap="word",
                    borderwidth=0, highlightthickness=0, padx=8, pady=8)
                fix_lbl.insert("1.0", fix_text)
                fix_lbl.configure(state="disabled")
                fix_lbl.bind("<Control-c>",
                    lambda e: _copy_selected_text(fix_lbl, self.app, "proposed fix"))
                fix_lbl.bind("<Control-a>", _select_all_text)
                fix_lbl.pack(fill="x")

        act_f = tk.Frame(left, bg=C_PANEL)
        act_f.pack(fill="x", padx=16, pady=(4, 10))

        def mk(txt, bg, cmd):
            return tk.Button(act_f, text=txt, command=cmd,
                bg=bg, fg="#FFFFFF", disabledforeground="#FFFFFF",
                relief="flat",
                font=("Segoe UI", 10, "bold"), padx=14, pady=8,
                cursor="hand2", activebackground=C_BORDER)

        if is_accepted:
            mk("\u2714  Accepted", C_ACCEPTED, self._show_already_accepted).pack(
                side="left", padx=(0, 8))
        else:
            mk("\u2714  Accept Suggestion", "#16A34A", self._accept).pack(
                side="left", padx=(0, 8))
        mk("\u270E  Override",           "#D97706", self._override).pack(
            side="left")

        # -- Right: source code viewer (VS Code theme) --
        right = tk.Frame(pane, bg="#1E1E1E")
        pane.add(right, minsize=600)

        code_hdr = tk.Frame(right, bg="#252526", height=36)
        code_hdr.pack(fill="x")
        code_hdr.pack_propagate(False)
        tk.Label(code_hdr, text="\U0001f4c4  Source Code",
            font=("Segoe UI", 10, "bold"), bg="#252526", fg="#CCCCCC"
        ).pack(side="left", padx=14, pady=6)
        fname = os.path.basename(defect.get("file", ""))
        tk.Label(code_hdr, text=fname,
            font=("Consolas", 9), bg="#252526", fg="#808080"
        ).pack(side="right", padx=14, pady=6)

        # Source origin banner
        self._src_banner = tk.Label(right, text="",
            font=("Segoe UI", 9, "bold"), bg="#1E1E1E", fg="#FFCC00",
            anchor="w", padx=10, pady=4)
        self._src_banner.pack(fill="x")

        code_box = scrolledtext.ScrolledText(right,
            bg="#1E1E1E", fg="#D4D4D4",
            font=("Consolas", 10), relief="flat", wrap="none",
            insertbackground="#D4D4D4", selectbackground="#264F78")
        code_box.pack(fill="both", expand=True, padx=0, pady=0)
        self._code_box = code_box
        code_box.bind("<Control-c>",
            lambda e: _copy_selected_text(code_box, self.app, "selected source"))
        code_box.bind("<Control-a>", _select_all_text)

        # Tab stops: 4 spaces
        tab_width = 4 * code_box.tk.call("font", "measure", code_box["font"], " ")
        code_box.configure(tabs=(tab_width,))

        # VS Code theme tags
        code_box.tag_configure("lineno", foreground="#858585",
                               font=("Consolas", 9))
        code_box.tag_configure("error_line", background="#5A1D1D")

        code_box.tag_configure("Token.Keyword", foreground="#569CD6")
        code_box.tag_configure("Token.Keyword.Type", foreground="#4EC9B0")
        code_box.tag_configure("Token.String", foreground="#CE9178")
        code_box.tag_configure("Token.Comment", foreground="#6A9955",
                               font=("Consolas", 10, "italic"))
        code_box.tag_configure("Token.Comment.Multiline", foreground="#6A9955",
                               font=("Consolas", 10, "italic"))
        code_box.tag_configure("Token.Comment.Single", foreground="#6A9955",
                               font=("Consolas", 10, "italic"))
        code_box.tag_configure("Token.Preproc", foreground="#C586C0")
        code_box.tag_configure("Token.Number", foreground="#B5CEA8")
        code_box.tag_configure("Token.Name.Function", foreground="#DCDCAA")
        code_box.tag_configure("Token.Name.Variable", foreground="#9CDCFE")
        code_box.tag_configure("Token.Name.Class", foreground="#4EC9B0")
        code_box.tag_configure("Token.Operator", foreground="#D4D4D4")
        code_box.tag_configure("Token.Text", foreground="#D4D4D4")

        # --- Source code: real file first, then embedded fallback ---
        src = ""
        source_origin = "none"
        file_path = defect.get("file", "")
        if file_path:
            search_path = file_path
            if not os.path.isabs(search_path):
                search_path = os.path.join(self.src_root, search_path)

            if os.path.isabs(file_path) and not os.path.isfile(search_path):
                rel_parts = file_path.strip(os.sep).split(os.sep)
                for i in range(len(rel_parts)):
                    tail_path = os.path.join(self.src_root, *rel_parts[i:])
                    if os.path.isfile(tail_path):
                        search_path = tail_path
                        break

            if not os.path.isfile(search_path):
                for root, dirs, files in os.walk(self.src_root):
                    if os.path.basename(file_path) in files:
                        search_path = os.path.join(root, os.path.basename(file_path))
                        break

            if os.path.isfile(search_path):
                try:
                    with open(search_path, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()
                    src = "".join(
                        f"{i+1:>6}  {l}"
                        for i, l in enumerate(lines)
                    )
                    source_origin = "local"
                except Exception:
                    pass

        if not src:
            src = defect.get("source_code", "")
            if src:
                source_origin = "html"

        if not src:
            src = "(No source code available)"
            source_origin = "none"

        error_line = str(defect.get("line", ""))

        if source_origin == "local":
            self._src_banner.configure(text="\u2713 Local source file", fg="#4EC9B0")
        elif source_origin == "html":
            self._src_banner.configure(text="\u26A0 HTML-embedded source (limited accuracy)", fg="#FFCC00")
        else:
            self._src_banner.configure(text="\u2717 No source code available", fg="#F44747")

        self._insert_highlighted_pygments(code_box, src, error_line)
        code_box.configure(state="disabled")

    def _insert_highlighted_pygments(self, widget, text, error_line):
        """Insert source code into a tkinter Text widget using Pygments with VS Code colours."""
        from pygments import lex
        from pygments.lexers import CLexer, CppLexer, AdaLexer
        from pygments.token import Token

        fname = self.defect.get("file", "")
        if fname.endswith((".cpp", ".cxx", ".hpp", ".cc", ".C")):
            lexer = CppLexer()
        elif fname.endswith((".adb", ".ads")):
            lexer = AdaLexer()
        else:
            lexer = CLexer()

        token_map = {
            Token.Keyword:          "Token.Keyword",
            Token.Keyword.Type:     "Token.Keyword.Type",
            Token.String:           "Token.String",
            Token.Comment:          "Token.Comment",
            Token.Comment.Multiline:"Token.Comment.Multiline",
            Token.Comment.Single:   "Token.Comment.Single",
            Token.Preproc:          "Token.Preproc",
            Token.Number:           "Token.Number",
            Token.Name.Function:    "Token.Name.Function",
            Token.Name.Variable:    "Token.Name.Variable",
            Token.Name.Class:       "Token.Name.Class",
            Token.Operator:         "Token.Operator",
            Token.Text:             "Token.Text",
        }

        lines = text.splitlines(keepends=True)
        for line in lines:
            m = re.match(r"^(\s*\d+)(  )(.*)", line)
            if m:
                lno = m.group(1)
                code_part = m.group(3) + "\n"

                widget.insert("end", lno + "  ", "lineno")

                tokens = list(lex(code_part, lexer))
                for ttype, value in tokens:
                    tag = token_map.get(ttype, "Token.Text")
                    widget.insert("end", value, tag)

                if lno.strip() == error_line:
                    line_start = widget.index("end-2l linestart")
                    line_end   = widget.index("end-1l lineend")
                    widget.tag_add("error_line", line_start, line_end)
            else:
                widget.insert("end", line)

        if error_line:
            try:
                idx = f"{int(error_line)}.0"
                widget.see(idx)
                widget.mark_set("insert", idx)
            except Exception:
                pass

    def _show_already_accepted(self):
        msg = f"ID {self.defect['cid']} was already accepted"
        reviewer = self.defect.get('accepted_by', 'unknown')
        ts = self.defect.get('accepted_at', '')
        if reviewer and ts:
            msg += f" by {reviewer} at {ts}"
        messagebox.showinfo("Already Accepted", msg + ".", parent=self)

    def _accept(self):
        if self.defect.get("accepted", False):
            messagebox.showinfo("Already Accepted", "This defect has already been accepted.", parent=self)
            return

        self.defect["accepted"] = True
        try:
            self.defect["accepted_by"] = os.getlogin()
        except Exception:
            self.defect["accepted_by"] = os.environ.get("USERNAME", "unknown")
        self.defect["accepted_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        rp = self.app._frames[ResultsPage]
        rp._save_decision(
            self.defect,
            self.defect.get("classification", "Needs review"),
            self.defect.get("comment", ""),
            self.defect.get("fix", ""),
            accepted=True)

        saved_cid = self.defect["cid"]
        rp._filter(rp._filter_var.get())
        rp._update_summary(rp._all_results)
        for child in rp._tree.get_children():
            if rp._tree.item(child)["values"][0] == saved_cid:
                rp._tree.selection_set(child)
                rp._tree.see(child)
                break
        rp._on_select()

        messagebox.showinfo("Saved", "Decision accepted.\nStatus updated to 'Accepted'.", parent=self)
        self.destroy()

    def _override(self):
        win = tk.Toplevel(self)
        win.title("Override Disposition")
        win.geometry("480x240")
        win.configure(bg=C_BG)
        win.grab_set()

        tk.Label(win, text="Classification",
            font=("Segoe UI", 11, "bold"), bg=C_BG, fg=C_TEXT
        ).pack(anchor="w", padx=20, pady=(18, 4))

        cls_var = tk.StringVar(value=self.defect.get("classification", "Bug"))
        cls_f = tk.Frame(win, bg=C_BG)
        cls_f.pack(fill="x", padx=20, pady=4)
        for val in ["Bug", "False positive", "Intentional", "Needs review"]:
            col = CLASS_COLOR.get(val, C_TEXT)
            tk.Radiobutton(cls_f, text=val, variable=cls_var, value=val,
                bg=C_BG, fg=col, selectcolor=C_CARD,
                activebackground=C_BG, font=("Segoe UI", 10)
            ).pack(side="left", padx=(0, 14))

        tk.Label(win, text="Comment",
            font=("Segoe UI", 11, "bold"), bg=C_BG, fg=C_TEXT
        ).pack(anchor="w", padx=20, pady=(12, 4))

        cmt = tk.Text(win, height=3, bg="#FFFFFF", fg=C_TEXT,
                      insertbackground=C_TEXT, relief="flat",
                      font=("Segoe UI", 10), borderwidth=1,
                      highlightthickness=1, highlightbackground=C_BORDER)
        cmt.pack(fill="x", padx=20)
        cmt.insert("end", self.defect.get("comment", ""))

        def _submit():
            c = cls_var.get()
            cm = cmt.get("1.0", "end-1c").strip() or "Manually overridden"

            self.defect["classification"] = c
            self.defect["comment"]        = cm
            self.defect["accepted"]       = False
            self.defect["accepted_by"]    = ""
            self.defect["accepted_at"]    = ""

            self.app._frames[ResultsPage]._save_decision(self.defect, c, cm, self.defect.get("fix", ""), accepted=False)
            win.destroy()
            self.destroy()
            self.app._frames[ResultsPage]._filter(self.app._frames[ResultsPage]._filter_var.get())
            self.app._frames[ResultsPage]._update_summary(self.app._frames[ResultsPage]._all_results)
            messagebox.showinfo("Saved", "Override recorded.\nStatus updated.")

        tk.Button(win, text="Save Override", command=_submit,
            bg=C_ACCENT, fg="#FFFFFF", relief="flat",
            font=("Segoe UI", 11, "bold"), padx=18, pady=8, cursor="hand2"
        ).pack(pady=14)


# ---------------------------------------------------------------------------
# Stand-alone Pull Dialog — pull defects directly from the Coverity Connect
# server (SOAP v9), bypassing the broken CSV export that reports "Various" line
# numbers, and save a structured Excel file that the parser understands.
# ---------------------------------------------------------------------------
class PullDialog(tk.Toplevel):
    """Pull defects from Coverity Connect into a structured Excel file."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app               = app
        self.result_excel_path = None   # set on success, read by SetupPage
        self._client           = None
        self._projects         = []     # list of {name, triage_store}
        self._project_streams  = []     # list of stream name strings
        self._q                = queue.Queue()
        self._pulling          = False

        self.title("Pull Defects from Coverity Connect")
        self.geometry("860x780")
        self.minsize(700, 620)
        self.configure(bg=C_BG)
        self.grab_set()
        self.resizable(True, True)

        out_default = os.path.join(os.path.expanduser("~"), "Documents")
        try:
            out_var = app._frames[SetupPage]._output_var.get().strip()
            if out_var:
                out_default = out_var
        except Exception:
            pass

        self._sv_host    = tk.StringVar(value="coverity-er.honaero.com")
        self._sv_port    = tk.StringVar(value="443")
        self._sv_user    = tk.StringVar()
        self._sv_pass    = tk.StringVar()
        self._sv_project = tk.StringVar()
        self._sv_stream  = tk.StringVar()
        self._sv_limit   = tk.StringVar(value="5000")
        self._sv_save    = tk.StringVar()
        self._sv_use_rest = tk.BooleanVar(value=True)  # fix current lines via Connect REST API
        self._sv_insecure = tk.BooleanVar(value=True)  # allow self-signed cert (verify off) — default True for corp compatibility
        self._set_save_path("", out_default)

        self._build()

    # ------------------------------------------------------------------ build
    def _build(self):
        canvas = tk.Canvas(self, bg=C_BG, highlightthickness=0)
        scroll = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        body = tk.Frame(canvas, bg=C_BG)
        win_id = canvas.create_window((0, 0), window=body, anchor="nw")

        def _on_resize(e):
            canvas.itemconfig(win_id, width=e.width)
        canvas.bind("<Configure>", _on_resize)
        body.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))

        # ── Title ──────────────────────────────────────────────────────
        tk.Label(body, text="⬇  Pull Defects from Coverity Connect",
                 font=("Segoe UI", 13, "bold"), bg=C_BG, fg=C_ACCENT
                 ).pack(anchor="w", padx=20, pady=(16, 4))
        tk.Label(body,
                 text="Fetch defects straight from the server (real line numbers,\n"
                      "no 'Various' entries) and save them as a structured Excel file.",
                 font=("Segoe UI", 9), bg=C_BG, fg=C_SUBTEXT, justify="left"
                 ).pack(anchor="w", padx=20, pady=(0, 12))

        # ── Section 1 — Server Connection ──────────────────────────────
        self._section(body, "Section 1 — Server Connection")
        s1 = self._card(body)

        def _conn_row(parent, label, var, show=""):
            f = tk.Frame(parent, bg=C_PANEL)
            f.pack(fill="x", padx=10, pady=3)
            tk.Label(f, text=label, width=10, anchor="w",
                     font=("Segoe UI", 9, "bold"), bg=C_PANEL, fg=C_SUBTEXT
                     ).pack(side="left")
            tk.Entry(f, textvariable=var, width=34, show=show,
                     bg="#FFFFFF", fg=C_TEXT, insertbackground=C_TEXT,
                     relief="flat", font=("Segoe UI", 10)
                     ).pack(side="left", fill="x", expand=True, padx=(0, 6))
            return f

        _conn_row(s1, "Host", self._sv_host)
        _conn_row(s1, "Port", self._sv_port)
        _conn_row(s1, "Username", self._sv_user)
        _conn_row(s1, "Password", self._sv_pass, show="*")
        # SSL verification toggle — secure default is unchecked (verify on); corp self-signed needs checked
        sec_f = tk.Frame(s1, bg=C_PANEL)
        sec_f.pack(fill="x", padx=10, pady=2)
        tk.Checkbutton(sec_f, text="Allow self-signed certificate (insecure — verify off)",
                       variable=self._sv_insecure, onvalue=True, offvalue=False,
                       bg=C_PANEL, fg=C_INTENT, selectcolor=C_CARD,
                       activebackground=C_PANEL, font=("Segoe UI", 8, "bold"), cursor="hand2").pack(side="left")
        tk.Label(sec_f, text="  (uncheck for production with valid cert)", font=("Segoe UI", 7), bg=C_PANEL, fg=C_SUBTEXT).pack(side="left", padx=4)

        tst_f = tk.Frame(s1, bg=C_PANEL)
        tst_f.pack(fill="x", padx=10, pady=(6, 10))
        self._test_btn = tk.Button(
            tst_f, text="Test Connection", command=self._test_connection,
            bg=C_CARD, fg=C_ACCENT, relief="flat",
            font=("Segoe UI", 9, "bold"), padx=10, pady=5, cursor="hand2",
            activebackground=C_BORDER)
        self._test_btn.pack(side="left")
        self._conn_lbl = tk.Label(tst_f, text="Not connected",
                                  font=("Segoe UI", 9), bg=C_PANEL, fg=C_SUBTEXT)
        self._conn_lbl.pack(side="left", padx=12)

        

        # ── Section 2 — Project & Stream ───────────────────────────────
        self._section(body, "Section 2 — Project & Stream")
        s2 = self._card(body)

        p_f = tk.Frame(s2, bg=C_PANEL)
        p_f.pack(fill="x", padx=10, pady=3)
        tk.Label(p_f, text="Project", width=10, anchor="w",
                 font=("Segoe UI", 9, "bold"), bg=C_PANEL, fg=C_SUBTEXT
                 ).pack(side="left")
        self._proj_cb = ttk.Combobox(p_f, textvariable=self._sv_project,
                                     state="disabled", values=[])
        self._proj_cb.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._proj_cb.bind("<<ComboboxSelected>>", self._on_project_select)

        st_f = tk.Frame(s2, bg=C_PANEL)
        st_f.pack(fill="x", padx=10, pady=3)
        tk.Label(st_f, text="Stream", width=10, anchor="w",
                 font=("Segoe UI", 9, "bold"), bg=C_PANEL, fg=C_SUBTEXT
                 ).pack(side="left")
        self._stream_cb = ttk.Combobox(st_f, textvariable=self._sv_stream,
                                       state="disabled", values=[])
        self._stream_cb.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._stream_cb.bind("<<ComboboxSelected>>", self._on_stream_select)

        lim_f = tk.Frame(s2, bg=C_PANEL)
        lim_f.pack(fill="x", padx=10, pady=3)
        tk.Label(lim_f, text="Defect limit", width=10, anchor="w",
                 font=("Segoe UI", 9, "bold"), bg=C_PANEL, fg=C_SUBTEXT
                 ).pack(side="left")
        self._limit_spin = ttk.Spinbox(lim_f, from_=100, to=50000, increment=100,
                                       textvariable=self._sv_limit, width=12)
        self._limit_spin.pack(side="left")

        # ── Section 3 — Output File ────────────────────────────────────
        self._section(body, "Section 3 — Output File")
        s3 = self._card(body)

        o_f = tk.Frame(s3, bg=C_PANEL)
        o_f.pack(fill="x", padx=10, pady=3)
        tk.Label(o_f, text="Save path", width=10, anchor="w",
                 font=("Segoe UI", 9, "bold"), bg=C_PANEL, fg=C_SUBTEXT
                 ).pack(side="left")
        tk.Entry(o_f, textvariable=self._sv_save, width=34,
                 bg="#FFFFFF", fg=C_TEXT, insertbackground=C_TEXT,
                 relief="flat", font=("Segoe UI", 9)
                 ).pack(side="left", fill="x", expand=True, padx=(0, 6))
        tk.Button(o_f, text="Browse…", command=self._browse_save,
                  bg=C_CARD, fg=C_ACCENT, relief="flat",
                  font=("Segoe UI", 9, "bold"), padx=8, pady=4,
                  cursor="hand2", activebackground=C_BORDER
                  ).pack(side="left")

        

        # ── Section 4 — Pull button, progress & log ────────────────────
        self._section(body, "Section 4 — Pull Defects")
        pull_f = tk.Frame(body, bg=C_BG)
        pull_f.pack(fill="x", padx=20, pady=(6, 2))
        self._pull_btn = tk.Button(
            pull_f, text="⬇  Pull Defects", command=self._pull,
            bg=C_ACCENT, fg="#FFFFFF", relief="flat",
            font=("Segoe UI", 11, "bold"), padx=18, pady=6,
            cursor="hand2", activebackground=C_ACCENT2,
            state="disabled")
        self._pull_btn.pack(side="left")
        self._close_btn = tk.Button(
            pull_f, text="Close", command=self._close_dialog,
            bg=C_CARD, fg=C_TEXT, relief="flat",
            font=("Segoe UI", 10), padx=14, pady=6,
            cursor="hand2", state="normal")
        self._close_btn.pack(side="left", padx=(10, 0))

        self._use_rest_chk = tk.Checkbutton(
            pull_f, text="Fix current lines via Connect REST API",
            variable=self._sv_use_rest, onvalue=True, offvalue=False,
            bg=C_BG, fg=C_SUBTEXT, selectcolor=C_CARD,
            activebackground=C_BG, activeforeground=C_TEXT,
            font=("Segoe UI", 9), relief="flat", bd=0, cursor="hand2")
        self._use_rest_chk.pack(side="left", padx=(14, 0))
        self._test_rest_btn = tk.Button(
            pull_f, text="Test REST", command=self._test_rest,
            bg=C_CARD, fg=C_ACCENT, relief="flat",
            font=("Segoe UI", 9, "bold"), padx=10, pady=4,
            cursor="hand2", activebackground=C_BORDER,
            state="disabled")
        self._test_rest_btn.pack(side="left", padx=(6, 0))

        self._prog = ttk.Progressbar(body, mode="determinate", maximum=100)
        self._prog.pack(fill="x", padx=20, pady=(6, 2))

        log_f = tk.Frame(body, bg=C_BG)
        log_f.pack(fill="x", padx=20, pady=(6, 4))
        self._log = tk.Text(log_f, height=5, state="disabled",
                            bg="#0B1220", fg="#E2E8F0", relief="flat",
                            wrap="word", font=("Consolas", 9),
                            insertbackground=C_TEXT)
        vsb = ttk.Scrollbar(log_f, orient="vertical", command=self._log.yview)
        self._log.configure(yscrollcommand=vsb.set)
        self._log.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self._log.tag_configure("ok",    foreground="#22C55E")
        self._log.tag_configure("warn",  foreground="#EAB308")
        self._log.tag_configure("error", foreground="#EF4444")
        self._log.tag_configure("info",  foreground="#E2E8F0")

        # ── Footer ─────────────────────────────────────────────────────
        foot = tk.Frame(body, bg=C_BG)
        foot.pack(fill="x", padx=20, pady=(8, 20))
        tk.Button(foot, text="Close", command=self.destroy,
                  bg=C_CARD, fg=C_TEXT, relief="flat",
                  font=("Segoe UI", 10), padx=14, pady=6,
                  cursor="hand2").pack(side="left")

        self._log_insert("info", "Enter server details and click Test Connection.\n")

        

    # ------------------------------------------------------------------ helpers
    def _section(self, parent, title):
        f = tk.Frame(parent, bg=C_BG)
        f.pack(fill="x", padx=20, pady=(10, 2))
        tk.Label(f, text=title, font=("Segoe UI", 10, "bold"),
                 bg=C_BG, fg=C_TEXT).pack(side="left")
        tk.Frame(f, bg=C_BORDER, height=1).pack(
            side="left", fill="x", expand=True, padx=(8, 0), pady=5)

    def _card(self, parent):
        f = tk.Frame(parent, bg=C_PANEL,
                     highlightbackground=C_BORDER, highlightthickness=1)
        f.pack(fill="x", padx=20, pady=2)
        return f

    def _log_insert(self, tag, text):
        self._log.configure(state="normal")
        self._log.insert("end", text, tag)
        self._log.see("end")
        self._log.configure(state="disabled")

    def _set_save_path(self, stream, out_default=None):
        folder = out_default or self._sv_save.get().strip()
        if not folder:
            try:
                folder = self.app._frames[SetupPage]._output_var.get().strip()
            except Exception:
                folder = ""
        if not folder or not os.path.isdir(folder):
            folder = os.path.join(os.path.expanduser("~"), "Documents")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if stream:
            safe = re.sub(r"[^\w\-]", "_", stream)
            name = f"coverity_pull_{safe}_{stamp}.xlsx"
        else:
            name = f"coverity_pull_{stamp}.xlsx"
        self._sv_save.set(os.path.join(folder, name))

    # ------------------------------------------------------------------ logic
    def _test_connection(self):
        host = self._sv_host.get().strip()
        port = self._sv_port.get().strip()
        user = self._sv_user.get().strip()
        pw   = self._sv_pass.get()
        if not host or not port or not user or not pw:
            self._conn_lbl.configure(
                text="Fill in Host, Port, Username and Password", fg=C_INTENT)
            self._log_insert("warn", "Fill in Host, Port, Username and Password.\n")
            return
        if not zeep_available():
            self._conn_lbl.configure(
                text="zeep not installed — run: pip install zeep", fg=C_BUG)
            self._log_insert("error", "zeep not installed — run: pip install zeep\n")
            return
        self._conn_lbl.configure(text="Testing…", fg=C_SUBTEXT)
        self._test_btn.configure(state="disabled")
        self._proj_cb.configure(state="disabled", values=[])
        self._stream_cb.configure(state="disabled", values=[])
        self._pull_btn.configure(state="disabled")
        self._log_insert("warn", "Testing connection…\n")

        def _worker():
            # Allow optional pre-supplied REST token / API key via env vars
            rest_tok = os.environ.get("COVERITY_REST_TOKEN")
            rest_key = os.environ.get("COVERITY_API_KEY")
            verify = not self._sv_insecure.get()
            client = CoveritySOAPClient(host, port, user, pw,
                verify_ssl=verify, rest_token=rest_tok, api_key=rest_key)
            ok, msg = client.test_connection()

            def _done():
                self._test_btn.configure(state="normal")
                if ok:
                    self._client = client
                    self._test_rest_btn.configure(state="normal")
                    self._load_projects()
                else:
                    self._conn_lbl.configure(text=f"✗ {msg}", fg=C_BUG)
                    self._log_insert("error", f"✗ {msg}\n")
            self.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

        

    def _load_projects(self):
        self._conn_lbl.configure(text="Loading projects…", fg=C_SUBTEXT)

        def _worker():
            projects = self._client.get_projects()

            def _done():
                self._projects = projects
                names = [p["name"] for p in projects]
                self._proj_cb.configure(
                    values=names, state="readonly" if names else "disabled")
                if names:
                    self._proj_cb.current(0)
                    self._sv_project.set(names[0])
                    self._on_project_select()
                count = len(names)
                self._conn_lbl.configure(
                    text=f"✓ Connected  ({count} project{'s' if count != 1 else ''} found)",
                    fg=C_FP)
                self._log_insert("ok", f"✓ Connected — {count} project(s) found.\n")
            self.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_project_select(self, _event=None):
        proj = self._sv_project.get()
        if not proj:
            return
        self._stream_cb.configure(state="disabled", values=[])
        self._sv_stream.set("")
        self._pull_btn.configure(state="disabled")

        def _worker():
            streams = self._client.get_streams_for_project(proj)

            def _done():
                self._project_streams = streams
                values = [self._client.ALL_STREAMS] + streams
                self._stream_cb.configure(
                    values=values, state="readonly" if streams else "disabled")
                if streams:
                    self._sv_stream.set(values[0])
                    self._refresh_pull_btn()
                    self._update_save_path()
            self.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_stream_select(self, _event=None):
        self._update_save_path()
        self._refresh_pull_btn()

    def _update_save_path(self):
        stream = self._sv_stream.get()
        self._set_save_path("" if stream == self._client.ALL_STREAMS else stream)

    def _browse_save(self):
        p = filedialog.asksaveasfilename(
            title="Save Coverity Pull as Excel",
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
            initialfile=os.path.basename(self._sv_save.get() or "coverity_pull.xlsx"))
        if p:
            self._sv_save.set(p)

    def _refresh_pull_btn(self):
        if self._sv_stream.get() and not self._pulling:
            self._pull_btn.configure(state="normal")
        else:
            self._pull_btn.configure(state="disabled")

    def _test_rest(self):
        """Probe candidate REST API bases and report what the server exposes."""
        if not self._client:
            self._log_insert("error", "Connect to the server first.\n")
            return
        self._log_insert("warn", "Probing REST API endpoints (may take a moment)…\n")

        def _worker():
            try:
                v1, v2, info = self._client.discover_rest_base()
                epath, emethod, elog = self._client._probe_issue_endpoint(self._sv_stream.get())
                found = bool(v1 or v2)
                ep = (f"  defect endpoint: /api/v2/{epath} via {emethod}\n"
                      if epath and emethod else "  (no defect endpoint auto-detected)\n")
                detail = f"{info}\n  {elog}\n"
                msg = (f"✓ REST API found — v1={v1 or '-'}  v2={v2 or '-'}\n{ep}"
                       if found else "✗ No REST endpoint responded.\n")
                self.after(0, lambda: self._log_insert(
                    "ok" if found else "error", msg + f"    {detail}\n"))
            except Exception as exc:
                self.after(0, lambda exc=exc: self._log_insert(
                    "error", f"REST probe error: {exc}\n"))

        threading.Thread(target=_worker, daemon=True).start()

        

    # ------------------------------------------------------------------ pulling
    def _pull(self):
        if self._pulling:
            return
        stream = self._sv_stream.get()
        if not stream:
            return
        self._pulling = True
        self._pull_btn.configure(state="disabled", text="Pulling…")
        self._prog.configure(value=0)

        limit = 5000
        try:
            limit = int(self._sv_limit.get())
        except (ValueError, TypeError):
            pass
        limit = max(100, min(limit, 50000))
        project = self._sv_project.get()
        out_path = self._sv_save.get().strip()

        def _worker():
            self._q.put(("info", f"Connecting to stream '{stream}'…\n"))
            self._q.put(("tick", 5, "Fetching defects…\n"))

            def _tick(pct, text):
                if pct == -1:
                    self._q.put(("warn", text + "\n"))
                else:
                    self._q.put(("tick", pct, text + "\n"))

            try:
                defects, err = self._client.get_defects_with_events(
                    stream, max_defects=limit, project_name=project,
                    progress_cb=_tick)
            except Exception as e:
                self._q.put(("error", str(e) + "\n"))
                self._q.put(("done", None))
                return

            if err and not defects:
                self._q.put(("error", err + "\n"))
                self._q.put(("done", None))
                return

            with_line   = sum(1 for d in defects if d.get("line", 0))
            with_events = sum(1 for d in defects if d.get("events"))
            summary = (f"Line numbers resolved: {with_line}/{len(defects)}  |  "
                       f"Events fetched: {with_events}/{len(defects)}")
            self._q.put(("tick", 90, f"Fetched {len(defects)} defects. Writing Excel…\n"))
            self._q.put(("info", f"  {summary}\n"))

            # Optional: overlay the defect's CURRENT line from the Connect REST
            # API (the web UI's authoritative line, e.g. after the code moved).
            if self._sv_use_rest.get():
                try:
                    from coverity_rest_client import CoverityRESTClient, apply_rest_lines
                    verify_rest = not self._sv_insecure.get()
                    rc = CoverityRESTClient(
                        self._sv_host.get().strip(), self._sv_port.get().strip(),
                        self._sv_user.get().strip(), self._sv_pass.get(),
                        verify_ssl=verify_rest,
                        auth_token=os.environ.get("COVERITY_REST_TOKEN"))
                    ok, msg = rc.login()
                    if ok:
                        if stream != self._client.ALL_STREAMS:
                            streams_for_rest = [stream]
                        else:
                            streams_for_rest = (self._client.get_streams_for_project(project)
                                                or [stream])
                        cid_map = {}
                        for st in streams_for_rest:
                            cid_map.update(rc.fetch_defect_lines(st, limit=limit))
                        rest_fixed = apply_rest_lines(defects, cid_map)
                        self._q.put(("info",
                                     f"REST current-line correction: {rest_fixed}/{len(defects)} "
                                     f"lines updated.\n"))
                    else:
                        self._q.put(("warn",
                                     f"REST API unavailable ({msg}) — keeping SOAP line numbers.\n"))
                    rc.close()
                except Exception as exc:
                    self._q.put(("warn", f"REST line correction skipped: {exc}\n"))

            # Write a plain-text log alongside the Excel for post-pull diagnosis.
            log_path = out_path.replace(".xlsx", "_pull_log.txt")
            try:
                import datetime as _dt
                with open(log_path, "w", encoding="utf-8") as _lf:
                    _lf.write(f"Pull log — {_dt.datetime.now()}\n")
                    _lf.write(f"Stream : {stream}\n")
                    _lf.write(f"Defects: {len(defects)}\n")
                    _lf.write(f"{summary}\n\n")
                    # Dump raw SOAP field values for the first defect only.
                    first = defects[0] if defects else {}
                    sd_probe   = first.get("_sd_probe", {})
                    inst_probe = first.get("_inst_probe", {})
                    if sd_probe:
                        _lf.write("\nSOAP streamDefectDataObj fields (first CID):\n")
                        for k, v in sorted(sd_probe.items()):
                            _lf.write(f"  sd.{k} = {v!r}\n")
                    if inst_probe:
                        _lf.write("\nSOAP defectInstanceDataObj fields (first CID):\n")
                        for k, v in sorted(inst_probe.items()):
                            _lf.write(f"  inst.{k} = {v!r}\n")
                    if sd_probe or inst_probe:
                        _lf.write("\n")

                    for d in defects:
                        _lf.write(
                            f"  CID={d['cid']} FINAL={d.get('line',0)} "
                            f"merged={d.get('_merged_line','?')} "
                            f"inst={d.get('_inst_line_val','?')} "
                            f"main_ev={d.get('_main_event_line','?')} "
                            f"last_ev={d.get('_last_event_line','?')} "
                            f"n_inst={d.get('_n_instances','?')} "
                            f"n_ev={len(d.get('events',[]))}\n"
                        )
                        for ev in d.get("events", [])[:5]:
                            _lf.write(f"      ev step={ev.get('step')} "
                                      f"main={ev.get('main')} "
                                      f"line={ev.get('line')} "
                                      f"tag={ev.get('type') or ev.get('tag')}\n")
            except Exception:
                pass

            try:
                write_pull_excel(defects, out_path)
            except Exception as e:
                self._q.put(("error", str(e) + "\n"))
                self._q.put(("done", None))
                return

            self._q.put(("ok", f"Saved : {out_path}\n"))
            self._q.put(("ok", f"Log   : {log_path}\n"))
            self._q.put(("tick", 100, f"Done — {len(defects)} defects. Read log above then close.\n"))
            self._q.put(("done", out_path))

        threading.Thread(target=_worker, daemon=True).start()
        self.after(50, self._poll_queue)

    def _poll_queue(self):
        try:
            while True:
                msg = self._q.get_nowait()
                kind = msg[0]
                if kind == "info":
                    self._log_insert("info", msg[1])
                elif kind == "ok":
                    self._log_insert("ok", msg[1])
                elif kind == "warn":
                    self._log_insert("warn", msg[1])
                elif kind == "error":
                    self._log_insert("error", msg[1])
                elif kind == "tick":
                    self._prog.configure(value=msg[1])
                    self._log_insert("info", msg[2])
                elif kind == "done":
                    self._on_pull_done(msg[1])
                    return
        except queue.Empty:
            pass
        self.after(50, self._poll_queue)

    def _close_dialog(self):
        self.destroy()

    def _on_pull_done(self, path):
        self._pulling = False
        self._pull_btn.configure(state="normal", text="⬇  Pull Defects")
        if path is None:
            self._log_insert("error", "Pull failed — check the messages above.\n")
            return
        self.result_excel_path = path
        # Keep dialog open so the user can read the full log before closing.
        if hasattr(self, "_close_btn"):
            self._close_btn.configure(state="normal")
        self._log_insert("ok",
            "\nPull complete — review the log above, then click Close.\n")
# ---------------------------------------------------------------------------
# Stand-alone Push Dialog — accessible from the main header at any time
# ---------------------------------------------------------------------------
class PushDialog(tk.Toplevel):
    """
    Three-step dialog: Connect → Select Project → Load CSV → Push.
    Can be opened without running a fresh analysis (uses any existing CSV).
    """
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app          = app
        self._client      = None
        self._projects    = []       # list of {name, triage_store}
        self._streams     = []
        self._csv_rows    = []       # parsed rows from chosen CSV

        self.title("Push Dispositions to Coverity Connect")
        self.geometry("860x820")
        self.minsize(700, 660)
        self.configure(bg=C_BG)
        self.grab_set()
        self.resizable(True, True)

        # StringVars — pre-fill from Results page settings if available.
        # Host/Port come pre-filled with the corporate server details and can
        # be overwritten by the user.
        rp = app._frames.get(ResultsPage)
        self._sv_host    = tk.StringVar(value="coverity-er.honaero.com")
        self._sv_port    = tk.StringVar(value="443")
        self._sv_user    = tk.StringVar(value=rp._sv_user.get()    if rp else "")
        self._sv_pass    = tk.StringVar(value=rp._sv_pass.get()    if rp else "")
        self._sv_project = tk.StringVar()
        self._sv_stream  = tk.StringVar()
        self._sv_store   = tk.StringVar(value=rp._sv_store.get()   if rp else "Default")
        self._sv_csv     = tk.StringVar()
        self._sv_insecure = tk.BooleanVar(value=True)  # allow self-signed cert

        self._build()

    # ------------------------------------------------------------------ build
    def _build(self):
        canvas = tk.Canvas(self, bg=C_BG, highlightthickness=0)
        scroll = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        body = tk.Frame(canvas, bg=C_BG)
        win_id = canvas.create_window((0, 0), window=body, anchor="nw")

        def _on_resize(e):
            canvas.itemconfig(win_id, width=e.width)
        canvas.bind("<Configure>", _on_resize)
        body.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))

        # ── Title ──────────────────────────────────────────────────────
        tk.Label(body, text="⬆  Push Dispositions to Coverity Connect",
                 font=("Segoe UI", 13, "bold"), bg=C_BG, fg=C_ACCENT
                 ).pack(anchor="w", padx=20, pady=(16, 4))
        tk.Label(body,
                 text="Connect to the server, select your project, load the dispositions\n"
                      "CSV, then push — no need to re-run the analysis.",
                 font=("Segoe UI", 9), bg=C_BG, fg=C_SUBTEXT, justify="left"
                 ).pack(anchor="w", padx=20, pady=(0, 12))

        # ── Step 1 — Server ────────────────────────────────────────────
        self._section(body, "Step 1 — Server Connection")
        s1 = self._card(body)

        def _row(parent, label, var, width=22, show="", hint=""):
            f = tk.Frame(parent, bg=C_PANEL)
            f.pack(fill="x", padx=10, pady=3)
            tk.Label(f, text=label, width=10, anchor="w",
                     font=("Segoe UI", 9, "bold"), bg=C_PANEL, fg=C_SUBTEXT
                     ).pack(side="left")
            e = tk.Entry(f, textvariable=var, width=width, show=show,
                         bg="#FFFFFF", fg=C_TEXT, insertbackground=C_TEXT,
                         relief="flat", font=("Segoe UI", 9),
                         highlightbackground=C_BORDER, highlightthickness=1)
            e.pack(side="left", ipady=4, padx=(0, 6))
            if hint:
                tk.Label(f, text=hint, font=("Segoe UI", 8), bg=C_PANEL,
                         fg="#94A3B8").pack(side="left")
            return e

        hf = tk.Frame(s1, bg=C_PANEL)
        hf.pack(fill="x", padx=10, pady=3)
        tk.Label(hf, text="Host", width=10, anchor="w",
                 font=("Segoe UI", 9, "bold"), bg=C_PANEL, fg=C_SUBTEXT
                 ).pack(side="left")
        tk.Entry(hf, textvariable=self._sv_host, width=28,
                 bg="#FFFFFF", fg=C_TEXT, insertbackground=C_TEXT,
                 relief="flat", font=("Segoe UI", 9),
                 highlightbackground=C_BORDER, highlightthickness=1
                 ).pack(side="left", ipady=4, padx=(0, 6))

        pf = tk.Frame(s1, bg=C_PANEL)
        pf.pack(fill="x", padx=10, pady=3)
        tk.Label(pf, text="Port", width=10, anchor="w",
                 font=("Segoe UI", 9, "bold"), bg=C_PANEL, fg=C_SUBTEXT
                 ).pack(side="left")
        tk.Entry(pf, textvariable=self._sv_port, width=7,
                 bg="#FFFFFF", fg=C_TEXT, insertbackground=C_TEXT,
                 relief="flat", font=("Segoe UI", 9),
                 highlightbackground=C_BORDER, highlightthickness=1
                 ).pack(side="left", ipady=4, padx=(0, 6))

        _row(s1, "Username", self._sv_user, 18)
        _row(s1, "Password", self._sv_pass, 18, show="*")
        sec_f = tk.Frame(s1, bg=C_PANEL)
        sec_f.pack(fill="x", padx=10, pady=2)
        tk.Checkbutton(sec_f, text="Allow self-signed certificate (insecure — verify off)",
                       variable=self._sv_insecure, onvalue=True, offvalue=False,
                       bg=C_PANEL, fg=C_INTENT, selectcolor=C_CARD,
                       activebackground=C_PANEL, font=("Segoe UI", 8, "bold"), cursor="hand2").pack(side="left")
        tk.Label(sec_f, text="  (uncheck for production with valid cert)", font=("Segoe UI", 7), bg=C_PANEL, fg=C_SUBTEXT).pack(side="left", padx=4)

        conn_f = tk.Frame(s1, bg=C_PANEL)
        conn_f.pack(fill="x", padx=10, pady=(2, 8))
        self._test_btn = tk.Button(
            conn_f, text="Test Connection", command=self._test_connection,
            bg=C_CARD, fg=C_ACCENT, relief="flat",
            font=("Segoe UI", 9, "bold"), padx=10, pady=5, cursor="hand2",
            activebackground=C_BORDER)
        self._test_btn.pack(side="left", padx=(0, 10))
        self._conn_lbl = tk.Label(conn_f, text="",
                                  font=("Segoe UI", 9, "bold"),
                                  bg=C_PANEL, fg=C_SUBTEXT)
        self._conn_lbl.pack(side="left")

        # ── Step 2 — Project & Stream ───────────────────────────────────
        self._section(body, "Step 2 — Select Project & Stream")
        s2 = self._card(body)

        pj_f = tk.Frame(s2, bg=C_PANEL)
        pj_f.pack(fill="x", padx=10, pady=4)
        tk.Label(pj_f, text="Project", width=10, anchor="w",
                 font=("Segoe UI", 9, "bold"), bg=C_PANEL, fg=C_SUBTEXT
                 ).pack(side="left")
        self._proj_cb = ttk.Combobox(pj_f, textvariable=self._sv_project,
                                     state="disabled", width=30,
                                     font=("Segoe UI", 9))
        self._proj_cb.pack(side="left", padx=(0, 8))
        self._proj_cb.bind("<<ComboboxSelected>>", self._on_project_selected)
        tk.Label(pj_f, text="← populated after Test Connection",
                 font=("Segoe UI", 8), bg=C_PANEL, fg="#94A3B8"
                 ).pack(side="left")

        st_f = tk.Frame(s2, bg=C_PANEL)
        st_f.pack(fill="x", padx=10, pady=4)
        tk.Label(st_f, text="Stream", width=10, anchor="w",
                 font=("Segoe UI", 9, "bold"), bg=C_PANEL, fg=C_SUBTEXT
                 ).pack(side="left")
        self._stream_cb = ttk.Combobox(st_f, textvariable=self._sv_stream,
                                       state="disabled", width=30,
                                       font=("Segoe UI", 9))
        self._stream_cb.pack(side="left", padx=(0, 8))
        tk.Label(st_f, text="← populated after selecting a project",
                 font=("Segoe UI", 8), bg=C_PANEL, fg="#94A3B8"
                 ).pack(side="left")

        ts_f = tk.Frame(s2, bg=C_PANEL)
        ts_f.pack(fill="x", padx=10, pady=(4, 8))
        tk.Label(ts_f, text="Triage Store", width=10, anchor="w",
                 font=("Segoe UI", 9, "bold"), bg=C_PANEL, fg=C_SUBTEXT
                 ).pack(side="left")
        self._store_cb = ttk.Combobox(ts_f, textvariable=self._sv_store,
                                      state="disabled", width=28,
                                      font=("Segoe UI", 9))
        self._store_cb.pack(side="left", padx=(0, 8))
        tk.Label(ts_f, text="← auto-filled from project; edit if needed",
                 font=("Segoe UI", 8), bg=C_PANEL, fg="#94A3B8"
                 ).pack(side="left")

        # ── Step 3 — CSV + defect preview table ────────────────────────
        self._section(body, "Step 3 — Load CSV & Review Defects to Push")
        s3 = self._card(body)

        csv_f = tk.Frame(s3, bg=C_PANEL)
        csv_f.pack(fill="x", padx=10, pady=6)
        tk.Button(csv_f, text="Browse…", command=self._browse_csv,
                  bg=C_CARD, fg=C_ACCENT, relief="flat",
                  font=("Segoe UI", 9, "bold"), padx=8, pady=4,
                  cursor="hand2", activebackground=C_BORDER
                  ).pack(side="left", padx=(0, 8))
        tk.Entry(csv_f, textvariable=self._sv_csv, width=46,
                 bg="#F8F9FB", fg=C_TEXT, insertbackground=C_TEXT,
                 relief="flat", font=("Segoe UI", 9),
                 highlightbackground=C_BORDER, highlightthickness=1
                 ).pack(side="left", ipady=4)

        self._csv_lbl = tk.Label(s3, text="No file loaded yet.",
                                 font=("Segoe UI", 9), bg=C_PANEL,
                                 fg=C_SUBTEXT, anchor="w")
        self._csv_lbl.pack(fill="x", padx=10, pady=(0, 4))

        # Validate button: fetches server defects to confirm CIDs exist in selected stream
        val_f = tk.Frame(s3, bg=C_PANEL)
        val_f.pack(fill="x", padx=10, pady=(0, 4))
        self._validate_btn = tk.Button(
            val_f, text="🔍  Validate CIDs against Server",
            command=self._validate_cids,
            bg=C_CARD, fg=C_ACCENT, relief="flat",
            font=("Segoe UI", 9, "bold"), padx=10, pady=4,
            cursor="hand2", activebackground=C_BORDER, state="disabled")
        self._validate_btn.pack(side="left")
        # Debug button — lists available SOAP defect methods to diagnose server version
        tk.Button(val_f, text="…", command=self._show_defect_methods,
                  bg=C_CARD, fg=C_SUBTEXT, relief="flat",
                  font=("Segoe UI", 8), padx=6, pady=4,
                  cursor="hand2", activebackground=C_BORDER,
                  ).pack(side="left", padx=(4, 0))
        self._validate_lbl = tk.Label(
            val_f, text="", font=("Segoe UI", 9),
            bg=C_PANEL, fg=C_SUBTEXT)
        self._validate_lbl.pack(side="left", padx=(10, 0))

        # Defect preview table — CID col shows local CID; ServerCID shows matched server CID
        tbl_f = tk.Frame(s3, bg=C_PANEL)
        tbl_f.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        cols = ("CID", "ServerCID", "Classification", "Comment", "Checker", "File")
        self._defect_tree = ttk.Treeview(tbl_f, columns=cols,
                                         show="headings", height=8,
                                         selectmode="browse")
        col_widths = {"CID": 55, "ServerCID": 70, "Classification": 110,
                      "Comment": 200, "Checker": 120, "File": 140}
        hdrs = {"CID": "CSV CID", "ServerCID": "Server CID",
                "Classification": "Classification", "Comment": "Comment",
                "Checker": "Checker", "File": "File"}
        for c in cols:
            self._defect_tree.heading(c, text=hdrs[c], anchor="w")
            self._defect_tree.column(c, width=col_widths[c],
                                     anchor="w", stretch=(c == "Comment"))

        vsb2 = ttk.Scrollbar(tbl_f, orient="vertical",
                              command=self._defect_tree.yview)
        self._defect_tree.configure(yscrollcommand=vsb2.set)
        self._defect_tree.grid(row=0, column=0, sticky="nsew")
        vsb2.grid(row=0, column=1, sticky="ns")
        tbl_f.rowconfigure(0, weight=1)
        tbl_f.columnconfigure(0, weight=1)

        for cls, col in CLASS_COLOR.items():
            self._defect_tree.tag_configure(cls, foreground=col)
        self._defect_tree.tag_configure("matched",   background="#DCFCE7")
        self._defect_tree.tag_configure("unmatched", background="#FEE2E2")
        self._defect_tree.tag_configure("pushed",    foreground="#16A34A")
        self._defect_tree.tag_configure("push_fail", foreground="#DC2626")

        self._defect_tree.bind("<Double-1>", self._edit_row)

        tk.Label(s3, text="Double-click a row to edit Classification/Comment.  Green = CID confirmed on server.  Red = not found (will be skipped).",
                 font=("Segoe UI", 8), bg=C_PANEL, fg="#94A3B8", anchor="w"
                 ).pack(fill="x", padx=10, pady=(0, 6))

        # ── Footer buttons ──────────────────────────────────────────────
        foot = tk.Frame(body, bg=C_BG)
        foot.pack(fill="x", padx=20, pady=(10, 20))
        tk.Button(foot, text="Cancel", command=self.destroy,
                  bg=C_CARD, fg=C_TEXT, relief="flat",
                  font=("Segoe UI", 10), padx=14, pady=6,
                  cursor="hand2").pack(side="left")
        self._push_btn = tk.Button(
            foot, text="⬆  Push to Coverity",
            command=self._push,
            bg=C_ACCENT, fg="#FFFFFF", relief="flat",
            font=("Segoe UI", 10, "bold"), padx=18, pady=6,
            cursor="hand2", activebackground=C_ACCENT2,
            state="disabled")
        self._push_btn.pack(side="right")

        self._progress_lbl = tk.Label(foot, text="",
                                      font=("Segoe UI", 9), bg=C_BG, fg=C_SUBTEXT)
        self._progress_lbl.pack(side="right", padx=12)

    # ------------------------------------------------------------------ helpers
    def _section(self, parent, title):
        f = tk.Frame(parent, bg=C_BG)
        f.pack(fill="x", padx=20, pady=(10, 2))
        tk.Label(f, text=title, font=("Segoe UI", 10, "bold"),
                 bg=C_BG, fg=C_TEXT).pack(side="left")
        tk.Frame(f, bg=C_BORDER, height=1).pack(
            side="left", fill="x", expand=True, padx=(8, 0), pady=5)

    def _card(self, parent):
        f = tk.Frame(parent, bg=C_PANEL,
                     highlightbackground=C_BORDER, highlightthickness=1)
        f.pack(fill="x", padx=20, pady=2)
        return f

    # ------------------------------------------------------------------ logic
    def _test_connection(self):
        host = self._sv_host.get().strip()
        port = self._sv_port.get().strip()
        user = self._sv_user.get().strip()
        pw   = self._sv_pass.get()
        if not host or not user or not pw:
            self._conn_lbl.configure(text="Fill in Host, Username and Password", fg=C_INTENT)
            return
        if not zeep_available():
            self._conn_lbl.configure(text="zeep not installed — run: pip install zeep", fg=C_BUG)
            return
        self._conn_lbl.configure(text="Testing…", fg=C_SUBTEXT)
        self._test_btn.configure(state="disabled")
        self._proj_cb.configure(state="disabled")
        self._stream_cb.configure(state="disabled")

        def _worker():
            verify = not self._sv_insecure.get()
            client = CoveritySOAPClient(host, port, user, pw, verify_ssl=verify)
            ok, msg = client.test_connection()

            def _done():
                self._test_btn.configure(state="normal")
                if ok:
                    self._client = client
                    self._conn_lbl.configure(text=f"✓ {msg}", fg=C_FP)
                    self._load_projects()
                else:
                    self._conn_lbl.configure(text=f"✗ {msg}", fg=C_BUG)
            self.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    def _load_projects(self):
        self._conn_lbl.configure(text="Loading projects & triage stores…", fg=C_SUBTEXT)

        def _worker():
            projects = self._client.get_projects()
            stores   = self._client.get_triage_stores()

            # Merge project-level stores first, then API-returned stores; dedupe
            proj_stores = [p["triage_store"] for p in projects if p.get("triage_store")]
            all_stores  = list(dict.fromkeys(proj_stores + stores))

            def _done():
                self._projects = projects
                names = [p["name"] for p in projects]
                self._proj_cb.configure(values=names,
                                        state="readonly" if names else "disabled")
                self._store_cb.configure(
                    values=all_stores,
                    state="readonly" if all_stores else "normal")
                if names:
                    self._proj_cb.current(0)
                    self._sv_project.set(names[0])
                    self._on_project_selected()
                count = len(names)
                self._conn_lbl.configure(
                    text=f"✓ Connected  ({count} project{'s' if count != 1 else ''} found)",
                    fg=C_FP)
                self._refresh_push_btn()
            self.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_project_selected(self, _event=None):
        proj_name = self._sv_project.get()
        if not proj_name:
            return

        self._stream_cb.configure(state="disabled", values=[])
        self._sv_stream.set("")
        self._sv_store.set("Loading…")

        def _worker():
            streams     = self._client.get_streams_for_project(proj_name)
            triage_store = self._client.get_triage_store_for_project(proj_name)

            def _done():
                self._streams = streams
                self._stream_cb.configure(
                    values=streams,
                    state="readonly" if streams else "disabled")
                if streams:
                    self._stream_cb.current(0)
                    self._sv_stream.set(streams[0])

                # Set triage store — guaranteed to return a value (falls back to {name}-TS)
                self._sv_store.set(triage_store)
                vals = list(self._store_cb["values"])
                if triage_store not in vals:
                    vals.insert(0, triage_store)
                    self._store_cb.configure(values=vals)
                self._store_cb.current(vals.index(triage_store))

                self._refresh_push_btn()
                if self._csv_rows and self._sv_project.get():
                    self.after(100, self._validate_cids)
            self.after(0, _done)
        threading.Thread(target=_worker, daemon=True).start()

    def _browse_csv(self):
        path = filedialog.askopenfilename(
            title="Select Dispositions CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            parent=self)
        if not path:
            return
        self._sv_csv.set(path)
        self._load_csv(path)

    def _load_csv(self, path):
        import csv as _csv
        rows = []
        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                reader = _csv.DictReader(f)
                for row in reader:
                    rows.append(row)
        except Exception as e:
            self._csv_lbl.configure(text=f"✗ Could not read file: {e}", fg=C_BUG)
            self._csv_rows = []
            self._refresh_push_btn()
            return

        # Accept both dispositions.csv and final_decisions.csv column layouts
        valid = []
        for row in rows:
            cid     = row.get("CID") or row.get("cid") or ""
            cls     = (row.get("Classification") or row.get("FinalClassification") or
                       row.get("classification") or "")
            cmt     = (row.get("Comment") or row.get("FinalComment") or
                       row.get("comment") or "")
            checker = row.get("Checker") or row.get("checker") or ""
            fpath   = row.get("File") or row.get("file") or ""
            if cid and cls:
                valid.append({
                    "cid": int(cid), "classification": cls,
                    "comment": cmt, "checker": checker, "file": fpath,
                })

        self._csv_rows = valid
        # Deduplicate by CID — keep last occurrence (most specific disposition wins)
        seen = {}
        for r in valid:
            seen[r["cid"]] = r
        valid = list(seen.values())
        self._csv_rows = valid

        # Clear and repopulate the preview table
        self._defect_tree.delete(*self._defect_tree.get_children())

        if not valid:
            self._csv_lbl.configure(
                text="✗ No valid rows found. CSV must have CID + Classification columns.",
                fg=C_BUG)
        else:
            from collections import Counter
            counts  = Counter(r["classification"] for r in valid)
            summary = "  |  ".join(f"{k}: {v}" for k, v in counts.most_common())
            self._csv_lbl.configure(
                text=f"✓ {len(valid)} CID(s) loaded — double-click any row to edit before pushing",
                fg=C_FP)
            for r in valid:
                tag = r["classification"] if r["classification"] in CLASS_COLOR else ""
                self._defect_tree.insert("", "end", iid=str(r["cid"]),
                    tags=(tag,),
                    values=(r["cid"], "", r["classification"],
                            r["comment"][:80], r["checker"],
                            os.path.basename(r["file"])))
        self._refresh_push_btn()
        # Enable Validate button once CSV is loaded and we have a stream selected
        if valid and self._sv_project.get():
            self._validate_btn.configure(state="normal")
            # Auto-validate immediately
            self.after(100, self._validate_cids)
        else:
            self._validate_btn.configure(state="disabled")

    def _show_defect_methods(self):
        """List available SOAP methods on the defect service — helps diagnose server version issues."""
        if not self._client:
            messagebox.showinfo("Debug", "Connect to server first.", parent=self)
            return
        try:
            svc = self._client._get_defect_client().service
            methods = sorted(m for m in dir(svc) if not m.startswith("_"))
            win = tk.Toplevel(self)
            win.title("DefectService SOAP Methods")
            win.geometry("420x400")
            win.configure(bg=C_BG)
            tk.Label(win, text="Available SOAP methods on DefectService:",
                     font=("Segoe UI", 9, "bold"), bg=C_BG, fg=C_TEXT
                     ).pack(anchor="w", padx=12, pady=(10, 4))
            lb = tk.Listbox(win, font=("Consolas", 9), bg="#F8F9FB",
                            fg=C_TEXT, selectbackground=C_ACCENT,
                            relief="flat", borderwidth=0)
            lb.pack(fill="both", expand=True, padx=12, pady=(0, 12))
            for m in methods:
                lb.insert("end", m)
        except Exception as e:
            messagebox.showerror("Debug Error", str(e), parent=self)

    def _validate_cids(self):
        """Fetch defects from ALL project streams and cross-match CSV rows by CID or file+checker."""
        proj = self._sv_project.get().strip()
        if not proj or not self._client:
            return
        self._validate_btn.configure(state="disabled", text="Fetching…")
        self._validate_lbl.configure(
            text=f"Loading defects from all streams in '{proj}'…", fg=C_SUBTEXT)

        def _worker():
            server_defects, fetch_err = self._client.get_defects_for_project(proj)

            def _done():
                self._validate_btn.configure(state="normal",
                                             text="🔍  Validate CIDs against Server")
                if fetch_err or not server_defects:
                    detail = fetch_err or "No defects returned for project"
                    self._validate_lbl.configure(text=f"⚠️  {detail}", fg=C_BUG)
                    return

                # Build lookup: cid→defect and (checker, basename)→list of defects
                by_cid    = {d["cid"]: d for d in server_defects}
                by_sig    = {}  # (checker, basename) → list
                for d in server_defects:
                    key = (d["checker"], os.path.basename(d["file"]))
                    by_sig.setdefault(key, []).append(d)

                matched = unmatched = remapped = 0
                for r in self._csv_rows:
                    iid = str(r["cid"])
                    if not self._defect_tree.exists(iid):
                        continue
                    vals = list(self._defect_tree.item(iid)["values"])

                    if r["cid"] in by_cid:
                        vals[1] = r["cid"]
                        r["server_cid"] = r["cid"]
                        self._defect_tree.item(iid, tags=("matched",), values=vals)
                        matched += 1
                    else:
                        sig = (r["checker"], os.path.basename(r["file"]))
                        candidates = by_sig.get(sig, [])
                        if len(candidates) == 1:
                            srv_cid = candidates[0]["cid"]
                            vals[1] = srv_cid
                            r["server_cid"] = srv_cid
                            self._defect_tree.item(iid, tags=("matched",), values=vals)
                            remapped += 1
                        else:
                            vals[1] = "NOT FOUND"
                            r["server_cid"] = None
                            self._defect_tree.item(iid, tags=("unmatched",), values=vals)
                            unmatched += 1

                # Auto-remove NOT FOUND rows — they belong to other projects
                if unmatched:
                    not_found_iids = [str(r["cid"]) for r in self._csv_rows
                                      if r.get("server_cid") is None]
                    for iid in not_found_iids:
                        if self._defect_tree.exists(iid):
                            self._defect_tree.delete(iid)
                    self._csv_rows = [r for r in self._csv_rows
                                      if r.get("server_cid") is not None]

                parts = [f"{matched + remapped} ready to push"]
                if remapped:
                    parts.append(f"{remapped} remapped by file+checker")
                if unmatched:
                    parts.append(f"{unmatched} removed (not in this project)")
                self._validate_lbl.configure(
                    text="  •  ".join(parts),
                    fg=C_FP)
                self._refresh_push_btn()

            self.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    def _edit_row(self, _event=None):
        sel = self._defect_tree.selection()
        if not sel:
            return
        iid  = sel[0]
        vals = self._defect_tree.item(iid)["values"]
        # cols: CID(0), ServerCID(1), Classification(2), Comment(3), Checker(4), File(5)
        cid, cur_cls, cur_cmt = vals[0], vals[2], vals[3]

        # Find full comment from csv_rows (table truncates to 80 chars)
        full_cmt = next(
            (r["comment"] for r in self._csv_rows if r["cid"] == int(cid)),
            cur_cmt)

        win = tk.Toplevel(self)
        win.title(f"Edit CID {cid}")
        win.geometry("480x260")
        win.configure(bg=C_BG)
        win.grab_set()

        tk.Label(win, text=f"CID {cid}  —  {vals[3]}",
                 font=("Segoe UI", 11, "bold"), bg=C_BG, fg=C_ACCENT
                 ).pack(anchor="w", padx=20, pady=(16, 8))

        cls_var = tk.StringVar(value=cur_cls)
        cls_f = tk.Frame(win, bg=C_BG)
        cls_f.pack(fill="x", padx=20, pady=4)
        tk.Label(cls_f, text="Classification", width=14, anchor="w",
                 font=("Segoe UI", 9, "bold"), bg=C_BG, fg=C_SUBTEXT
                 ).pack(side="left")
        cls_cb = ttk.Combobox(cls_f, textvariable=cls_var, state="readonly",
                              values=["Bug", "False positive", "Intentional",
                                      "Needs review"],
                              width=18, font=("Segoe UI", 9))
        cls_cb.pack(side="left")

        tk.Label(win, text="Comment", font=("Segoe UI", 9, "bold"),
                 bg=C_BG, fg=C_SUBTEXT).pack(anchor="w", padx=20, pady=(8, 2))
        cmt_box = tk.Text(win, height=4, bg="#FFFFFF", fg=C_TEXT,
                          insertbackground=C_TEXT, relief="flat",
                          font=("Segoe UI", 9), borderwidth=1,
                          highlightthickness=1, highlightbackground=C_BORDER)
        cmt_box.pack(fill="x", padx=20)
        cmt_box.insert("end", full_cmt)

        def _save():
            new_cls = cls_var.get()
            new_cmt = cmt_box.get("1.0", "end-1c").strip()
            for r in self._csv_rows:
                if r["cid"] == int(cid):
                    r["classification"] = new_cls
                    r["comment"]        = new_cmt
                    break
            # Preserve existing tags (matched/unmatched); just update classification+comment cols
            existing_tags = self._defect_tree.item(iid)["tags"]
            self._defect_tree.item(iid, tags=existing_tags,
                values=(vals[0], vals[1], new_cls, new_cmt[:80], vals[4], vals[5]))
            win.destroy()

        tk.Button(win, text="Save", command=_save,
                  bg=C_ACCENT, fg="#FFFFFF", relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=16, pady=6,
                  cursor="hand2").pack(pady=12)

    def _refresh_push_btn(self):
        ready = (self._client is not None and
                 bool(self._sv_project.get()) and
                 bool(self._csv_rows))
        self._push_btn.configure(state="normal" if ready else "disabled")
        can_validate = (self._client is not None and
                        bool(self._sv_project.get()) and
                        bool(self._csv_rows))
        self._validate_btn.configure(state="normal" if can_validate else "disabled")

    def _push(self):
        if not self._client or not self._csv_rows:
            return
        store = self._sv_store.get().strip() or self._sv_project.get() or "Default"
        rows  = self._csv_rows
        self._push_btn.configure(state="disabled", text="Pushing…")

        def _worker():
            pushed_ok    = 0
            pushed_fail  = 0
            first_error  = None
            total        = len(rows)

            for i, row in enumerate(rows):
                # Use server-validated CID if available (may differ from CSV CID after remapping)
                push_cid = row.get("server_cid") or row["cid"]
                if push_cid is None:
                    # server said NOT FOUND — skip
                    pushed_fail += 1
                    def _mark_skip(cid=row["cid"]):
                        iid = str(cid)
                        if self._defect_tree.exists(iid):
                            vals = self._defect_tree.item(iid)["values"]
                            self._defect_tree.item(iid, tags=("push_fail",),
                                values=(f"✗ {vals[0]}", vals[1], vals[2], vals[3], vals[4], vals[5]))
                    self.after(0, _mark_skip)
                    def _tick_skip(done=i + 1):
                        self._progress_lbl.configure(text=f"Pushing {done}/{total}…")
                    self.after(0, _tick_skip)
                    continue

                ok, _, err = self._client.update_triage(
                    [push_cid], store,
                    row["classification"], row["comment"])
                if ok:
                    pushed_ok += 1
                    def _mark_ok(cid=row["cid"]):
                        iid = str(cid)
                        if self._defect_tree.exists(iid):
                            vals = self._defect_tree.item(iid)["values"]
                            self._defect_tree.item(iid, tags=("pushed",),
                                values=(f"✓ {vals[0]}", vals[1], vals[2], vals[3], vals[4], vals[5]))
                    self.after(0, _mark_ok)
                else:
                    pushed_fail += 1
                    if first_error is None and err:
                        first_error = err
                    def _mark_fail(cid=row["cid"]):
                        iid = str(cid)
                        if self._defect_tree.exists(iid):
                            vals = self._defect_tree.item(iid)["values"]
                            self._defect_tree.item(iid, tags=("push_fail",),
                                values=(f"✗ {vals[0]}", vals[1], vals[2], vals[3], vals[4], vals[5]))
                    self.after(0, _mark_fail)

                def _tick(done=i + 1):
                    self._progress_lbl.configure(text=f"Pushing {done}/{total}…")
                self.after(0, _tick)

            def _done():
                self._push_btn.configure(state="normal", text="⬆  Push to Coverity")
                self._progress_lbl.configure(text="")
                msg = f"Pushed to triage store '{store}'.\n\n"
                msg += f"  Succeeded : {pushed_ok}\n"
                msg += f"  Failed    : {pushed_fail}"
                if first_error:
                    msg += f"\n\nFirst error:\n{first_error}"
                    msg += ("\n\nTip: Check the Triage Store name — it usually\n"
                            "matches the project name, not 'Default'.\n"
                            f"Try: '{self._sv_project.get()}'")
                icon = "showinfo" if pushed_fail == 0 else "showwarning"
                getattr(messagebox, icon)(
                    "Push Complete" if pushed_fail == 0 else "Push Finished with Errors",
                    msg, parent=self)
                if pushed_fail == 0:
                    self.destroy()
            self.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()


# ---------------------------------------------------------------------------
# Direct Push Dialog — push the analysed results table straight to Connect
# ---------------------------------------------------------------------------
class DirectPushDialog(tk.Toplevel):
    """Push in-memory analysis results to Coverity Connect without a CSV.

    Flow: Connect → pick project + triage store → choose which defects →
    Validate CIDs against the server → review → Push.

    All non-Tk logic lives in :mod:`coverity_push` so it is unit-tested; this
    class is the thin GUI shell around it.
    """

    def __init__(self, parent, app, results, on_complete=None):
        super().__init__(parent)
        self.app = app
        self._results = results
        self._on_complete = on_complete
        self._client = None
        self._rows = []            # list[coverity_push.PushRow]
        self._validated = False

        self.title("Push Results to Coverity Connect")
        self.geometry("900x760")
        self.minsize(720, 620)
        self.configure(bg=C_BG)
        self.grab_set()

        rp = app._frames.get(ResultsPage)
        self._sv_host = tk.StringVar(value=(rp._sv_host.get() if rp else "")
                                     or "coverity-er.honaero.com")
        self._sv_port = tk.StringVar(value=(rp._sv_port.get() if rp else "") or "443")
        self._sv_user = tk.StringVar(value=rp._sv_user.get() if rp else "")
        self._sv_pass = tk.StringVar(value=rp._sv_pass.get() if rp else "")
        self._sv_store = tk.StringVar(value=(rp._sv_store.get() if rp else "") or "Default")
        self._sv_project = tk.StringVar()
        self._sv_mode = tk.StringVar(
            value=(rp._sv_push_mode.get() if rp else cpush.MODE_ACCEPTED))
        self._sv_insecure = tk.BooleanVar(value=False)
        self._sv_dry_run = tk.BooleanVar(value=False)

        self._build()
        self._refresh_preview()

    # ------------------------------------------------------------------ build
    def _section(self, parent, title):
        f = tk.Frame(parent, bg=C_BG)
        f.pack(fill="x", padx=20, pady=(10, 2))
        tk.Label(f, text=title, font=("Segoe UI", 10, "bold"),
                 bg=C_BG, fg=C_TEXT).pack(side="left")
        tk.Frame(f, bg=C_BORDER, height=1).pack(
            side="left", fill="x", expand=True, padx=(8, 0), pady=5)

    def _card(self, parent):
        f = tk.Frame(parent, bg=C_PANEL,
                     highlightbackground=C_BORDER, highlightthickness=1)
        f.pack(fill="x", padx=20, pady=2)
        return f

    def _build(self):
        canvas = tk.Canvas(self, bg=C_BG, highlightthickness=0)
        scroll = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        body = tk.Frame(canvas, bg=C_BG)
        win_id = canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))
        body.bind("<Configure>",
                  lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        tk.Label(body, text="\u2b06  Push Results to Coverity Connect",
                 font=("Segoe UI", 13, "bold"), bg=C_BG, fg=C_ACCENT
                 ).pack(anchor="w", padx=20, pady=(16, 4))
        tk.Label(body,
                 text="Pushes the defects from the current analysis directly to the\n"
                      "server triage store — no CSV export needed.",
                 font=("Segoe UI", 9), bg=C_BG, fg=C_SUBTEXT, justify="left"
                 ).pack(anchor="w", padx=20, pady=(0, 10))

        # ── Step 1 — connection ────────────────────────────────────────
        self._section(body, "Step 1 — Server Connection")
        s1 = self._card(body)

        def _row(label, var, width=26, show=""):
            f = tk.Frame(s1, bg=C_PANEL)
            f.pack(fill="x", padx=10, pady=3)
            tk.Label(f, text=label, width=10, anchor="w",
                     font=("Segoe UI", 9, "bold"), bg=C_PANEL, fg=C_SUBTEXT
                     ).pack(side="left")
            tk.Entry(f, textvariable=var, width=width, show=show,
                     bg="#FFFFFF", fg=C_TEXT, insertbackground=C_TEXT,
                     relief="flat", font=("Segoe UI", 9),
                     highlightbackground=C_BORDER, highlightthickness=1
                     ).pack(side="left", ipady=4, padx=(0, 6))

        _row("Host", self._sv_host)
        _row("Port", self._sv_port, 8)
        _row("Username", self._sv_user, 20)
        _row("Password", self._sv_pass, 20, show="*")

        opt_f = tk.Frame(s1, bg=C_PANEL)
        opt_f.pack(fill="x", padx=10, pady=3)
        tk.Checkbutton(opt_f, text="Allow self-signed certificate (insecure)",
                       variable=self._sv_insecure, bg=C_PANEL, fg=C_SUBTEXT,
                       selectcolor=C_CARD, activebackground=C_PANEL,
                       font=("Segoe UI", 9)).pack(side="left")

        conn_f = tk.Frame(s1, bg=C_PANEL)
        conn_f.pack(fill="x", padx=10, pady=(3, 8))
        self._conn_btn = tk.Button(conn_f, text="\U0001f50c  Connect",
                                   command=self._connect,
                                   bg=C_ACCENT, fg="#FFFFFF", relief="flat",
                                   font=("Segoe UI", 9, "bold"), padx=12, pady=4,
                                   cursor="hand2", activebackground=C_ACCENT2)
        self._conn_btn.pack(side="left")
        self._conn_lbl = tk.Label(conn_f, text="Not connected.",
                                  font=("Segoe UI", 9), bg=C_PANEL, fg=C_SUBTEXT)
        self._conn_lbl.pack(side="left", padx=10)

        # ── Step 2 — project + triage store ────────────────────────────
        self._section(body, "Step 2 — Project & Triage Store")
        s2 = self._card(body)

        pf = tk.Frame(s2, bg=C_PANEL)
        pf.pack(fill="x", padx=10, pady=(8, 3))
        tk.Label(pf, text="Project", width=10, anchor="w",
                 font=("Segoe UI", 9, "bold"), bg=C_PANEL, fg=C_SUBTEXT
                 ).pack(side="left")
        self._proj_cb = ttk.Combobox(pf, textvariable=self._sv_project,
                                     state="readonly", width=38,
                                     font=("Segoe UI", 9))
        self._proj_cb.pack(side="left")
        self._proj_cb.bind("<<ComboboxSelected>>", self._on_project)

        tf = tk.Frame(s2, bg=C_PANEL)
        tf.pack(fill="x", padx=10, pady=(3, 8))
        tk.Label(tf, text="Triage store", width=10, anchor="w",
                 font=("Segoe UI", 9, "bold"), bg=C_PANEL, fg=C_SUBTEXT
                 ).pack(side="left")
        self._store_cb = ttk.Combobox(tf, textvariable=self._sv_store,
                                      width=38, font=("Segoe UI", 9))
        self._store_cb.pack(side="left")
        tk.Label(tf, text="usually matches the project name",
                 font=("Segoe UI", 8), bg=C_PANEL, fg="#94A3B8"
                 ).pack(side="left", padx=6)

        # ── Step 3 — what to push ──────────────────────────────────────
        self._section(body, "Step 3 — Which Defects to Push")
        s3 = self._card(body)
        mf = tk.Frame(s3, bg=C_PANEL)
        mf.pack(fill="x", padx=10, pady=(8, 4))
        for mode in (cpush.MODE_ACCEPTED, cpush.MODE_DECIDED, cpush.MODE_ALL):
            tk.Radiobutton(mf, text=cpush.MODE_LABELS[mode],
                           variable=self._sv_mode, value=mode,
                           command=self._refresh_preview,
                           bg=C_PANEL, fg=C_TEXT, selectcolor=C_CARD,
                           activebackground=C_PANEL, font=("Segoe UI", 9)
                           ).pack(anchor="w")

        self._count_lbl = tk.Label(s3, text="", font=("Segoe UI", 9, "bold"),
                                   bg=C_PANEL, fg=C_ACCENT, anchor="w")
        self._count_lbl.pack(fill="x", padx=10, pady=(2, 6))

        vf = tk.Frame(s3, bg=C_PANEL)
        vf.pack(fill="x", padx=10, pady=(0, 8))
        self._validate_btn = tk.Button(
            vf, text="\U0001f50d  Validate CIDs against Server",
            command=self._validate, bg=C_CARD, fg=C_ACCENT, relief="flat",
            font=("Segoe UI", 9, "bold"), padx=10, pady=4,
            cursor="hand2", activebackground=C_BORDER, state="disabled")
        self._validate_btn.pack(side="left")
        self._validate_lbl = tk.Label(vf, text="", font=("Segoe UI", 9),
                                      bg=C_PANEL, fg=C_SUBTEXT)
        self._validate_lbl.pack(side="left", padx=10)

        # Preview table
        tbl_f = tk.Frame(s3, bg=C_PANEL)
        tbl_f.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        cols = ("CID", "ServerCID", "Classification", "Comment", "Checker", "File")
        widths = {"CID": 60, "ServerCID": 75, "Classification": 110,
                  "Comment": 220, "Checker": 130, "File": 140}
        self._tree = ttk.Treeview(tbl_f, columns=cols, show="headings",
                                  height=9, selectmode="browse")
        for c in cols:
            self._tree.heading(c, text=c, anchor="w")
            self._tree.column(c, width=widths[c], anchor="w",
                              stretch=(c == "Comment"))
        vsb = ttk.Scrollbar(tbl_f, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        tbl_f.rowconfigure(0, weight=1)
        tbl_f.columnconfigure(0, weight=1)
        for cls, col in CLASS_COLOR.items():
            self._tree.tag_configure(cls, foreground=col)
        self._tree.tag_configure("matched", background="#DCFCE7")
        self._tree.tag_configure("unmatched", background="#FEE2E2")
        self._tree.tag_configure("pushed", foreground="#16A34A")
        self._tree.tag_configure("push_fail", foreground="#DC2626")

        tk.Label(s3, text="Green = CID confirmed on the server.  Red = not found "
                          "(skipped).  Validation is required before pushing.",
                 font=("Segoe UI", 8), bg=C_PANEL, fg="#94A3B8", anchor="w"
                 ).pack(fill="x", padx=10, pady=(0, 6))

        # ── Footer ─────────────────────────────────────────────────────
        foot = tk.Frame(body, bg=C_BG)
        foot.pack(fill="x", padx=20, pady=(10, 20))
        tk.Button(foot, text="Close", command=self.destroy,
                  bg=C_CARD, fg=C_TEXT, relief="flat",
                  font=("Segoe UI", 10), padx=14, pady=6,
                  cursor="hand2").pack(side="left")
        tk.Checkbutton(foot, text="Dry run (preview only, writes nothing)",
                       variable=self._sv_dry_run, bg=C_BG, fg=C_SUBTEXT,
                       selectcolor=C_CARD, activebackground=C_BG,
                       font=("Segoe UI", 9)).pack(side="left", padx=14)
        self._push_btn = tk.Button(
            foot, text="\u2b06  Push to Coverity", command=self._push,
            bg=C_ACCENT, fg="#FFFFFF", relief="flat",
            font=("Segoe UI", 10, "bold"), padx=18, pady=6,
            cursor="hand2", activebackground=C_ACCENT2, state="disabled")
        self._push_btn.pack(side="right")
        self._progress_lbl = tk.Label(foot, text="", font=("Segoe UI", 9),
                                      bg=C_BG, fg=C_SUBTEXT)
        self._progress_lbl.pack(side="right", padx=12)

    # ---------------------------------------------------------------- preview
    def _reviewer(self):
        try:
            return os.getlogin()
        except Exception:
            return os.environ.get("USERNAME", "") or ""

    def _refresh_preview(self):
        """Rebuild the push rows from the current selection mode."""
        selected = cpush.select_defects(self._results, self._sv_mode.get())
        self._rows = cpush.build_push_rows(selected, reviewer=self._reviewer())
        self._validated = False
        self._validate_lbl.configure(text="", fg=C_SUBTEXT)

        self._tree.delete(*self._tree.get_children())
        for row in self._rows:
            tag = row.classification if row.classification in CLASS_COLOR else ""
            self._tree.insert("", "end", iid=str(row.cid), tags=(tag,),
                              values=(row.cid, "", row.classification,
                                      row.comment.replace("\n", " ")[:90],
                                      row.checker, os.path.basename(row.file)))
        total = len(self._results)
        self._count_lbl.configure(
            text=f"{len(self._rows)} of {total} defect(s) selected for push")
        self._refresh_buttons()

    def _refresh_buttons(self):
        connected = self._client is not None
        has_rows = bool(self._rows)
        self._validate_btn.configure(
            state="normal" if (connected and has_rows and self._sv_project.get())
            else "disabled")
        ready = connected and has_rows and self._validated and any(
            r.server_cid is not None for r in self._rows)
        self._push_btn.configure(state="normal" if ready else "disabled")

    # ------------------------------------------------------------- connection
    def _connect(self):
        host = self._sv_host.get().strip()
        port = self._sv_port.get().strip()
        user = self._sv_user.get().strip()
        pw = self._sv_pass.get()
        if not (host and port and user and pw):
            messagebox.showwarning("Missing Details",
                                   "Host, port, username and password are required.",
                                   parent=self)
            return
        if not zeep_available():
            messagebox.showerror(
                "Missing Dependency",
                "The 'zeep' library is required for Coverity Connect.\n\n"
                "Install it with:  pip install zeep", parent=self)
            return

        self._conn_btn.configure(state="disabled", text="Connecting…")
        self._conn_lbl.configure(text="Contacting server…", fg=C_SUBTEXT)
        verify = not self._sv_insecure.get()

        def _worker():
            client = CoveritySOAPClient(host, port, user, pw, verify_ssl=verify)
            ok, info = client.test_connection()
            projects = stores = None
            if ok:
                try:
                    projects = client.get_projects()
                    stores = client.get_triage_stores()
                except Exception:
                    projects, stores = projects or [], stores or []

            def _done():
                self._conn_btn.configure(state="normal", text="\U0001f50c  Connect")
                if not ok:
                    self._client = None
                    self._conn_lbl.configure(text=f"\u2717 {info}", fg=C_BUG)
                    self._refresh_buttons()
                    return
                self._client = client
                self._conn_lbl.configure(text=f"\u2713 {info}", fg=C_FP)
                names = [p["name"] if isinstance(p, dict) else str(p)
                         for p in (projects or [])]
                self._proj_cb.configure(values=names)
                if names:
                    self._sv_project.set(names[0])
                    self._on_project()
                store_names = [s if isinstance(s, str) else str(s)
                               for s in (stores or [])]
                if store_names:
                    self._store_cb.configure(values=store_names)
                self._refresh_buttons()

            self.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_project(self, _event=None):
        """Auto-fill the triage store that belongs to the chosen project."""
        proj = self._sv_project.get().strip()
        self._validated = False
        self._refresh_buttons()
        if not (proj and self._client):
            return

        def _worker():
            try:
                store = self._client.get_triage_store_for_project(proj)
            except Exception:
                store = None

            def _done():
                if store:
                    self._sv_store.set(store)
                    vals = list(self._store_cb.cget("values") or [])
                    if store not in vals:
                        vals.insert(0, store)
                        self._store_cb.configure(values=vals)
                self._refresh_buttons()

            self.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    # -------------------------------------------------------------- validation
    def _validate(self):
        proj = self._sv_project.get().strip()
        if not (proj and self._client and self._rows):
            return
        self._validate_btn.configure(state="disabled", text="Fetching…")
        self._validate_lbl.configure(
            text=f"Loading defects from '{proj}'…", fg=C_SUBTEXT)

        def _worker():
            try:
                server_defects, err = self._client.get_defects_for_project(proj)
            except Exception as exc:
                server_defects, err = None, str(exc)

            def _done():
                self._validate_btn.configure(
                    state="normal", text="\U0001f50d  Validate CIDs against Server")
                if err or not server_defects:
                    self._validate_lbl.configure(
                        text=f"\u26a0 {err or 'No defects returned for project'}",
                        fg=C_BUG)
                    self._validated = False
                    self._refresh_buttons()
                    return
                report = cpush.validate_rows(self._rows, server_defects)
                for row in self._rows:
                    iid = str(row.cid)
                    if not self._tree.exists(iid):
                        continue
                    vals = list(self._tree.item(iid)["values"])
                    if row.server_cid is not None:
                        vals[1] = row.server_cid
                        self._tree.item(iid, tags=("matched",), values=vals)
                    else:
                        vals[1] = "NOT FOUND"
                        self._tree.item(iid, tags=("unmatched",), values=vals)
                self._validated = True
                self._validate_lbl.configure(text=report.summary(), fg=C_FP)
                self._refresh_buttons()

            self.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    # -------------------------------------------------------------------- push
    def _push(self):
        if not (self._client and self._rows and self._validated):
            return
        store = (self._sv_store.get().strip()
                 or self._sv_project.get().strip() or "Default")
        dry = bool(self._sv_dry_run.get())
        pushable = [r for r in self._rows if r.server_cid is not None]
        skipped = len(self._rows) - len(pushable)

        confirm = (f"{'DRY RUN — nothing will be written.' if dry else ''}\n\n"
                   f"Push {len(pushable)} disposition(s) to triage store "
                   f"'{store}'?\n")
        if skipped:
            confirm += f"\n{skipped} defect(s) not found on the server will be skipped."
        if not dry:
            confirm += "\n\nThis overwrites the current triage on the server."
        if not messagebox.askyesno("Confirm Push", confirm.strip(), parent=self):
            return

        self._push_btn.configure(state="disabled", text="Pushing…")
        total = len(pushable)

        def _progress(done, _total, row):
            def _tick():
                self._progress_lbl.configure(text=f"Pushing {done}/{total}…")
                iid = str(row.cid)
                if self._tree.exists(iid):
                    tag = "pushed" if row.status == "\u2713" else "push_fail"
                    vals = list(self._tree.item(iid)["values"])
                    vals[0] = f"{row.status} {row.cid}"
                    self._tree.item(iid, tags=(tag,), values=vals)
            self.after(0, _tick)

        def _worker():
            report = cpush.push_rows(self._client, self._rows, store,
                                     progress_cb=_progress, dry_run=dry)

            def _done():
                self._push_btn.configure(state="normal",
                                         text="\u2b06  Push to Coverity")
                self._progress_lbl.configure(text="")
                if not dry:
                    cpush.apply_status_to_results(self._results, self._rows)
                    if self._on_complete:
                        try:
                            self._on_complete()
                        except Exception:
                            pass
                msg = f"Triage store: '{store}'\n\n{report.summary()}"
                if report.failed and not dry:
                    msg += ("\n\nTip: if every row failed, check the triage store "
                            "name — it usually matches the project name rather "
                            f"than 'Default'. Try: '{self._sv_project.get()}'")
                if report.ok:
                    messagebox.showinfo("Push Complete", msg, parent=self)
                else:
                    messagebox.showwarning("Push Finished with Errors", msg,
                                           parent=self)

            self.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()


# ---------------------------------------------------------------------------
# Commit Defects Dialog — uploads an intermediate directory (cov-commit-defects)
# ---------------------------------------------------------------------------
class CommitDefectsDialog(tk.Toplevel):
    """Upload existing Coverity analysis results to a Connect stream.

    The user runs cov-build / cov-analyze themselves; this dialog only runs
    ``cov-commit-defects`` on the resulting intermediate directory.

    The input must be an **intermediate directory (idir)** containing both
    ``emit/`` (captured source) and ``output/`` (analysis results). The dialog
    inspects the chosen folder and names whichever part is missing, rather than
    letting Coverity fail with a cryptic message.

    All command building, validation and execution live in :mod:`cov_cli`;
    this class is only the GUI shell.
    """

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._canceller = None
        self._running = False

        self.title("Commit Defects to Coverity Connect")
        self.geometry("900x760")
        self.minsize(720, 620)
        self.configure(bg=C_BG)
        self.grab_set()

        self._sv_bin = tk.StringVar()
        self._sv_idir = tk.StringVar()
        self._sv_host = tk.StringVar(value="coverity-er.honaero.com")
        self._sv_port = tk.StringVar(value="443")
        self._sv_ssl = tk.BooleanVar(value=True)
        self._sv_project = tk.StringVar()
        self._sv_stream = tk.StringVar()
        self._sv_user = tk.StringVar()
        self._sv_pass = tk.StringVar()
        self._sv_keyfile = tk.StringVar()
        self._sv_trust = tk.BooleanVar(value=True)
        self._sv_desc = tk.StringVar(value="Coverity Tool commit")
        self._sv_dry = tk.BooleanVar(value=False)

        # Populated by _connect() once the user has signed in. Kept as
        # state so the Project dropdown's <<ComboboxSelected>> handler can
        # ask the server for the streams belonging to the chosen project.
        self._client = None

        self._build()
        self._check_tool()
        self._refresh_ready()

    # ------------------------------------------------------------------ build
    def _section(self, parent, title):
        f = tk.Frame(parent, bg=C_BG)
        f.pack(fill="x", padx=20, pady=(10, 2))
        tk.Label(f, text=title, font=("Segoe UI", 10, "bold"),
                 bg=C_BG, fg=C_TEXT).pack(side="left")
        tk.Frame(f, bg=C_BORDER, height=1).pack(
            side="left", fill="x", expand=True, padx=(8, 0), pady=5)

    def _card(self, parent):
        f = tk.Frame(parent, bg=C_PANEL,
                     highlightbackground=C_BORDER, highlightthickness=1)
        f.pack(fill="x", padx=20, pady=2)
        return f

    def _field(self, parent, label, var, width=46, show="", browse=None,
               hint=""):
        f = tk.Frame(parent, bg=C_PANEL)
        f.pack(fill="x", padx=10, pady=3)
        tk.Label(f, text=label, width=15, anchor="w",
                 font=("Segoe UI", 9, "bold"), bg=C_PANEL, fg=C_SUBTEXT
                 ).pack(side="left")
        tk.Entry(f, textvariable=var, width=width, show=show,
                 bg="#FFFFFF", fg=C_TEXT, insertbackground=C_TEXT,
                 relief="flat", font=("Segoe UI", 9),
                 highlightbackground=C_BORDER, highlightthickness=1
                 ).pack(side="left", ipady=4, padx=(0, 6))
        if browse:
            tk.Button(f, text="…", command=browse, bg=C_CARD, fg=C_ACCENT,
                      relief="flat", font=("Segoe UI", 8), padx=6,
                      cursor="hand2", activebackground=C_BORDER
                      ).pack(side="left")
        if hint:
            tk.Label(f, text=hint, font=("Segoe UI", 8), bg=C_PANEL,
                     fg="#94A3B8").pack(side="left", padx=4)
        return f

    def _build(self):
        canvas = tk.Canvas(self, bg=C_BG, highlightthickness=0)
        scroll = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        body = tk.Frame(canvas, bg=C_BG)
        win_id = canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))
        body.bind("<Configure>",
                  lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        tk.Label(body, text="\u2b06  Commit Defects to Coverity Connect",
                 font=("Segoe UI", 13, "bold"), bg=C_BG, fg=C_ACCENT
                 ).pack(anchor="w", padx=20, pady=(16, 4))
        tk.Label(body,
                 text="Uploads results you have already produced with cov-build /\n"
                      "cov-analyze into a Coverity Connect stream. Afterwards, Pull\n"
                      "the defects back in and disposition them.",
                 font=("Segoe UI", 9), bg=C_BG, fg=C_SUBTEXT, justify="left"
                 ).pack(anchor="w", padx=20, pady=(0, 8))

        self._tool_lbl = tk.Label(body, text="", font=("Segoe UI", 9),
                                  bg=C_BG, fg=C_SUBTEXT, justify="left")
        self._tool_lbl.pack(anchor="w", padx=20, pady=(0, 6))

        # ── Tool location ──────────────────────────────────────────────
        self._section(body, "Coverity Tool")
        s0 = self._card(body)
        self._field(s0, "Coverity bin", self._sv_bin, browse=self._browse_bin,
                    hint="blank if cov-commit-defects is on PATH")
        tk.Button(s0, text="Re-check", command=self._check_tool,
                  bg=C_CARD, fg=C_ACCENT, relief="flat",
                  font=("Segoe UI", 8, "bold"), padx=8, pady=3,
                  cursor="hand2", activebackground=C_BORDER
                  ).pack(anchor="w", padx=10, pady=(0, 8))

        # ── Step 1 — what to upload ────────────────────────────────────
        self._section(body, "Step 1 — Analysis Results to Upload")
        s1 = self._card(body)
        self._field(s1, "Intermediate dir", self._sv_idir,
                    browse=self._browse_idir,
                    hint="the --dir folder from cov-build / cov-analyze")
        self._input_lbl = tk.Label(
            s1, text="Select the intermediate directory (idir) to upload — "
                     "it must contain emit/ and output/.",
            font=("Segoe UI", 9), bg=C_PANEL, fg=C_SUBTEXT,
            anchor="w", justify="left", wraplength=760)
        self._input_lbl.pack(fill="x", padx=10, pady=(0, 8))
        self._sv_idir.trace_add("write", lambda *_: self._inspect_input())

        # ── Step 2 — destination ───────────────────────────────────────
        # Mirrors the Push dialog: sign in first, then pick project + stream
        # from live dropdowns so the user cannot mistype a stream name (and
        # so a stream they lack permission on is transparently absent).
        self._section(body, "Step 2 — Destination")
        s2 = self._card(body)
        self._field(s2, "Host", self._sv_host)
        self._field(s2, "Port", self._sv_port, width=10)
        tk.Checkbutton(s2, text="Use SSL (https)", variable=self._sv_ssl,
                       bg=C_PANEL, fg=C_SUBTEXT, selectcolor=C_CARD,
                       activebackground=C_PANEL, font=("Segoe UI", 9)
                       ).pack(anchor="w", padx=10)
        self._field(s2, "Username", self._sv_user, width=24)
        self._field(s2, "Password", self._sv_pass, width=24, show="*")
        self._field(s2, "or Auth key file", self._sv_keyfile,
                    browse=self._browse_key,
                    hint="preferred for the upload — no password needed")

        # ── Connect button + status ────────────────────────────────────
        conn_f = tk.Frame(s2, bg=C_PANEL)
        conn_f.pack(fill="x", padx=10, pady=(6, 4))
        self._conn_btn = tk.Button(
            conn_f, text="\U0001f50c  Connect",
            command=self._connect,
            bg=C_ACCENT, fg="#FFFFFF", relief="flat",
            font=("Segoe UI", 9, "bold"), padx=12, pady=4,
            cursor="hand2", activebackground=C_ACCENT2)
        self._conn_btn.pack(side="left")
        self._conn_lbl = tk.Label(
            conn_f,
            text="Sign in to load your projects and streams.",
            font=("Segoe UI", 9), bg=C_PANEL, fg=C_SUBTEXT)
        self._conn_lbl.pack(side="left", padx=10)

        # ── Project dropdown (populated by _connect) ───────────────────
        pf = tk.Frame(s2, bg=C_PANEL)
        pf.pack(fill="x", padx=10, pady=(4, 3))
        tk.Label(pf, text="Project", width=15, anchor="w",
                 font=("Segoe UI", 9, "bold"), bg=C_PANEL, fg=C_SUBTEXT
                 ).pack(side="left")
        self._proj_cb = ttk.Combobox(pf, textvariable=self._sv_project,
                                     state="disabled", width=38,
                                     font=("Segoe UI", 9))
        self._proj_cb.pack(side="left", ipady=2)
        self._proj_cb.bind("<<ComboboxSelected>>", self._on_project_select)

        # ── Stream dropdown (populated when a project is picked) ───────
        sf = tk.Frame(s2, bg=C_PANEL)
        sf.pack(fill="x", padx=10, pady=(3, 3))
        tk.Label(sf, text="Stream", width=15, anchor="w",
                 font=("Segoe UI", 9, "bold"), bg=C_PANEL, fg=C_SUBTEXT
                 ).pack(side="left")
        self._stream_cb = ttk.Combobox(sf, textvariable=self._sv_stream,
                                       state="disabled", width=38,
                                       font=("Segoe UI", 9))
        self._stream_cb.pack(side="left", ipady=2)
        tk.Label(sf, text="must already exist in Coverity Connect",
                 font=("Segoe UI", 8), bg=C_PANEL, fg="#94A3B8"
                 ).pack(side="left", padx=6)

        self._field(s2, "Description", self._sv_desc)
        tk.Checkbutton(s2, text="Trust a new/unseen server certificate",
                       variable=self._sv_trust, bg=C_PANEL, fg=C_SUBTEXT,
                       selectcolor=C_CARD, activebackground=C_PANEL,
                       font=("Segoe UI", 9)).pack(anchor="w", padx=10,
                                                  pady=(0, 4))

        # ── Live "what's still missing" hint ───────────────────────────
        # Rechecks validate_config(cfg) on every field change so the user
        # sees exactly which required fields for cov-commit-defects are
        # still blank, rather than discovering it at run time.
        self._ready_lbl = tk.Label(
            s2, text="", font=("Segoe UI", 9), bg=C_PANEL,
            fg=C_SUBTEXT, anchor="w", justify="left", wraplength=760)
        self._ready_lbl.pack(fill="x", padx=10, pady=(2, 8))
        for _v in (self._sv_bin, self._sv_idir, self._sv_host, self._sv_port,
                   self._sv_stream, self._sv_user, self._sv_pass,
                   self._sv_keyfile):
            _v.trace_add("write", lambda *_: self._refresh_ready())

        # ── Log ────────────────────────────────────────────────────────
        self._section(body, "Output")
        log_f = tk.Frame(body, bg=C_BG)
        log_f.pack(fill="both", expand=True, padx=20, pady=(0, 6))
        self._log = scrolledtext.ScrolledText(
            log_f, height=14, bg="#1E1E1E", fg="#D4D4D4",
            font=("Consolas", 9), relief="flat", wrap="word",
            insertbackground="#D4D4D4", state="disabled")
        self._log.pack(fill="both", expand=True)
        self._log.tag_configure("cmd", foreground="#4FC1FF")
        self._log.tag_configure("err", foreground="#F48771")
        self._log.tag_configure("ok", foreground="#89D185")

        # ── Footer ─────────────────────────────────────────────────────
        foot = tk.Frame(body, bg=C_BG)
        foot.pack(fill="x", padx=20, pady=(4, 20))
        tk.Button(foot, text="Close", command=self._on_close,
                  bg=C_CARD, fg=C_TEXT, relief="flat",
                  font=("Segoe UI", 10), padx=14, pady=6,
                  cursor="hand2").pack(side="left")
        self._cancel_btn = tk.Button(
            foot, text="Cancel", command=self._cancel,
            bg=C_CARD, fg=C_BUG, relief="flat", font=("Segoe UI", 10),
            padx=14, pady=6, cursor="hand2", state="disabled")
        self._cancel_btn.pack(side="left", padx=8)
        tk.Checkbutton(foot, text="Dry run (show the command only)",
                       variable=self._sv_dry, bg=C_BG, fg=C_SUBTEXT,
                       selectcolor=C_CARD, activebackground=C_BG,
                       font=("Segoe UI", 9)).pack(side="left", padx=10)
        self._run_btn = tk.Button(
            foot, text="\u2b06  Commit to Coverity", command=self._run,
            bg=C_ACCENT, fg="#FFFFFF", relief="flat",
            font=("Segoe UI", 10, "bold"), padx=20, pady=6,
            cursor="hand2", activebackground=C_ACCENT2)
        self._run_btn.pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------------------------------------------------------- browse
    def _browse_bin(self):
        d = filedialog.askdirectory(title="Select Coverity Analysis bin folder",
                                    parent=self)
        if d:
            self._sv_bin.set(d)
            self._check_tool()

    def _browse_idir(self):
        d = filedialog.askdirectory(
            title="Select the Coverity intermediate directory (idir)",
            parent=self)
        if d:
            self._sv_idir.set(d)

    def _browse_key(self):
        f = filedialog.askopenfilename(title="Select Coverity auth key file",
                                       parent=self)
        if f:
            self._sv_keyfile.set(f)

    # ------------------------------------------------------------------ tool
    def _check_tool(self):
        path = cov_cli.commit_tool_path(self._sv_bin.get().strip())
        if path:
            self._tool_lbl.configure(
                text=f"\u2713  Found {os.path.basename(path)}", fg=C_FP)
        else:
            self._tool_lbl.configure(
                text="\u26a0  cov-commit-defects not found.\n"
                     "     Set the Coverity bin folder above, or add it to PATH.",
                fg=C_BUG)

    # ----------------------------------------------------------- input check
    def _inspect_input(self):
        """Tell the user immediately whether the chosen folder is usable."""
        info = cov_cli.inspect_input(self._sv_idir.get().strip())
        if info.committable:
            self._input_lbl.configure(text="\u2713  " + info.message, fg=C_FP)
        elif info.kind == cov_cli.INPUT_MISSING and not self._sv_idir.get().strip():
            self._input_lbl.configure(
                text="Select the intermediate directory (idir) to upload — "
                     "it must contain emit/ and output/.",
                fg=C_SUBTEXT)
        else:
            text = "\u26a0  " + info.message
            if info.hint:
                text += "\n     " + info.hint
            self._input_lbl.configure(text=text, fg=C_BUG)

    # ------------------------------------------------------------------- log
    def _append(self, text, tag=None):
        def _do():
            self._log.configure(state="normal")
            self._log.insert("end", text, tag or "")
            self._log.see("end")
            self._log.configure(state="disabled")
        self.after(0, _do)

    # ---------------------------------------------------------------- config
    def _config(self):
        return cov_cli.CommitConfig(
            idir=self._sv_idir.get().strip(),
            bin_dir=self._sv_bin.get().strip(),
            host=self._sv_host.get().strip(),
            port=self._sv_port.get().strip(),
            stream=self._sv_stream.get().strip(),
            username=self._sv_user.get().strip(),
            password=self._sv_pass.get(),
            auth_key_file=self._sv_keyfile.get().strip(),
            use_ssl=bool(self._sv_ssl.get()),
            on_new_cert_trust=bool(self._sv_trust.get()),
            description=self._sv_desc.get().strip(),
        )

    # ---------------------------------------------------------- readiness
    def _refresh_ready(self):
        """Live status of which required fields are still blank.

        Runs ``cov_cli.validate_config`` on the current form and lists any
        remaining problems, so the user knows exactly what's missing for
        ``cov-commit-defects`` without having to press the button first.
        Also enables/disables the run button accordingly.
        """
        try:
            problems = cov_cli.validate_config(self._config())
        except Exception as exc:                          # defensive
            problems = [str(exc)]
        if problems:
            self._ready_lbl.configure(
                text="\u26a0  Still needed:\n     • " +
                     "\n     • ".join(problems),
                fg=C_BUG)
            if hasattr(self, "_run_btn"):
                self._run_btn.configure(state="disabled")
        else:
            self._ready_lbl.configure(
                text="\u2713  All required fields for cov-commit-defects "
                     "are set.", fg=C_FP)
            if hasattr(self, "_run_btn"):
                self._run_btn.configure(state="normal")

    # ------------------------------------------------------------ connect
    def _connect(self):
        """Sign in to Coverity Connect and populate the Project dropdown.

        Uses username + password (SOAP). An auth-key file is fine for the
        actual ``cov-commit-defects`` upload, but the browsing API needs
        credentials — we tell the user that instead of failing silently.
        """
        host = self._sv_host.get().strip()
        port = self._sv_port.get().strip()
        user = self._sv_user.get().strip()
        pw = self._sv_pass.get()
        if not (host and port and user and pw):
            messagebox.showwarning(
                "Missing Details",
                "Host, port, username and password are required to load\n"
                "the project and stream lists from Coverity Connect.\n\n"
                "(An auth-key file can still be used for the upload itself.)",
                parent=self)
            return
        if not zeep_available():
            messagebox.showerror(
                "Missing Dependency",
                "The 'zeep' library is required for Coverity Connect.\n\n"
                "Install it with:  pip install zeep", parent=self)
            return

        self._conn_btn.configure(state="disabled", text="Connecting…")
        self._conn_lbl.configure(text="Contacting server…", fg=C_SUBTEXT)
        self._proj_cb.configure(state="disabled", values=[])
        self._stream_cb.configure(state="disabled", values=[])
        self._sv_project.set("")
        self._sv_stream.set("")
        # verify_ssl mirrors the "trust new cert" toggle — if the user has
        # opted to trust unseen certs for the upload, we shouldn't refuse
        # the SOAP call for the very same server.
        verify = not bool(self._sv_trust.get())

        def _worker():
            client = CoveritySOAPClient(host, port, user, pw,
                                        verify_ssl=verify)
            ok, info = client.test_connection()
            projects = None
            if ok:
                try:
                    projects = client.get_projects()
                except Exception:
                    projects = []

            def _done():
                self._conn_btn.configure(state="normal",
                                         text="\U0001f50c  Connect")
                if not ok:
                    self._client = None
                    self._conn_lbl.configure(text=f"\u2717 {info}",
                                             fg=C_BUG)
                    self._refresh_ready()
                    return
                self._client = client
                names = [p["name"] if isinstance(p, dict) else str(p)
                         for p in (projects or [])]
                count = len(names)
                self._conn_lbl.configure(
                    text=f"\u2713 Connected  "
                         f"({count} project{'s' if count != 1 else ''} "
                         "visible to this user)",
                    fg=C_FP)
                self._proj_cb.configure(
                    values=names,
                    state="readonly" if names else "disabled")
                if names:
                    self._sv_project.set(names[0])
                    self._on_project_select()
                self._refresh_ready()

            self.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_project_select(self, _event=None):
        """Load the streams belonging to the newly-selected project."""
        proj = self._sv_project.get().strip()
        self._stream_cb.configure(state="disabled", values=[])
        self._sv_stream.set("")
        if not (proj and self._client):
            self._refresh_ready()
            return

        def _worker():
            try:
                streams = self._client.get_streams_for_project(proj) or []
            except Exception:
                streams = []

            def _done():
                self._stream_cb.configure(
                    values=streams,
                    state="readonly" if streams else "disabled")
                if streams:
                    self._sv_stream.set(streams[0])
                else:
                    # No streams visible → almost always a permissions
                    # issue on Coverity Connect for this user, not a bug
                    # the tool can work around.
                    self._conn_lbl.configure(
                        text=f"\u2713 Connected  "
                             f"(no streams visible in '{proj}' — "
                             "check your Coverity permissions)",
                        fg=C_BUG)
                self._refresh_ready()

            self.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    # ------------------------------------------------------------------- run
    def _run(self):
        if self._running:
            return
        cfg = self._config()
        problems = cov_cli.validate_config(cfg)
        if problems:
            messagebox.showwarning(
                "Check the Settings",
                "Please fix the following:\n\n" +
                "\n\n".join(f"  •  {p}" for p in problems), parent=self)
            return

        dry = bool(self._sv_dry.get())
        if not dry and not messagebox.askyesno(
                "Confirm Commit",
                f"Upload the analysis results in\n{cfg.idir}\n\n"
                f"to stream '{cfg.stream}' on {cfg.host}?",
                parent=self):
            return

        self._running = True
        self._canceller = cov_cli.Canceller()
        self._run_btn.configure(state="disabled", text="Committing…")
        self._cancel_btn.configure(state="normal")
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

        def _worker():
            result = cov_cli.run_commit(cfg, log_cb=self._append,
                                        canceller=self._canceller,
                                        dry_run=dry)

            def _done():
                self._running = False
                self._run_btn.configure(state="normal",
                                        text="\u2b06  Commit to Coverity")
                self._cancel_btn.configure(state="disabled")
                self._append("\n" + result.summary() + "\n",
                             "ok" if result.ok else "err")
                if result.cancelled:
                    messagebox.showinfo("Cancelled",
                                        "The commit was cancelled.", parent=self)
                elif result.ok and not dry:
                    messagebox.showinfo(
                        "Commit Complete",
                        f"Defects are now in stream '{cfg.stream}'.\n\n"
                        "Next: use '⬇ Pull from Coverity' on the Setup page "
                        "to bring them in for disposition.", parent=self)
                elif result.ok:
                    messagebox.showinfo("Dry Run", result.summary(), parent=self)
                else:
                    messagebox.showerror(
                        "Commit Failed",
                        result.summary() + "\n\nSee the output log for details.",
                        parent=self)

            self.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    def _cancel(self):
        if self._canceller:
            self._canceller.cancel()
            self._append("\n! Cancelling…\n", "err")

    def _on_close(self):
        if self._running:
            if not messagebox.askyesno(
                    "Commit in Progress",
                    "A commit is still running. Cancel it and close?",
                    parent=self):
                return
            self._cancel()
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
