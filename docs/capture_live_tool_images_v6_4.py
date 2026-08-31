#!/usr/bin/env python3
from __future__ import annotations

import ctypes
import json
import sys
import time
from pathlib import Path

from PIL import ImageGrab
import tkinter as tk

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_gui import (  # noqa: E402
    App,
    AnalysisPage,
    C_FP,
    CommitDefectsDialog,
    DetailWindow,
    DirectPushDialog,
    PullDialog,
    PushDialog,
    ResultsPage,
    SetupPage,
)

OUT = ROOT / "docs" / "images" / "manual_v6_4_live"
META = OUT / "annotation_map.json"
SHOT_PAD = 2


def _bring_front(win: tk.Misc) -> None:
    win.update_idletasks()
    win.lift()
    win.update()
    time.sleep(0.18)


def _set_topmost(win: tk.Misc, value: bool) -> None:
    try:
        win.attributes("-topmost", bool(value))
    except Exception:
        pass


def _safe_restore_topmost(win: tk.Misc) -> None:
    _set_topmost(win, False)
    win.update()
    time.sleep(0.06)


def _shot(win: tk.Misc, path: Path, pad: int = SHOT_PAD) -> dict:
    _bring_front(win)
    _set_topmost(win, True)
    try:
        win.update_idletasks()
        win.update()
        time.sleep(0.12)

        x = win.winfo_rootx()
        y = win.winfo_rooty()
        w = win.winfo_width()
        h = win.winfo_height()

        hwnd = int(win.winfo_id())
        img = None
        try:
            img = ImageGrab.grab(window=hwnd)
        except TypeError:
            img = None
        except Exception:
            img = None

        if img is None:
            bbox = (x + pad, y + pad, x + w - pad, y + h - pad)
            img = ImageGrab.grab(bbox=bbox, all_screens=True)

        img.save(path, format="PNG", optimize=True)

        iw, ih = img.size
        if iw > 0 and ih > 0:
            return {"x": x, "y": y, "w": iw, "h": ih, "window_relative": True}
        return {"x": x + pad, "y": y + pad, "w": max(1, w - 2 * pad), "h": max(1, h - 2 * pad), "window_relative": False}
    finally:
        _safe_restore_topmost(win)


def _sample_results() -> list[dict]:
    rows = []
    src = (
        "int fnParseUserData(...) {\n"
        "    if (dwVarOffset >= sizeof(buf)) return ERROR;\n"
        "    return fnParseUserData(...);\n"
        "}\n"
    )
    base = [
        (3704139, "OVERRUN", "Bug", "High", 0.77, "DSIUsrPrmtvProc.cpp", 706, "fnParseEnddCnf"),
        (3704169, "OVERRUN", "Bug", "High", 0.74, "DSIUsrPrmtvProc.cpp", 708, "fnParseEndInd"),
        (3704314, "STRING_NULL", "False positive", "Low", 0.86, "CM_LsnrFSM.c", 2468, "fnCM_LS_Listen_State"),
        (3704401, "BUFFER_SIZE", "False positive", "Low", 0.81, "CPDLC_USR_FSM.c", 10556, "state_fn"),
        (3704423, "BUFFER_SIZE", "False positive", "Low", 0.82, "FaultMngr.cpp", 293, "fault_handler"),
        (3704424, "OVERRUN", "False positive", "Low", 0.79, "CPDLC.c", 940, "ATN_Abort_NDA"),
        (3704450, "STRING_NULL", "False positive", "Low", 0.80, "CM_LsnrFSM.c", 4925, "fnCM_LS_WaitForUser_Log"),
        (3704475, "REVERSE_NULL", "False positive", "Low", 0.72, "pe_ObjectIdentifier.c", 129, "obj_id"),
        (3704551, "BUFFER_SIZE", "False positive", "Low", 0.69, "seamless_manager.c", 571, "strcpy_guard"),
        (3704600, "RESOURCE_LEAK", "Needs review", "Medium", 0.61, "session.c", 88, "session_loop"),
    ]
    for cid, checker, cls, sev, conf, file_name, line, func in base:
        rows.append({
            "cid": cid,
            "checker": checker,
            "classification": cls,
            "comment": f"{checker} at line {line} in {func}.",
            "fix": "Add bounds check and fail-safe return for invalid offsets." if cls == "Bug" else "No fix required.",
            "file": file_name,
            "line": line,
            "function": func,
            "severity": sev,
            "confidence": conf,
            "source_code": src,
            "accepted": False,
            "action": "Fix Required" if cls == "Bug" else ("Ignore" if cls == "False positive" else "Undecided"),
            "overridden": cls == "False positive",
        })
    return rows


def _is_visible(w: tk.Misc) -> bool:
    try:
        return bool(w.winfo_ismapped() and w.winfo_width() > 2 and w.winfo_height() > 2)
    except Exception:
        return False


def _descendants(root: tk.Misc) -> list[tk.Misc]:
    out: list[tk.Misc] = []
    stack = [root]
    while stack:
        w = stack.pop()
        out.append(w)
        try:
            stack.extend(list(w.winfo_children()))
        except Exception:
            pass
    return out


def _safe_text(w: tk.Misc) -> str:
    try:
        return str(w.cget("text"))
    except Exception:
        return ""


def _first_text(root: tk.Misc, needle: str) -> tk.Misc | None:
    key = needle.lower()
    for w in _descendants(root):
        if _is_visible(w) and key in _safe_text(w).lower():
            return w
    return None


def _all_text(root: tk.Misc, words: list[str]) -> list[tk.Misc]:
    wanted = {w.strip().lower() for w in words}
    out = []
    for w in _descendants(root):
        if not _is_visible(w):
            continue
        txt = _safe_text(w).strip().lower()
        if txt in wanted:
            out.append(w)
    return out


def _first_canvas(root: tk.Misc) -> tk.Canvas | None:
    for w in _descendants(root):
        if isinstance(w, tk.Canvas) and _is_visible(w):
            return w
    return None


def _scroll_dialog(root: tk.Misc, fraction: float) -> None:
    canvas = _first_canvas(root)
    if canvas is None:
        return
    try:
        canvas.yview_moveto(fraction)
        root.update_idletasks()
        root.update()
        time.sleep(0.12)
    except Exception:
        pass


def _rel_box(capture: dict, w: tk.Misc, pad: int = 4) -> tuple[int, int, int, int] | None:
    if not _is_visible(w):
        return None
    try:
        x1 = w.winfo_rootx() - capture["x"] - pad
        y1 = w.winfo_rooty() - capture["y"] - pad
        x2 = w.winfo_rootx() - capture["x"] + w.winfo_width() + pad
        y2 = w.winfo_rooty() - capture["y"] + w.winfo_height() + pad
    except Exception:
        return None

    x1 = max(0, min(capture["w"] - 1, x1))
    y1 = max(0, min(capture["h"] - 1, y1))
    x2 = max(0, min(capture["w"], x2))
    y2 = max(0, min(capture["h"], y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return int(x1), int(y1), int(x2), int(y2)


def _union(capture: dict, widgets: list[tk.Misc], pad: int = 4) -> tuple[int, int, int, int] | None:
    boxes = [b for b in (_rel_box(capture, w, pad=pad) for w in widgets) if b is not None]
    if not boxes:
        return None
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _note(name: str, action: str, box: tuple[int, int, int, int] | None) -> dict | None:
    if box is None:
        return None
    return {"name": name, "action": action, "box": [int(v) for v in box]}


def _setup_notes(sp: SetupPage, cap: dict) -> list[dict]:
    widgets = [w for w in _descendants(sp) if _is_visible(w)]
    entries = [w for w in widgets if w.winfo_class() == "Entry" and w.winfo_width() > 220]
    entries.sort(key=lambda w: w.winfo_rooty())
    browse = [w for w in widgets if "browse" in _safe_text(w).lower()]
    browse.sort(key=lambda w: w.winfo_rooty())

    commit_btn = _first_text(sp, "Commit Defects to Coverity")
    pull_btn = _first_text(sp, "Pull from Coverity")
    start_btn = _first_text(sp, "Start Disposition")
    report_lbl = _first_text(sp, "Coverity Report")
    src_lbl = _first_text(sp, "Source Code Root")
    out_lbl = _first_text(sp, "Output Folder")

    notes: list[dict] = []
    if len(entries) >= 3:
        blocks = [
            ("Report input", "Select HTML report folder or pulled Excel file", [report_lbl, entries[0], pull_btn]),
            ("Source root", "Set source tree to load local code context", [src_lbl, entries[1]]),
            ("Output folder", "Choose where CSV and logs will be written", [out_lbl, entries[2]]),
            ("Commit path", "Use this button only when findings are not yet in Coverity Connect", [commit_btn]),
            ("Start analysis", "Run disposition after all required fields are set", [start_btn]),
        ]
        for name, action, ws in blocks:
            ws2 = [w for w in ws if w is not None]
            n = _note(name, action, _union(cap, ws2, pad=6))
            if n:
                notes.append(n)
    return notes


def _commit_notes(cm: CommitDefectsDialog, cap: dict) -> list[dict]:
    bin_lbl = _first_text(cm, "Coverity bin")
    idir_lbl = _first_text(cm, "Intermediate dir")
    host_lbl = _first_text(cm, "Host")
    port_lbl = _first_text(cm, "Port")
    user_lbl = _first_text(cm, "Username")
    pass_lbl = _first_text(cm, "Password")
    key_lbl = _first_text(cm, "Auth key file")
    connect = _first_text(cm, "Connect")

    conn_rows = [w.master for w in (host_lbl, port_lbl, user_lbl, pass_lbl, key_lbl) if w is not None]
    notes = [
        _note("Tool location", "Set Coverity bin only if cov-commit-defects is not on PATH", _union(cap, [w for w in [bin_lbl.master if bin_lbl else None] if w is not None], pad=6)),
        _note("Intermediate directory", "Select idir generated by cov-build and cov-analyze", _union(cap, [w for w in [idir_lbl.master if idir_lbl else None, cm._input_lbl] if w is not None], pad=6)),
        _note("Destination login", "Enter host and credentials, then click Connect", _union(cap, conn_rows + [w for w in [connect, cm._conn_lbl] if w is not None], pad=6)),
        _note("Project and stream", "Choose existing project and stream in Coverity Connect", _union(cap, [cm._proj_cb, cm._stream_cb], pad=6)),
        _note("Readiness and commit", "Resolve all red validation messages before committing", _union(cap, [cm._ready_lbl, cm._run_btn], pad=6)),
        _note("Commit output", "Use output log to diagnose command failures", _union(cap, [cm._log], pad=6)),
    ]
    return [n for n in notes if n is not None]


def _pull_notes(pull: PullDialog, cap: dict) -> list[dict]:
    host = _first_text(pull, "Host")
    port = _first_text(pull, "Port")
    user = _first_text(pull, "Username")
    pw = _first_text(pull, "Password")
    save = _first_text(pull, "Save path")

    conn_rows = [w.master for w in (host, port, user, pw) if w is not None]
    output_rows = [save.master] if save is not None else []
    notes = [
        _note("Connection block", "Enter host, port, username, and password", _union(cap, conn_rows + [pull._test_btn, pull._conn_lbl], pad=6)),
        _note("Project and stream", "Select project, stream, and defect limit", _union(cap, [pull._proj_cb, pull._stream_cb, pull._limit_spin], pad=6)),
        _note("Output file", "Confirm where pull Excel file will be saved", _union(cap, output_rows, pad=6)),
        _note("Pull and log", "Run pull and check progress log", _union(cap, [pull._pull_btn, pull._prog, pull._log], pad=6)),
    ]
    return [n for n in notes if n is not None]


def _analysis_notes(ap: AnalysisPage, cap: dict) -> list[dict]:
    notes = [
        _note("Progress", "Track percentage and processed defect count", _union(cap, [ap._pbar, ap._pbar_label, ap._pbar_stat], pad=6)),
        _note("Timing", "Use elapsed and ETC to estimate completion", _union(cap, [ap._pbar_time], pad=6)),
        _note("Analysis log", "Read warnings and per-defect decisions", _union(cap, [ap._log], pad=6)),
        _note("Cancel", "Cancel only when inputs are wrong", _union(cap, [ap._cancel_btn], pad=6)),
    ]
    return [n for n in notes if n is not None]


def _results_notes(rp: ResultsPage, cap: dict) -> list[dict]:
    top_bar = rp.winfo_children()[0] if rp.winfo_children() else None
    filter_btns = _all_text(top_bar, ["All", "Bug", "False positive", "Intentional", "Needs review", "Accepted"]) if top_bar else []
    push_top = _first_text(rp, "Push these to Coverity")

    evidence = [rp._detail_meta, rp._detail_comment]
    if _is_visible(rp._fix_box):
        evidence.extend([rp._fix_label, rp._fix_box])

    notes = [
        _note("Findings list", "Select CID cards by category", _union(cap, [rp._find_canvas], pad=6)),
        _note("Filters", "Narrow findings by classification and category", _union(cap, filter_btns, pad=6)),
        _note("Decision panel", "Review rationale and adjust disposition", _union(cap, evidence + [rp._open_btn, rp._accept_btn, rp._override_btn], pad=6)),
        _note("Source panel", "Validate line context before accept or override", _union(cap, [rp._code_box], pad=6)),
        _note("Direct push", "Open direct push for currently reviewed results", _union(cap, [w for w in [push_top] if w is not None], pad=6)),
    ]
    return [n for n in notes if n is not None]


def _detail_notes(dw: DetailWindow, cap: dict) -> list[dict]:
    top = dw.winfo_children()[0] if dw.winfo_children() else None
    accept_btn = _first_text(dw, "Accept Suggestion") or _first_text(dw, "Accepted")
    override_btn = _first_text(dw, "Override")
    source_box = _rel_box(cap, dw._code_box, pad=6)
    action_box = _union(cap, [w for w in [accept_btn, override_btn] if w is not None], pad=6)
    header_box = _rel_box(cap, top, pad=6) if top is not None else None

    analysis_box = None
    if source_box and action_box and header_box:
        analysis_box = (8, min(cap["h"] - 1, header_box[3] + 8), max(18, source_box[0] - 10), max(30, action_box[1] - 8))

    notes = [
        _note("Defect header", "Confirms CID, checker, and current classification", _union(cap, [w for w in [top] if w is not None], pad=6)),
        _note("Analysis and fix", "Read analyst comment and proposed fix", analysis_box),
        _note("Review actions", "Use Accept Suggestion or Override", _union(cap, [w for w in [accept_btn, override_btn] if w is not None], pad=6)),
        _note("Source code", "Cross-check highlighted line before final decision", _union(cap, [dw._code_box], pad=6)),
    ]
    return [n for n in notes if n is not None]


def _push_csv_notes(push: PushDialog, cap: dict) -> list[dict]:
    host = _first_text(push, "Host")
    port = _first_text(push, "Port")
    user = _first_text(push, "Username")
    pw = _first_text(push, "Password")
    browse = _first_text(push, "Browse")

    conn_rows = [w.master for w in (host, port, user, pw) if w is not None]
    csv_row = [browse.master] if browse is not None else []
    notes = [
        _note("Connection", "Connect before loading CSV", _union(cap, conn_rows + [push._test_btn, push._conn_lbl], pad=6)),
        _note("Project scope", "Select project, stream, and triage store", _union(cap, [push._proj_cb, push._stream_cb, push._store_cb], pad=6)),
        _note("CSV and validation", "Load final CSV and validate CIDs", _union(cap, csv_row + [push._validate_btn, push._csv_lbl, push._validate_lbl], pad=6)),
        _note("Defect table", "Review each row before push", _union(cap, [push._defect_tree], pad=6)),
        _note("Push button", "Push only when validation is clean", _union(cap, [push._push_btn], pad=6)),
    ]
    return [n for n in notes if n is not None]


def _direct_push_notes(dp: DirectPushDialog, cap: dict) -> list[dict]:
    host = _first_text(dp, "Host")
    port = _first_text(dp, "Port")
    user = _first_text(dp, "Username")
    pw = _first_text(dp, "Password")
    conn_rows = [w.master for w in (host, port, user, pw) if w is not None]

    mode_widgets = _all_text(dp, ["Accepted / overridden only", "Everything except 'Needs review'", "All analysed defects"])
    notes = [
        _note("Connection", "Enter credentials and connect", _union(cap, conn_rows + [dp._conn_btn, dp._conn_lbl], pad=6)),
        _note("Project and store", "Pick project and triage store", _union(cap, [dp._proj_cb, dp._store_cb], pad=6)),
        _note("Push mode", "Choose which reviewed defects will be pushed", _union(cap, mode_widgets + [dp._count_lbl], pad=6)),
        _note("Validation and table", "Validate CIDs and review mapped rows", _union(cap, [dp._validate_btn, dp._tree], pad=6)),
        _note("Push action", "Use Push to Coverity after validation", _union(cap, [dp._push_btn], pad=6)),
    ]
    return [n for n in notes if n is not None]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

    app = App()
    try:
        app.tk.call("tk", "scaling", 1.0)
    except Exception:
        pass

    app.update_idletasks()
    screen_w = app.winfo_screenwidth()
    screen_h = app.winfo_screenheight()
    width = max(1250, min(1500, screen_w - 30))
    height = max(820, min(950, screen_h - 70))
    app.geometry(f"{width}x{height}+20+20")
    app.update()

    annotations: dict[str, list[dict]] = {}

    sp = app._frames[SetupPage]
    sp._input_var.set(r"C:\Users\H565513.HONAERO\Documents\coverity_pull_CORE_EPP_EPIC_ATS_CORE-MASTER_20260824_223143.xlsx")
    sp._src_root_var.set(r"C:\ATS_CORE_COMMON")
    sp._output_var.set(r"C:\Users\H565513.HONAERO\Documents")
    app.show(SetupPage)
    app.update()
    cap = _shot(app, OUT / "01_setup_live.png")
    annotations["01_setup_live.png"] = _setup_notes(sp, cap)

    commit = CommitDefectsDialog(app, app)
    commit.geometry("1060x920+40+30")
    commit._sv_idir.set(r"C:\coverity\idir")
    commit._sv_host.set("coverity-er.honaero.com")
    commit._sv_port.set("443")
    commit._sv_desc.set("Coverity Tool commit")
    commit._refresh_ready()
    commit.update()
    cap = _shot(commit, OUT / "02_commit_live.png")
    annotations["02_commit_live.png"] = _commit_notes(commit, cap)
    commit.destroy()
    app.update()

    pull = PullDialog(app, app)
    pull.geometry("980x900+50+30")
    pull._sv_host.set("coverity-er.honaero.com")
    pull._sv_port.set("443")
    pull._sv_limit.set("5000")
    pull.update()
    _scroll_dialog(pull, 0.0)
    cap = _shot(pull, OUT / "03a_pull_top_live.png")
    annotations["03a_pull_top_live.png"] = _pull_notes(pull, cap)
    _scroll_dialog(pull, 1.0)
    cap = _shot(pull, OUT / "03b_pull_bottom_live.png")
    annotations["03b_pull_bottom_live.png"] = _pull_notes(pull, cap)
    pull.destroy()
    app.update()

    ap = app._frames[AnalysisPage]
    ap.lift()
    app._breadcrumb.configure(text="Analysing...")
    ap._pbar.stop()
    ap._pbar.configure(mode="determinate", maximum=100, value=9)
    ap._pbar_label.configure(text="7 / 73  -  analysing...")
    ap._pbar_stat.configure(text="9%  (7 / 73 defects)")
    ap._pbar_time.configure(text="Elapsed  0:00:12     ETC  0:01:35")
    ap._log_clear()
    ap._log_insert("info", "Using Excel file: coverity_pull_CORE_EPP_EPIC_ATS_CORE-MASTER_20260824_223143.xlsx\n")
    ap._log_insert("info", "Found 114 source files in C:/ATS_CORE_COMMON\n")
    ap._log_insert("ok", "Workspace indexed in 7.2s - starting per-defect analysis.\n")
    ap._log_insert("warn", "ID 3704139 [OVERRUN]  Bug\n")
    ap._log_insert("warn", "ID 3704169 [OVERRUN]  Bug\n")
    ap._log_insert("ok", "ID 3704314 [STRING_NULL]  False positive\n")
    app.update()
    cap = _shot(app, OUT / "04_analysis_live.png")
    annotations["04_analysis_live.png"] = _analysis_notes(ap, cap)

    app._results = _sample_results()
    app.show(ResultsPage)
    rp = app._frames[ResultsPage]
    app.update()
    rp._select_by_id(3704139)
    app.update()
    cap = _shot(app, OUT / "05_results_live.png")
    annotations["05_results_live.png"] = _results_notes(rp, cap)

    first = app._results[0]
    rp._open_detail_window(first)
    app.update()
    detail_win = None
    for w in app.winfo_children():
        if isinstance(w, tk.Toplevel):
            detail_win = w
    if detail_win is None:
        detail_win = DetailWindow(app, first, app, src_root="")
        app.update()
    if detail_win is not None:
        detail_win.geometry("1460x900+30+20")
        detail_win.update()
        cap = _shot(detail_win, OUT / "06_detail_live.png")
        annotations["06_detail_live.png"] = _detail_notes(detail_win, cap)
        detail_win.destroy()
        app.update()

    push = PushDialog(app, app)
    push.geometry("980x900+45+25")
    push._sv_host.set("coverity-er.honaero.com")
    push._sv_port.set("443")
    push._sv_user.set("j.doe")
    push._sv_pass.set("********")
    push._conn_lbl.configure(text="Not connected.", fg=C_FP)
    push._proj_cb.configure(values=["Engine_Control"], state="readonly")
    push._stream_cb.configure(values=["engine_main"], state="readonly")
    push._store_cb.configure(values=["Engine_Control-TS"], state="readonly")
    push._sv_csv.set(r"C:\Users\H565513.HONAERO\Documents\coverity_final_decisions.csv")
    push._csv_lbl.configure(text="Loaded CSV with 73 valid rows", fg=C_FP)
    push._validate_lbl.configure(text="Validate before push", fg=C_FP)
    try:
        push._defect_tree.delete(*push._defect_tree.get_children())
        for r in app._results[:8]:
            push._defect_tree.insert("", "end", iid=str(r["cid"]), values=(r["cid"], "", r["classification"], r.get("action", "Undecided"), r["comment"], r["checker"], r["file"]))
        push._push_btn.configure(state="normal")
    except Exception:
        pass
    push.update()
    _scroll_dialog(push, 0.0)
    cap = _shot(push, OUT / "07a_push_csv_top_live.png")
    annotations["07a_push_csv_top_live.png"] = _push_csv_notes(push, cap)
    _scroll_dialog(push, 1.0)
    cap = _shot(push, OUT / "07b_push_csv_bottom_live.png")
    annotations["07b_push_csv_bottom_live.png"] = _push_csv_notes(push, cap)
    push.destroy()
    app.update()

    direct = DirectPushDialog(app, app, app._results)
    direct.geometry("980x900+45+25")
    direct._sv_project.set("Engine_Control")
    direct._proj_cb.configure(values=["Engine_Control"], state="readonly")
    direct._store_cb.configure(values=["Engine_Control-TS"], state="readonly")
    direct._sv_store.set("Engine_Control-TS")
    direct._sv_mode.set("all")
    try:
        direct._refresh_preview()
        for row in direct._rows:
            row.server_cid = row.cid
        direct._validated = True
        direct._validate_lbl.configure(text="10 ready to push", fg=C_FP)
        direct._refresh_buttons()
    except Exception:
        pass
    direct.update()
    _scroll_dialog(direct, 0.0)
    cap = _shot(direct, OUT / "08a_direct_push_top_live.png")
    annotations["08a_direct_push_top_live.png"] = _direct_push_notes(direct, cap)
    _scroll_dialog(direct, 1.0)
    cap = _shot(direct, OUT / "08b_direct_push_bottom_live.png")
    annotations["08b_direct_push_bottom_live.png"] = _direct_push_notes(direct, cap)
    direct.destroy()

    app.destroy()

    META.write_text(json.dumps(annotations, indent=2), encoding="utf-8")
    print(f"Live screenshots generated in: {OUT}")
    print(f"Annotation map: {META}")


if __name__ == "__main__":
    main()
