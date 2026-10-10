#!/usr/bin/env python3
"""crt_scen.py — CAB-138: CRT 初期化後の突合 scenario 定義 (native / wasm 両ランナ共通)。

entry_scen.py (CAB-137) の step 形式をそのまま使い、CRT が絡む経路だけを追加する:
  - float formatter (effGetParamDisplay の float param 群 / op34 effGetOutputProperties):
    CRT 未初期化では native SIGSEGV / wasm fail-fast だった経路 (CAB-137 §2.3)。
  - DSP 数學エラー経路 (params 全 0 → log(0) → _handle_error): override 4 件の置換検証用。

buffer 配置・step 種別は entry_scen.py と同一 (STR/OUT_F/CKPT/CHUNK/IN_A/OU_A/BUF)。
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'entry'))
from entry_scen import RVA, STR, OUT_F, N  # noqa: E402

FLOAT_PARAMS = [0, 1, 2, 3, 5, 6, 7, 8, 9, 10, 16, 17,18]   # effGetParamDisplay の float 経路 (CAB-137 実測)


def scen_list():
    S = []

    def base(name, calls):
        S.append((name, [{'c': 'vstmain'}] + calls))

    # --- float formatter: ctor 既定値のまま全 float param を表示 ---
    base('flt_disp_def', [{'c': 'virt', 'rva': RVA['pdisplay'], 'rdx': i, 'r8': STR, 'buf': 1} for i in FLOAT_PARAMS])
    # --- float formatter: params を一様 0.335 にセットしてから表示 (値依存の分岐を通す) ---
    base('flt_disp_035', [{'c': 'setp', 'idx': i, 'fv': 0.335} for i in range(19)] +
                         [{'c': 'virt', 'rva': RVA['pdisplay'], 'rdx': i, 'r8': STR, 'buf': 1} for i in FLOAT_PARAMS])
    # --- float formatter: 極値 mix (小値 / 大値 / 0 / 1) — 桁数・指数表記分岐 ---
    vals = [(0, 0.001), (1, 0.999), (2, 0.0), (3, 1.0), (5, 0.25), (6, 0.75),
            (7, 0.1), (8, 0.9), (9, 0.05), (10, 0.95), (16, 0.123), (17, 0.456), (18, 0.789)]
    base('flt_disp_mix', [{'c': 'setp', 'idx': i, 'fv': v} for i, v in vals] +
                         [{'c': 'virt', 'rva': RVA['pdisplay'], 'rdx': i, 'r8': STR, 'buf': 1} for i in FLOAT_PARAMS])
    # --- float formatter: [0x248]=1 (per-sample 路線) + 表示 ---
    base('flt_disp_p4_1', [{'c': 'setp', 'idx': 4, 'fv': 1.0}] +
                          [{'c': 'virt', 'rva': RVA['pdisplay'], 'rdx': i, 'r8': STR, 'buf': 1} for i in FLOAT_PARAMS])
    # --- op34 effGetOutputProperties (getParameter + float format の複合; CAB-137 で native crash) ---
    base('op34_outprop', [{'c': 'disp', 'op': 34, 'idx': 0, 'val': 0, 'buf': 1},
                          {'c': 'disp', 'op': 34, 'idx': 1, 'val': 0, 'buf': 1}])
    # --- op7 (effGetParamDisplay 経由の dispatcher 入口) float param ---
    base('op7_disp', [{'c': 'disp', 'op': 7, 'idx': i, 'val': 0, 'buf': 1} for i in FLOAT_PARAMS])
    # --- DSP 数學エラー経路: params 全 0.0 → process (log(0) → _handle_error 系) ---
    # [0x248]=0 (SVF 路線) と =1 (per-sample 路線) の両方
    base('err_zero_svf', [{'c': 'setp', 'idx': i, 'fv': 0.0} for i in range(19)] +
                         [{'c': 'disp', 'op': 12, 'idx': 0, 'val': 1, 'buf': 0},
                          {'c': 'proc', 'n': N},
                          {'c': 'disp', 'op': 12, 'idx': 0, 'val': 0, 'buf': 0}])
    base('err_zero_pers', [{'c': 'setp', 'idx': i, 'fv': 0.0} for i in range(19)] +
                           [{'c': 'setp', 'idx': 4, 'fv': 1.0},
                            {'c': 'disp', 'op': 12, 'idx': 0, 'val': 1, 'buf': 0},
                            {'c': 'proc', 'n': N},
                            {'c': 'disp', 'op': 12, 'idx': 0, 'val': 0, 'buf': 0}])
    # --- 表示 + 実処理の複合 (エラー経路と formatter の両方を 1 scenario で) ---
    base('err_zero_disp', [{'c': 'setp', 'idx': i, 'fv': 0.0} for i in range(19)] +
                           [{'c': 'virt', 'rva': RVA['pdisplay'], 'rdx': i, 'r8': STR, 'buf': 1} for i in FLOAT_PARAMS] +
                           [{'c': 'disp', 'op': 12, 'idx': 0, 'val': 1, 'buf': 0},
                            {'c': 'proc', 'n': N}])
    return S


if __name__ == '__main__':
    json.dump([{'name': n, 'steps': s} for n, s in scen_list()], open(sys.argv[1], 'w'))
    print('[crt_scen] scenarios', len(scen_list()))
