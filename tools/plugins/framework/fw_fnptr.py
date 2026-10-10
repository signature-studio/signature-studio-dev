#!/usr/bin/env python3
"""fw_fnptr.py — 関数ポインタ型 `RET ()*` を `ptr` に正規化する (m5 ir5 の parse_functions が
`define i32 ()* @f(...)` 形を取りこぼすため; 対象は GetProcAddress 系 IAT thunk の 3 define ほか)。

  python3 fw_fnptr.py IN.ll OUT.ll
"""
import re, sys

t = open(sys.argv[1], errors='replace').read()
n = len(re.findall(r'\b(?:i\d+|void|ptr|float|double) \(\)\* ', t))
t = re.sub(r'\b(?:i\d+|void|ptr|float|double) \(\)\* ', 'ptr ', t)
open(sys.argv[2], 'w').write(t)
print('[fnptr] normalized: %d' % n)
