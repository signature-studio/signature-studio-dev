#!/usr/bin/env python3
"""crt_roots.py — CAB-138: CRT 初期化版 lift の entries.json を作る。

entry_roots.py (CAB-137) の出力 + CRT 関係の追加:
  roots  += UCRT 数學エラー経路 (_handle_error d/f, sqrt wrapper d/f — 旧 override 4 件の実体)
         += audioMaster/CRT trampoline 群 (override 先)
  calltgt += DSP/entry coverage の和集合 (引数で受ける)

usage: crt_roots.py DSP_COV.json ENTRY_COV.json OUT.json
"""
import json
import os
import sys

IMG = 0x180000000

# GetProcAddress が返す API の trampoline (wasm)。native は実 C 関数ポインタを返す。
# VA は image 末尾パディング (.rsrc 領域内, data_gen も jump table 窓も使わない)。
TRAMP = {
    0x1802f9000: 'ovr_fls_alloc',
    0x1802f9010: 'ovr_fls_free',
    0x1802f9020: 'ovr_fls_get',
    0x1802f9030: 'ovr_fls_set',
    0x1802f9040: 'ovr_cs_ex',
    0x1802f9050: 'ovr_gstpaft',
}

# 旧 override 4 件の実体を lift して置換する (CAB-137 時点では C 実装に差し替えられていた)
CRT_REAL = [
    0x1801c8c00,  # _handle_error(double)  — 旧 ovr_handle_error_d
    0x1801c8cb8,  # _handle_errorf(float)  — 旧 ovr_handle_error_f
    0x1801a9a6c,  # sqrt(double) CRT wrapper — 旧 ovr_sqrt_d
    0x1801a9b38,  # sqrtf wrapper — 旧 ovr_sqrt_f
]


def overrides():
    ov = {va: name for va, name in TRAMP.items()}
    ov[0x180120ff0] = 'ovr_editor_null'      # editor NULL surrogate (CAB-137 から維持)
    ov[0x1802f8000] = 'ovr_am_shim'          # audioMaster trampoline (CAB-137 から維持)
    return ov


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(here, '..', 'entry'))
    import entry_roots
    *covs, out = sys.argv[1:]
    calltgt = set()
    for c in covs:
        d = json.load(open(c))
        calltgt |= set(int(r) for r in d.get('calltgt', []))
    roots = [0x18011d400, 0x180120af0, 0x180120800, 0x18011ec20] + entry_roots.ENTRY_ROOTS
    roots += CRT_REAL + list(TRAMP)
    for r in entry_roots.ENTRY_ROOTS + CRT_REAL + list(TRAMP):
        calltgt.add(r - IMG)
    json.dump({'roots': roots, 'calltgt': sorted(calltgt)}, open(out, 'w'))
    print('[crt_roots] cov %d / roots %d / calltgt %d / overrides %d' % (len(covs), len(roots), len(calltgt), len(overrides())))


if __name__ == '__main__':
    main()
