#!/usr/bin/env python3
"""acc_lift_set.py — CAB-137/138 独立再計算: lift 集合 (関数数/命令数) と coverage 差分。

定義 (規則 36):
  - 関数数   = lift_meta.json の `functions` 配列の要素数。
              要素は image VA (10 進文字列) で、override 対象関数は **含まない**
              (override は C 実装に差し替えられ lift されないため)。
  - 命令数   = lift_meta.json の `ninsn` (x64c が生成した IR 命令数 = `insns` と同義)。
  - unsup    = 未対応 mnemonic のユニーク種数 (空 dict なら 0)。
  - coverage = entry_scen.py / crt_scen.py の scenario を native 単歩で実行して得た
              命令アドレス集合 (cov_entry.json / cov_crt.json の `insn`)。
  - 差分原因 = 「コミット済み scenario 定義の再実行」と「実装報告時の coverage 成果物」の
              命令集合差 (筋違いの scenario が混ざっていないかの機械検査)。

使い方:
  python3 tools/ott/accept/acc_lift_set.py                # snapshot (既定)
  python3 tools/ott/accept/acc_lift_set.py --main         # 実装報告時の成果物
"""
import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')


def meta(p):
    d = json.load(open(p))
    return d


def cov(p):
    d = json.load(open(p))
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--main', action='store_true',
                    help='実装報告時の成果物 (tools/ott/work/…) を参照')
    a = ap.parse_args()
    base = ROOT if a.main else os.path.join(ROOT, 'work', 'verify_HEAD', 'tools', 'ott')
    base = os.environ.get('OTT_SNAP', base)

    print('=== lift 集合 (定義: REPORT §1) ===')
    for name, p in (('entry 版', 'work/entrylift/lift_meta.json'),
                    ('crt 版', 'work/crtlift/lift_meta.json')):
        d = meta(os.path.join(base, p))
        print('  %-8s functions %d / insns %d / unsup %d 種 / unlifted_callees %d / overrides %d'
              % (name, len(d['functions']), d['ninsn'], len(d.get('unsup', {})),
                 len(d.get('unlifted_callees', [])), len(d.get('overrides', {}))))

    print()
    print('=== coverage (snapshot 再実行 vs 実装報告時) ===')
    for name, snap_p, main_p in (
            ('entry', os.path.join(base, 'work/entrylift/cov_entry.json'),
             os.path.join(ROOT, 'work/entrylift/cov_entry.json')),
            ('crt', os.path.join(base, 'work/crtlift/cov_crt.json'),
             os.path.join(ROOT, 'work/crtlift/cov_crt.json'))):
        if not os.path.exists(snap_p) or not os.path.exists(main_p):
            continue
        s, m = cov(snap_p), cov(main_p)
        si, mi = set(s['insn']), set(m['insn'])
        print('  %-6s snapshot %d insn / main %d insn / main-only %d / snapshot-only %d'
              % (name, len(si), len(mi), len(mi - si), len(si - mi)))
        if mi - si:
            byscen = {}
            for n, ins in m.get('per_scen', {}).items():
                d = set(ins) - si
                if d:
                    byscen[n] = d
            for n, d in sorted(byscen.items(), key=lambda kv: -len(kv[1])):
                v = sorted(d)
                print('    %-14s +%d insn (先頭 0x%x..0x%x)'
                      % (n, len(d), 0x180000000 + v[0], 0x180000000 + v[-1]))
        # scenario 定義と coverage の整合 (筋違い scenario 混入検査)
        import sys
        sys.path.insert(0, os.path.join(base, 'entry'))
        import entry_scen
        n_defined = len(entry_scen.scen_list())
        n_cov = len(s.get('per_scen', {}))
        print('    scenario 定義 %d (一意名 %d) / coverage 実行 %d'
              % (n_defined, len({n for n, _ in entry_scen.scen_list()}), n_cov))
        getp_idx = []
        for n, steps in entry_scen.scen_list():
            if n == 'getp_range':
                getp_idx = [st['idx'] for st in steps if st['c'] == 'getp']
        print('    getp_range の idx: %s (max %d)' % (getp_idx, max(getp_idx) if getp_idx else -1))


if __name__ == '__main__':
    main()
