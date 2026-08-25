"""Tests for the libclang translation-unit context.

libclang used to be handed the extracted function body in an empty temp file
with no include paths::

    tu = idx.parse(tmp, args=['-std=c11'])

With no project headers visible, most types were unknown, CONSTANTARRAY never
resolved, and ``get_array_size()`` returned ``(0, '')`` -- so the regex
fallback did all the work and the library was effectively inert.

These tests cover the plumbing that fixes it.  They do not require libclang to
be installed: the context/include-discovery logic is pure, and the parse-level
assertions skip when the shared library is absent.
"""
import os

import pytest

import clang_resolver as cr


@pytest.fixture(autouse=True)
def _reset_context():
    yield
    cr.set_translation_context('')
    cr.clear_tu_cache()


requires_libclang = pytest.mark.skipif(
    not cr._clang_available(), reason="libclang shared library not installed")


# --------------------------------------------------------------------------- #
# include discovery
# --------------------------------------------------------------------------- #
def test_discovers_directories_containing_headers(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.c").write_text("int main(void){return 0;}")
    (tmp_path / "include").mkdir()
    (tmp_path / "include" / "api.h").write_text("#define MAX 8\n")

    dirs = cr.discover_include_dirs(str(tmp_path))
    assert str(tmp_path / "include") in dirs
    # A directory with only .c files is not an include candidate.
    assert str(tmp_path / "src") not in dirs


def test_conventional_include_dirs_are_ranked_first(tmp_path):
    for name in ("zzz_other", "include"):
        d = tmp_path / name
        d.mkdir()
        (d / "h.h").write_text("/* header */")

    dirs = cr.discover_include_dirs(str(tmp_path))
    inc = dirs.index(str(tmp_path / "include"))
    other = dirs.index(str(tmp_path / "zzz_other"))
    assert inc < other, "include/ must survive the cap on large trees"


def test_build_directories_are_skipped(tmp_path):
    build = tmp_path / "build"
    build.mkdir()
    (build / "generated.h").write_text("/* generated */")
    assert str(build) not in cr.discover_include_dirs(str(tmp_path))


def test_discovery_is_bounded(tmp_path):
    for i in range(15):
        d = tmp_path / f"d{i}"
        d.mkdir()
        (d / "h.h").write_text("/* h */")
    assert len(cr.discover_include_dirs(str(tmp_path), limit=5)) <= 5


def test_discovery_tolerates_a_missing_root():
    assert cr.discover_include_dirs("/nonexistent/path/xyz") == []


# --------------------------------------------------------------------------- #
# translation context
# --------------------------------------------------------------------------- #
def test_context_round_trips(tmp_path):
    f = tmp_path / "a.c"
    f.write_text("int a;")
    cr.set_translation_context(str(f), [str(tmp_path)], ['-DFOO=1'])
    assert cr._TU_FILE == str(f)
    assert cr._INCLUDE_DIRS == (str(tmp_path),)
    args = cr._build_args()
    assert '-I' in args and str(tmp_path) in args
    assert '-DFOO=1' in args


def test_clearing_context_restores_snippet_mode():
    cr.set_translation_context('')
    assert cr._TU_FILE is None
    assert cr._INCLUDE_DIRS == ()


def test_args_tolerate_missing_system_headers():
    """A partial AST with real project types beats a regex guess."""
    assert '-ferror-limit=0' in cr._build_args()


def test_cpp_files_get_a_cpp_standard():
    assert '-std=c++14' in cr._build_args(for_cpp=True)
    assert '-std=c11' in cr._build_args(for_cpp=False)


def test_parse_real_file_returns_none_without_context():
    cr.set_translation_context('')
    assert cr.parse_real_file() is None


def test_parse_real_file_returns_none_for_a_missing_file():
    assert cr.parse_real_file('/nonexistent/file.c') is None


# --------------------------------------------------------------------------- #
# parsing with real headers (skipped when libclang is absent)
# --------------------------------------------------------------------------- #
@requires_libclang
def test_array_size_resolves_via_a_header_macro(tmp_path):
    """The size constant lives in a header the snippet never contains."""
    (tmp_path / "limits_cfg.h").write_text("#define MAX_CONN 16\n")
    src = tmp_path / "mod.c"
    src.write_text('#include "limits_cfg.h"\n'
                   'static int g_table[MAX_CONN];\n'
                   'int use(int i) { return g_table[i]; }\n')

    cr.set_translation_context(str(src), cr.discover_include_dirs(str(tmp_path)))
    size, expr = cr.get_array_size("int use(int i) { return g_table[i]; }",
                                   "g_table")
    assert size > 0, "array size should resolve from the real translation unit"


@requires_libclang
def test_macro_expands_from_a_project_header(tmp_path):
    (tmp_path / "cfg.h").write_text("#define BUF_LEN 64\n")
    src = tmp_path / "mod.c"
    src.write_text('#include "cfg.h"\nchar buf[BUF_LEN];\n')

    cr.set_translation_context(str(src), cr.discover_include_dirs(str(tmp_path)))
    # The snippet does not contain the #define; only the real TU has it.
    assert cr.expand_macro("char buf[BUF_LEN];", "BUF_LEN") == 64


@requires_libclang
def test_translation_units_are_cached(tmp_path):
    src = tmp_path / "m.c"
    src.write_text("int x;")
    cr.set_translation_context(str(src), [])
    assert cr.parse_real_file() is cr.parse_real_file()
    cr.clear_tu_cache()
