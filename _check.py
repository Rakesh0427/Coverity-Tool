import ast
path = r'C:\Users\H565513.HONAERO\Coverity_v3_stable_version\Coverity_Tool\heuristic_analyzer.py'
src = open(path, encoding='utf-8').read()
try:
    ast.parse(src)
    print('Syntax OK')
except SyntaxError as e:
    print(f'Line {e.lineno}: {e.msg}')
    print(e.text)
