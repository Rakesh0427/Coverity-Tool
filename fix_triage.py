import py_compile
p=r"coverity_triage.py"
s=open(p,encoding="utf-8").read()

# Fix over-indented row_dimensions line.
s=s.replace(
  "                                                ws.row_dimensions[1].height = 22",
  "            ws.row_dimensions[1].height = 22")

# Collapse trailing blank lines before disposition block.
s=s.replace(
  '            COMMENT_MAX_LINES = 12   # cap so the block never consumes full height\n\n\n\n            # ---- Disposition fill colours ----',
  '            COMMENT_MAX_LINES = 12   # cap so the block never consumes full height\n\n            # ---- Disposition fill colours ----')

open(p,'w',encoding="utf-8").write(s)
print("fixed row_dimensions + blanks; len", len(s))
py_compile.compile(p, doraise=True)
print("TRIAGE_COMPILE_OK")

