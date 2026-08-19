path = r'C:\Users\H565513.HONAERO\Coverity_v3_stable_version\Coverity_Tool\heuristic_analyzer.py'
with open(path, 'rb') as f:
    raw = f.read()

# Print bytes around the problematic area  
text = raw.decode('utf-8')
idx = text.find('md = re.search')
if idx >= 0:
    snippet = text[idx:idx+120]
    print("Found at offset", idx)
    print(repr(snippet))
else:
    print("Pattern not found")
    # search for destination
    idx2 = text.find('destination')
    print("'destination' at:", idx2)
    if idx2 >= 0:
        print(repr(text[idx2-30:idx2+100]))
