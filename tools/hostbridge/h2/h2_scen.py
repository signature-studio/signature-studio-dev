#!/usr/bin/env python3
"""h2_scen.py — HB-H2 (CAB-91) の native 参照 scenario 集。

bridge 経由ハーネス (surrogate_harness.mjs) が再現する呼出列と **同一順序** の scenario を
tools/ott/entry/entry_nat.py に食わせて native 実機械語の参照値を作る。
entry_scen.py の既存 scenario (getp_range / op45 / op47 / op48 / op6系 / virt_plabel / virt_pname /
chunk_rt) をそのまま流用し、host.load 相当の前処理を含む 'h2_full' を追加する。
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'ott', 'entry'))
import entry_scen  # noqa: E402  (読取専用の参照)

STR = entry_scen.STR
N = entry_scen.N


def h2_scen_list():
    S = []
    # host.load相当 (effOpen → effSetSampleRate(44100) → effSetBlockSize(1024) → effMainsChanged(1))
    # → param 0..18 = 0.5 → effMainsChanged(1) → processReplacing(128f) → effMainsChanged(0)
    pre = [{'c': 'disp', 'op': 0, 'idx': 0, 'val': 0, 'buf': 0},
           {'c': 'disp', 'op': 10, 'idx': 0, 'val': 0, 'buf': 0, 'opt': 44100.0},
           {'c': 'disp', 'op': 11, 'idx': 0, 'val': 1024, 'buf': 0},
           {'c': 'disp', 'op': 12, 'idx': 0, 'val': 1, 'buf': 0}]
    S.append(('h2_full', [{'c': 'vstmain'}] + pre +
              [{'c': 'setp', 'idx': i, 'fv': 0.5} for i in range(19)] +
              [{'c': 'disp', 'op': 12, 'idx': 0, 'val': 1, 'buf': 0},
               {'c': 'proc', 'n': N},
               {'c': 'disp', 'op': 12, 'idx': 0, 'val': 0, 'buf': 0}]))
    # effGetParamName を dispatcher (op8) 経由で全 param — bridge の outstr marshal 経路の参照
    S.append(('h2_pnames', [{'c': 'vstmain'}] +
              [{'c': 'disp', 'op': 8, 'idx': i, 'val': 0, 'buf': 1} for i in range(20)]))
    # effGetParamLabel を dispatcher (op6) 経由で全 param
    S.append(('h2_plabels', [{'c': 'vstmain'}] +
              [{'c': 'disp', 'op': 6, 'idx': i, 'val': 0, 'buf': 1} for i in range(20)]))
    return S


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'work', 'scen.json')
    reuse = ['getp_range', 'op45', 'op47', 'op48', 'op49', 'op58', 'op35', 'op8', 'chunk_rt', 'virt_plabel', 'virt_pname']
    base = {n: s for n, s in entry_scen.scen_list()}
    scens = [{'name': n, 'steps': s} for n, s in h2_scen_list()]
    scens += [{'name': n, 'steps': base[n]} for n in reuse if n in base]
    json.dump(scens, open(out, 'w'))
    print('[h2_scen] scenarios %d -> %s' % (len(scens), out))


if __name__ == '__main__':
    main()
