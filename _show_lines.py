import sys
path = r'C:\Users\H565513.HONAERO\Coverity_v3_stable_version\Coverity_Tool\heuristic_analyzer.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Line numbers are 1-based; lines 143 and 146 are the broken ones
# Print them to verify
for i, ln in enumerate(lines[140:150], 141):
    print(i, repr(ln))
