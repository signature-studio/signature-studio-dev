#!/usr/bin/env python3
"""negcon_table.py — CAB-273 のネガティブコントロール (規則 41): 判定列は実測値から決まること。

背景: 撤去前の scripts/make_table.py は snapins.json に `tol` キーがあるかどうかだけで
判定列を `許容誤差` / `bit-exact` と決めていた (= 設定の有無で判定を偽れる)。
撤去後は stat.json の **実測** (trials/calls の PASS 数と compare 文字列の tol 統計) から
判定する。本スクリプトは「approx 0 でない snapshot を食わせると bit-exact と誤表示しない」
ことを実測する (Linear CAB-273 要件 2 のネガコン)。

数え方の定義 (規則 36):
  - snapshot = work/<name>/<tag>/stat.json (build.py が書く 1 snap-in 分の実測)。
  - 「legacy 統計」= compare 文字列の `tol(1.6*2^-12 gate): approx N, maxrel R, maxabs A, exceed E`。
    値は親ツリー 8efb7a0 の実測 baseline (work/run_all.phase2_base.log L22-25) をそのまま使う
    (= 推定でなく実測値の転記)。ただし trials/calls は現行 snapshot の実測値とし、
    「判定が tol 統計だけに依存する」ことを見る。
  - 誤表示 = 判定列が 'bit-exact' になること。

合否基準:
  1) 現行 snapshot (tol 撤去後) → 全 snap-in が 'bit-exact'
  2) legacy 統計を埋めた snapshot → 該当 3 本は 'bit-exact' 以外 (許容誤差/不一致) になる
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAG = 'negcon_legacy'
# 親ツリー 8efb7a0 の実測 baseline (work/run_all.phase2_base.log L22-25) の転記
LEGACY = {
    'resonator': ('180743390', 'tol(1.6*2^-12 gate): approx 140067 / diff-words, maxrel 2.778e-1, maxabs 2.813e-1, exceed 0', 65787),
    'stereo': ('18080d4d0', 'tol(1.6*2^-12 gate): approx 827 / diff-words, maxrel 2.894e-5, maxabs 6.607e-3, exceed 0', 111574),
    'delay': ('1802ed550:200/200 1802ed7f0:799/799 1802ed790:200/200 1802ed3b0:50/50 1802ed490:50/50',
              'tol(1.6*2^-12 gate): approx 478 / diff-words, maxrel 6.110e-6, maxabs 1.192e-7, exceed 0', 3585984),
}
ORDER = ['matrix', 'gain', 'haas', 'clipper', 'gate', 'quickeq', 'resonator', 'stereo',
         'disperser', 'formant', 'phaser', 'delay', 'limiter', 'khbase']


def make_snapshots():
    """現行 stat.json を <name>/negcon_legacy/stat.json に legacy 比較文字列で複写する。"""
    made = []
    for n, (fn, toltag, wasm) in LEGACY.items():
        src = os.path.join(ROOT, 'work', n, 's0', 'stat.json')
        if not os.path.exists(src):
            continue
        d = json.load(open(src))
        d['wasm_bytes'] = wasm
        if n == 'delay':
            cmp_ = 'RESULT trials %s/%s [tolerance]; calls %s/%s; by fn %s %s' % (
                d['trials_ok'], d['trials'], d['calls_ok'], d['calls'], fn, toltag)
        else:
            cmp_ = 'RESULT trials %s/%s [tolerance]; calls %s/%s; by fn %s:999/999 %s' % (
                d['trials_ok'], d['trials'], d['calls_ok'], d['calls'], fn, toltag)
        d['compare'] = cmp_
        dst = os.path.join(ROOT, 'work', n, TAG)
        os.makedirs(dst, exist_ok=True)
        json.dump(d, open(os.path.join(dst, 'stat.json'), 'w'), indent=1)
        made.append(n)
    return made


def table(tag):
    r = subprocess.run(['python3', os.path.join(ROOT, 'scripts', 'make_table.py'), tag],
                       capture_output=True, text=True, cwd=ROOT)
    if r.returncode:
        raise SystemExit('make_table.py failed: ' + r.stderr[-400:])
    rows = {}
    for line in r.stdout.strip().split('\n'):
        if not line.startswith('| ') or line.startswith('|---'):
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if cells[0].startswith('snap-in'):
            continue
        rows[cells[0]] = cells[8] if len(cells) > 8 else '(no row)'
    return rows


def main():
    made = make_snapshots()
    print('  legacy snapshots injected: %s (tag=%s)' % (','.join(made), TAG))
    cur = table('s0')
    leg = table(TAG)
    cfg = json.load(open(os.path.join(ROOT, 'snapins.json')))
    title = {n: '%s (%s)' % (cfg[n]['title'], cfg[n]['id']) for n in ORDER}
    print('  %-26s %-10s %-22s' % ('snap-in', 'current', 'legacy-approx>0'))
    bad = []
    for name in ORDER:
        row = title[name]
        c, l = cur.get(row, '(no row)'), leg.get(row, '(no legacy snapshot)')
        print('  %-26s %-10s %-22s' % (row[:26], c, l))
        if c != 'bit-exact':
            bad.append('current %s not bit-exact (%s)' % (row, c))
        if name in LEGACY and l == 'bit-exact':
            bad.append('legacy %s misreported as bit-exact' % row)
    print('---')
    if bad:
        print('FAIL: ' + '; '.join(bad))
        return 1
    print('OK: judgment comes from measurement (approx>0 is never shown as bit-exact)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
