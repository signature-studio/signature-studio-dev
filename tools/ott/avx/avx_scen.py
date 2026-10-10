#!/usr/bin/env python3
"""avx_scen.py — CAB-135: AVX/VEX 経路に到達させる scenario (entry_scen/crt_scen の step 形式を流用)。

AVX_FORCE=1 (fma+isa 強制) の native/wasm で実行し、以下の VEX 経路を実際に走らせる:
  - fma_p025 / fma_mix : CRT 数学 kernel (0x1801a9be0 系 11 種) の __use_fma3 分岐 →
    processReplacing 中の exp/log/pow が FMA 経路を通る (param 値を変えて多様な入力域)
  - avx_proc_2k / avx_proc_8k : 大块 n の processReplacing → memmove (0x1801a2a20) の
    __isa_available>=3 かつ 0x2000<len<0x180000 の ymm copy 経路 (vmovdqu ymm / vmovntdq)
  - fma_big : 上記の複合 (FMA + 大块)

native 実機械語との突合は entry runner の schema (rax / buf / obj / alog) で行う。
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'entry'))
from entry_scen import RVA, STR, N  # noqa: E402


def scen_list():
    S = []

    def base(name, calls):
        S.append((name, [{'c': 'vstmain'}] + calls))

    proc = lambda n: [{'c': 'disp', 'op': 12, 'idx': 0, 'val': 1, 'buf': 0},
                      {'c': 'proc', 'n': n},
                      {'c': 'disp', 'op': 12, 'idx': 0, 'val': 0, 'buf': 0}]

    # --- FMA 経路: 既定 param / 一様値 / mix (CRT 数学 kernel の入力域を広げる) ---
    base('fma_def', proc(N))
    base('fma_p025', [{'c': 'setp', 'idx': i, 'fv': 0.25} for i in range(19)] + proc(N))
    base('fma_p075', [{'c': 'setp', 'idx': i, 'fv': 0.75} for i in range(19)] + proc(N))
    base('fma_mix', [{'c': 'setp', 'idx': i, 'fv': v} for i, v in
                     [(0, 0.1), (1, 0.9), (2, 0.335), (3, 0.7), (4, 0.5), (5, 0.05), (6, 0.95),
                      (7, 0.2), (8, 0.8), (9, 0.123), (10, 0.456), (16, 0.789), (17, 0.3), (18, 0.6)]] + proc(N))
    base('fma_zero', [{'c': 'setp', 'idx': i, 'fv': 0.0} for i in range(19)] + proc(N))

    # --- 大块 processReplacing (memmove ymm 経路: n*4 byte が 0x2000 超え) ---
    base('avx_proc_2k', proc(2048))
    base('avx_proc_8k', proc(8192))

    # --- 複合: FMA + 大块 + 表示 (entry 突合の全要素) ---
    base('fma_big', [{'c': 'setp', 'idx': i, 'fv': 0.335} for i in range(19)] +
                     [{'c': 'virt', 'rva': RVA['pdisplay'], 'rdx': i, 'r8': STR, 'buf': 1} for i in (0, 5, 9)] +
                     proc(4096))
    # --- 大块 2 block (連続 proc で state が乗る) ---
    base('avx_proc_4k_x2', proc(4096) + proc(4096))
    return S


if __name__ == '__main__':
    json.dump([{'name': n, 'steps': s} for n, s in scen_list()], open(sys.argv[1], 'w'))
    print('[avx_scen] scenarios', len(scen_list()))
