#!/usr/bin/env python3
"""m11_postjs.py: emcc 生成 m11_boot.cjs の '.'-含み stub 名補正 (sanitizer).

emcc の stub table (`function _X.1`) と wasmImports key (`X.1: ...`) は
IR 側 '.'-suffix 名 (e.g. SHGetFolderPathW.1) から JS 変数名にそのまま
展開され Node 26 parser で SyntaxError になる. stub 関数名を JS-safe 変数名
に sanitize し, wasmImports key は quoted にして wasm import 名 (実 IR 名)
を保つ.
"""
import os, re, sys

path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'work', 'm11_boot.cjs')
s = open(path).read()


def fix(js):
    names = sorted(set(re.findall(r"function _([A-Za-z_]\w*\.\d+)\(", js)))
    fixed = js
    mapping = {}
    for n in names:
        jsname = '_' + n.replace('.', '_')
        fixed = fixed.replace('function _%s(' % n, 'function %s(' % jsname)
        fixed = fixed.replace('_%s.stub = true;' % n, '%s.stub = true;' % jsname)
        fixed = fixed.replace('%s: _%s,' % (n, n), "'%s': %s," % (n, jsname))
        # `Module['_X.1']` / createExportWrapper 参照があれば同様に変数化
        fixed = fixed.replace("Module['_%s']" % n, "Module['%s']" % jsname)
        mapping[n] = jsname
    return fixed, mapping


fixed, mapping = fix(s)
open(path, 'w').write(fixed)
if mapping:
    sys.stderr.write('[m11post] sanitized stub names: %s\n' % ', '.join(mapping))
else:
    sys.stderr.write('[m11post] no dot-stub found (already clean)\n')
