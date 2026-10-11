#!/usr/bin/env python3
"""acc_scen_count.py — CAB-137 独立再計算 (別アルゴリズム: scenario JSON の直接集計)。

定義 (規則 36):
  - scenario entry数   = entry_scen.scen_list() が返す (name, steps) の要素数。
                        runner は dict で name をキーに保持するため **同一 name は後勝ちで 1 件に潰れる**。
  - 一意 scenario 名数 = 上記を name でユニーク化した数 (cmp_entries が比較する実際の件数)。
  - op 値             = {'c':'disp'} step の op フィールドのユニーク値。
                        GUI 4 op = effEditGetRect(13)/effEditOpen(14)/effEditClose(15)/effEditIdle(19)。
                        (これらは editor=NULL surrogate 経路のみ到達)
  - getp/setp/virt   = 各 step 種の出現回数。

使い方:  python3 tools/ott/accept/acc_scen_count.py [SCEN.json]
"""
import json
import os
import sys
from collections import Counter

GUI_OPS = {13, 14, 15, 19}


def count(scens):
    names = [s['name'] for s in scens]
    c = Counter(names)
    op_vals = sorted({int(n[2:]) for n in names if n.startswith('op')})
    all_ops = sorted({st['op'] for s in scens for st in s['steps'] if st['c'] == 'disp'})
    return {
        'scenario_entries': len(names),
        'unique_scenario_names': len(set(names)),
        'duplicate_names': sorted(k for k, v in c.items() if v > 1),
        'op_scenario_entries': sum(1 for n in names if n.startswith('op')),
        'op_distinct_values': len(op_vals),
        'op_values': op_vals,
        'op_non_gui_values': len(set(op_vals) - GUI_OPS),
        'op_gui_values': sorted(set(op_vals) & GUI_OPS),
        'all_disp_op_values': len(all_ops),
        'all_disp_op_non_gui': len(set(all_ops) - GUI_OPS),
        'all_disp_op_extra': sorted(set(all_ops) - set(op_vals)),
        'getp_steps': sum(1 for s in scens for st in s['steps'] if st['c'] == 'getp'),
        'getp_distinct_idx': sorted({st['idx'] for s in scens for st in s['steps'] if st['c'] == 'getp'}),
        'setp_steps': sum(1 for s in scens for st in s['steps'] if st['c'] == 'setp'),
        'virt_steps': sum(1 for s in scens for st in s['steps'] if st['c'] == 'virt'),
        'plabel_steps': sum(1 for s in scens for st in s['steps'] if st['c'] == 'virt' and st.get('rva') == 0x11e7b0),
        'pname_steps': sum(1 for s in scens for st in s['steps'] if st['c'] == 'virt' and st.get('rva') == 0x11e820),
        'pdisplay_steps': sum(1 for s in scens for st in s['steps'] if st['c'] == 'virt' and st.get('rva') == 0x11e770),
        'proc_steps': sum(1 for s in scens for st in s['steps'] if st['c'] == 'proc'),
        'chunk_steps': sum(1 for s in scens for st in s['steps'] if st['c'] in ('setchunk', 'getchunk')),
    }


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        here, '..', 'work', 'entrylift', 'scen.json')
    scens = json.load(open(path))
    r = count(scens)
    for k, v in r.items():
        print('%-28s %s' % (k, v))
    return r


if __name__ == '__main__':
    main()
