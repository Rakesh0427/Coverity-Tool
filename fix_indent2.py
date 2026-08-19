import py_compile
p=r"coverity_triage.py"
L=open(p,encoding="utf-8").read().splitlines(keepends=True)
# Line 461 is index 460. Force its indentation to 12 spaces (align with loop body at depth 3 inside try).
i=460
cur=L[i]
indent="            "
L[i]=indent+cur.lstrip()+"\n"
open(p,"w",encoding="utf-8").writelines(L)
py_compile.compile(p,doraise=True)
print("FIXED line461 indent; COMPILE_OK")
