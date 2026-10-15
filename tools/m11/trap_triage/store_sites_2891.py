#!/usr/bin/env python3
# #2891: store_sites_2672.py の一般化。wasm-opt --instrument-memory の計装版 wat から、
# store 計装 id -> (wasm 関数 index, wat 行, bytes, offset) を作る。store_ptr の import 番号は wat から引く
# (build ごとに import 番号が変わるため固定しない)。
# 入力: <instr.wat>  出力: <out.json>。計装版 wat・出力は work/ 以下に置き commit しない。
import json, re, sys

src, out = sys.argv[1], sys.argv[2]
lines = open(src, encoding='utf-8').read().split('\n')
imp = [re.search(r'\(func \$(fimport\$\d+)', ln) for ln in lines if '"store_ptr"' in ln]
imp = [m.group(1) for m in imp if m]
if len(imp) != 1:
    sys.exit('store_ptr の import が 1 件でない: %d' % len(imp))
call_re = re.compile(r'\(call \$' + re.escape(imp[0]) + r'\b')
func_re = re.compile(r'^ \(func \$(\d+)\b')
exp_re = re.compile(r'^ \(export "([^"]+)" \(func \$(\d+)\)\)')
sites = {}
exports = {}
cur = None
for i, ln in enumerate(lines):
    m = func_re.match(ln)
    if m:
        cur = int(m.group(1))
    m = exp_re.match(ln)
    if m:
        exports.setdefault(int(m.group(2)), m.group(1))
    if call_re.search(ln):
        vals = []
        j = i + 1
        while len(vals) < 3 and j < len(lines):
            mm = re.search(r'\(i32\.const (-?\d+)\)', lines[j])
            if mm:
                vals.append(int(mm.group(1)))
            j += 1
        sid, nbytes, off = vals
        sites.setdefault(sid, []).append({'func': cur, 'line': i + 1, 'bytes': nbytes, 'offset': off})
dup = {k: v for k, v in sites.items() if len(v) > 1}
json.dump({'import': imp[0], 'n_ids': len(sites), 'n_dup_ids': len(dup), 'exports': {str(k): v for k, v in exports.items()},
           'sites': {str(k): v for k, v in sites.items()}}, open(out, 'w'))
print(json.dumps({'import': imp[0], 'n_ids': len(sites), 'n_dup_ids': len(dup), 'n_exports': len(exports)}))
