# Corroboration backend: cppcheck

The tool optionally corroborates each defect with a second, independent static
analyzer. After a defect (e.g. a Coverity `BUFFER_SIZE` finding) is anchored
to a source line, the tool runs **cppcheck** on that file; if a cppcheck
finding lands within ±3 lines of the defect line, its check id is recorded as
independent confirmation and shown in the triage evidence and comments.

## Why cppcheck

- **Official and actively maintained** — the dedicated open-source C/C++
  static analyzer (<https://github.com/danmar/cppcheck>), regular 2.x
  releases, not a fork or an abandoned tool.
- **100 % local and offline** — its rules are compiled into the binary; no
  registry, no network, no account. It works in air-gapped environments and
  inside the frozen Windows exe.
- **Purpose-built for this tool's defect set** — buffer overflows, `strcpy`/
  `memcpy` misuse, double-free, null dereference, uninitialized memory, leaks.
  The check ids map directly onto Coverity checker families
  (`bufferAccessOutOfBounds` ↔ `BUFFER_SIZE`, `doubleFree` ↔ `DOUBLE_FREE`,
  `nullPointer` ↔ `NULLPTR_DEREF`, …).
- **Fast** — a native binary; a single-file scan is typically 0.1–1 s, so the
  per-file cache makes corroboration nearly free.
- **Available as a library** — `pip install cppcheck` installs a wheel that
  bundles the official cppcheck 2.17.1 binary and exposes a Python API
  (`cppcheck.get_cppcheck_dir()`). No PATH changes, no separate installer;
  `pip install -r requirements.txt` is all that is needed, and the binary can
  be bundled into the exe (see `CoverityTool.spec` / `build_exe.bat`).

## How it is wired in

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
   one parser works on every supported version. Findings are read from both
   stdout and stderr (cppcheck writes findings to stderr). Findings within ±3
   lines of the defect line corroborate it; the check id (e.g.
   `bufferAccessOutOfBounds`) becomes `ctx['corrob_rule']`.
3. `decision_agent.py` and `deep_analyzer.py` use `corrob_rule` for the
   `corrob_confirms` evidence and the "(cppcheck `rule` confirms.)" comment
   suffix.

## Binary discovery order

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

## Environment variables

| Variable | Meaning |
|---|---|
| `COVERITY_DISABLE_CPPCHECK=1` | Turn corroboration off. |
| `COVERITY_CPPCHECK_BIN` | Explicit path to the cppcheck binary. |
| `COVERITY_CPPCHECK_TIMEOUT` | Per-file scan timeout in seconds (default 15). |
| `COVERITY_CPPCHECK_ARGS` | Extra CLI args, e.g. `--check-level=exhaustive --std=c++17`. |
| `COVERITY_CPPCHECK_PROBE_TIMEOUT` | Probe timeout in seconds (default 10). |

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

## Example output

Capability banner (`python capabilities.py`):

```
Analysis backends:
  tree-sitter (AST)           OK       v?, grammars: c+cpp
  libclang (types/macros)     OK       auto-discovered
  z3 (SMT path proofs)        OK       v4.12.6
  flow_analysis (CFG)         OK       builtin
  cppcheck (corroboration)    OK       Cppcheck 2.17.1 from cppcheck-wheel 1.5.1
  ...
  → analysis depth: FULL
```

Generated disposition comment suffix when cppcheck independently confirms a
defect:

```
... Buffer 'dst' can overflow ... (cppcheck `bufferAccessOutOfBounds` confirms.)
```

Decision-agent evidence row:

```
corrob_confirms  (bug, weight 0.45): Cppcheck rule bufferAccessOutOfBounds
independently confirms finding.
```
