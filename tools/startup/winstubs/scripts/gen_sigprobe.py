#!/usr/bin/env python3
"""IR の `declare` から api_matrix.tsv の API だけを抜き、各 API を 1 回呼ぶ最小 .ll を生成する (argv: in.ll out.ll)。
IR 側の関数型で call するため、定義側 (winstubs/shimx) の wasm 署名と食い違えば wasm-ld が signature mismatch を出す。"""
import re, sys, os, csv
here = os.path.dirname(os.path.abspath(__file__))
apis = [r[0] for r in csv.reader(open(os.path.join(here, '..', 'data', 'api_matrix.tsv')), delimiter='\t') if r and not r[0].startswith('#')]
want = set(apis)
decl = {}
pat = re.compile(r'^declare\s+(?P<attrs>(?:[\w]+\s+)*?)(?P<ret>void|i\d+|ptr|float|double|%\w+)\s+@(?P<name>[\w$.]+)\((?P<args>.*?)\)\s*(?P<tail>[^{]*)$')
for line in open(sys.argv[1], errors='replace'):
    if not line.startswith('declare '): continue
    m = pat.match(line.rstrip('\n'))
    if not m or m.group('name') not in want: continue
    decl[m.group('name')] = (m.group('ret'), m.group('args'))
out = ['target triple = "wasm32-unknown-emscripten"', '']
calls = []
for name, (ret, args) in sorted(decl.items()):
    # 引数型だけ取り出す (属性は落とす)
    tys = []
    depth = 0; cur = ''
    for ch in args + ',':
        if ch in '({[<': depth += 1
        if ch in ')}]>': depth -= 1
        if ch == ',' and depth == 0:
            t = cur.strip().split()
            if t: tys.append(t[0])
            cur = ''
        else: cur += ch
    out.append('declare %s @%s(%s)' % (ret, name, ', '.join(tys)))
    a = ', '.join('%s %s' % (t, 'null' if t == 'ptr' else ('0' if t.startswith('i') else '0.0')) for t in tys)
    calls.append('  call %s @%s(%s)' % (ret, name, a))
out.append('')
out.append('define void @sigprobe_main() {')
out += calls
out.append('  ret void')
out.append('}')
open(sys.argv[2], 'w').write('\n'.join(out) + '\n')
print('IR declare のうち api_matrix 掲載 %d / %d 本 (matrix は Win32 API 以外を含む)' % (len(decl), len(want)))
print('IR 未 declare: ' + ', '.join(sorted(want - set(decl))))
