path = r'C:\Users\H565513.HONAERO\Coverity_v3_stable_version\Coverity_Tool\heuristic_analyzer.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# In Python 3.12+, r"...['" ] is parsed differently.
# Fix: replace r"..." regexes containing ['"...] with r'...' using escaped quotes.
fixes = [
    (
        r"""r"destination\s+(?:array|buffer|string)?\s*['"]([^'"]+)['"]" """.strip(),
        r"""r'destination\s+(?:array|buffer|string)?\s*[\'"]([^\'"]+)[\'"]\' """.strip(),
    ),
    (
        r"""r"source\s+(?:array|buffer|string)?\s*['"]([^'"]+)['"]" """.strip(),
        r"""r'source\s+(?:array|buffer|string)?\s*[\'"]([^\'"]+)[\'"]\' """.strip(),
    ),
]

# Simpler: just find the lines and replace the outer quote style
lines = content.split('\n')
new_lines = []
for line in lines:
    stripped = line.strip()
    if stripped.startswith('md = re.search(r"destination') or stripped.startswith('ms = re.search(r"source'):
        # Change r"..." to r'...' style - swap the outer quote of the string
        # The pattern is: r"CONTENT", desc)
        # Find start of r" and end "
        idx = line.index('r"')
        # Find the closing " after r"
        end = line.rindex('"', idx+2)
        inner = line[idx+2:end]
        # Build new line with single quotes
        new_line = line[:idx] + "r'" + inner.replace("'", "\\'") + "'" + line[end+1:]
        new_lines.append(new_line)
        print(f"Fixed: {line.strip()}")
        print(f"   To: {new_line.strip()}")
    else:
        new_lines.append(line)

with open(path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(new_lines))

print("Done.")
