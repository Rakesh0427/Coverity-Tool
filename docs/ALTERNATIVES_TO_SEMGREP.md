# Replacing Semgrep: the corroboration backend

Semgrep was used as a **corroboration backend** — after a defect (e.g. a Coverity
`BUFFER_SIZE` finding) is anchored to a source line, the tool ran semgrep on that
file and, if a rule hit within ±3 lines of the defect line, recorded it as
independent confirmation (shown as *"X independently confirms finding"* in the
triage evidence and comments).

Semgrep proved to be a bad fit:

| Problem | Detail |
|---|---|
| Needs the online registry | `semgrep --config p/c-and-cpp` downloads rules from the Semgrep Registry. Offline machines (and air-gapped corporate desktops) get nothing. |
| Never worked in the shipped exe | The Windows build (PyInstaller) cannot ship the `semgrep` CLI, so `shutil.which("semgrep")` fails and corroboration silently never runs. |
| Heavy | 2–30 s per file on a cold cache; a huge Python dependency tree pinned as `semgrep==1.45.0`. |
| Wrong focus | Its C/C++ coverage is "limited" compared with C/C++-native tools, and this tool's defects are C/C++ buffer/memory issues. |

## Decision: cppcheck

**cppcheck** (the official open-source C/C++ static analyzer,
<https://github.com/danmar/cppcheck>) is the replacement. It is:

- **Official and actively maintained** — a dedicated project with regular
  releases (2.x line), not a fork or an abandoned tool.
- **100 % local and offline** — its rules are compiled into the binary; no
  registry, no network, no account. It works in air-gapped environments and
  inside the frozen Windows exe.
- **Purpose-built for this tool's defect set** — buffer overflows, `strcpy`/
  `memcpy` misuse, double-free, null dereference, uninitialized memory, leaks.
  The check IDs map directly onto Coverity checker families
  (`bufferAccessOutOfBounds` ↔ `BUFFER_SIZE`, `doubleFree` ↔ `DOUBLE_FREE`,
  `nullPointer` ↔ `NULLPTR_DEREF`, …).
- **Fast** — a native binary; a single-file scan is typically 0.1–1 s, so the
  per-file cache makes corroboration nearly free.
- **Available as a library** — `pip install cppcheck` installs a wheel that
  bundles the official cppcheck 2.17.1 binary and exposes a Python API
  (`cppcheck.get_cppcheck_dir()`). No PATH changes, no separate installer;
  `pip install -r requirements.txt` is all that is needed, and the binary can
  be bundled into the exe (see `CoverityTool.spec` / `build_exe.bat`).

### How it is wired in

1. `capabilities.py` probes `cppcheck --version` (cached, one per process) and
   shows it in the capability banner:
   `cppcheck (corroboration) OK  Cppcheck 2.17.1`.
2. `heuristic_analyzer.py` runs, per source file (cached), at most once:

   ```
   cppcheck --enable=warning,style,performance,portability --quiet \
            --template='{line}|{id}|{severity}|{message}' <file>
   ```

   The pipe-separated template output is stable across cppcheck 2.x (the
   `--json` format changed between releases and was removed in newer ones), so
   one parser works on every supported version. Findings within ±3 lines of
   the defect line corroborate it; the check id (e.g.
   `bufferAccessOutOfBounds`) becomes `ctx['corrob_rule']`.
3. `decision_agent.py` and `deep_analyzer.py` use `corrob_rule` for the
   `corrob_confirms` evidence and the "(cppcheck `rule` confirms.)" comment
   suffix.

### Binary discovery order

`capabilities.find_cppcheck_bin()` tries, in order:

1. `COVERITY_CPPCHECK_BIN` (explicit override; if set but broken, it fails —
   no silent fallback);
2. `cppcheck` on `PATH` (official install via package manager / release
   archive);
3. frozen-exe locations: `cppcheck.exe` next to `CoverityTool.exe`,
   `sys._MEIPASS/cppcheck.exe`, and the `cppcheck/Cppcheck/` data bundled by
   `CoverityTool.spec`;
4. the pip wheel's bundled binary via `import cppcheck` →
   `cppcheck.get_cppcheck_dir()`.

## Alternatives considered (and why not)

| Tool | Verdict |
|---|---|
| **Opengrep** (community fork of Semgrep CE) | Closest drop-in (same rule syntax), but still an OCaml CLI needing downloaded rule packs — same offline/embedded problems; a community consortium rather than a single official project. |
| **CodeQL (GitHub)** | Deeper semantic analysis, but a heavyweight Java-engine CLI, no Python library, slow database builds, and licensing restricts free use to public repositories/research. |
| **clang-tidy (LLVM)** | Official and offline, but needs a compile database for accurate results, is binary-only, and is heavier to install than cppcheck; without a CDB it cannot resolve the C/C++ code reliably. |
| **Flawfinder** | The only C/C++ analyzer that is a pure-Python importable module — but regex-based (no AST), dated and noisy; weak corroboration compared with cppcheck's semantic checks. |
| **Infer (Meta)** | Good null/leak detection but an OCaml binary, slow on large trees, and needs build commands — overkill for per-file corroboration. |
| **Bandit / gosec / Brakeman** | Language-specific (Python/Go/Ruby) — this tool analyzes C/C++. |

## Environment variables

| Variable | Meaning |
|---|---|
| `COVERITY_DISABLE_CPPCHECK=1` | Turn corroboration off (new primary flag). |
| `COVERITY_DISABLE_SEMGREP=1`, `COVERITY_ENABLE_SEMGREP=0` | **Legacy aliases** — still disable corroboration so old scripts keep working. |
| `COVERITY_CPPCHECK_BIN` | Explicit path to the cppcheck binary. |
| `COVERITY_CPPCHECK_TIMEOUT` | Per-file scan timeout in seconds (default 15). |
| `COVERITY_CPPCHECK_ARGS` | Extra CLI args, e.g. `--check-level=exhaustive --std=c++17`. |
| `COVERITY_CPPCHECK_PROBE_TIMEOUT` | Probe timeout in seconds (default 10; legacy `COVERITY_SEMGREP_PROBE_TIMEOUT` also honoured). |

## Installing cppcheck

```bash
# Preferred: library-form install (bundles the official binary)
pip install cppcheck          # or: pip install -r requirements.txt

# Alternative: official binary from a package manager / cppcheck releases
sudo apt install cppcheck     # Debian/Ubuntu
brew install cppcheck         # macOS
choco install cppcheck        # Windows
```

The Windows exe build (`build_exe.bat` + `CoverityTool.spec`) bundles the
wheel's `cppcheck.exe` automatically, so corroboration works in the shipped
product with no extra user setup.
