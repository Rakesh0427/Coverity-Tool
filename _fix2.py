path = r'C:\Users\H565513.HONAERO\Coverity_v3_stable_version\Coverity_Tool\heuristic_analyzer.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

out = []
for line in lines:
    # Fix lines with r"...['"]..." pattern (double-quote delimited raw string with mixed quotes inside char class)
    # Change to triple-quoted raw strings
    if 'r"destination' in line and "['" in line:
        line = line.replace(
            'r"destination\\s+(?:array|buffer|string)?\\s*[\'\"]([^\'\"]+)[\'\"]"',
            'r"""destination\\s+(?:array|buffer|string)?\\s*[\'\"]([^\'\"]+)[\'\"]"""'
        )
        # Also try with actual characters
        old = 'r"destination\s+(?:array|buffer|string)?\s*[\'"' + ']([^\'"]+)[\'"' + ']"'
        new = 'r"""destination\s+(?:array|buffer|string)?\s*[\'"' + ']([^\'"]+)[\'"' + ']"""'
        line = line.replace(old, new)
    if 'r"source' in line and "['" in line:
        old = 'r"source\s+(?:array|buffer|string)?\s*[\'"' + ']([^\'"]+)[\'"' + ']"'
        new = 'r"""source\s+(?:array|buffer|string)?\s*[\'"' + ']([^\'"]+)[\'"' + ']"""'
        line = line.replace(old, new)
    out.append(line)

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(out)

# Verify
import py_compile
try:
    py_compile.compile(path, doraise=True)
    print("Syntax OK!")
except py_compile.PyCompileError as e:
    print(f"Still broken: {e}")
