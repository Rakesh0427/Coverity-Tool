import py_compile, os
fp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "coverity_soap_client.py")
try:
    py_compile.compile(fp, doraise=True)
    print("Syntax OK")
except py_compile.PyCompileError as e:
    print("Syntax error:", e)

