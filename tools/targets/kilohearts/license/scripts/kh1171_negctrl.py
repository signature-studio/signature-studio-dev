#!/usr/bin/env python3
"""kh1171_negctrl.py — #710 named import 節の閉包入力ネガコン (#1171)。

  python3 scripts/kh1171_negctrl.py <tag> pos|neg <VA>[,VA...]

pos: 宣言補完 (decl_named_imports) ありで build。neg: 宣言補完を無効化して build。
出力は work/kh1171/<tag>/ (gitignore)。要 素材 (winpkg/HeartCore.core_64)・emsdk・retdec。
KH_EM_CACHE に読取専用でない cache を指定する場合は環境変数で与える。"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LIC = os.path.dirname(HERE)
sys.path.insert(0, LIC)
import lic_build as lb  # noqa: E402

tag, mode = sys.argv[1], sys.argv[2]
vas = {int(v, 16) for v in sys.argv[3].split(',')}
if mode == 'neg':
    lb.decl_named_imports = lambda txt: txt
t = time.time()
try:
    st = lb.build(vas, os.path.join(LIC, 'work', 'kh1171', tag), tag, apply_stub=False)
    print('RESULT', mode, 'rc=0', json.dumps({k: v for k, v in st.items() if k in ('wasm_sha256', 'undefined_imports', 'stubs', 'emcc_sec', 'wasm_bytes')}, ensure_ascii=False), 'total_sec', round(time.time() - t, 1))
except SystemExit as e:
    print('RESULT', mode, 'SystemExit', str(e)[:300], 'total_sec', round(time.time() - t, 1))
