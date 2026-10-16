#!/usr/bin/env python3
"""site_gran_4556.py — #4556 (LD-224): audit の CELL_COLLAPSED 判定を関数 × K から site 単位にする非既定の判定。

既定の audit (audit_lsf_ssa.py) は cell_check で関数全体の K 読み出しを見るため、同じ (関数, K) の i32 読み出しが
1 本でも残ると、その関数の全 spill site が CELL_COLLAPSED のまま残る。本ツールは site ごとに判定する:
  1. 修復前 IR で、site の機械語 chain (rip セル経由の mov) が「同一ブロックの IR 読み出し 1 本と 1 対 1」に結べるか
     (value_flow_5243.py の rmw 規則。修復報告 fixed[].ir_name は使わない)。
  2. 結べた site は、修復後 IR の同じブロックに同じ K の読み出しが残っていなければ REPAIRED (CELL_COLLAPSED から外す)、
     残っていれば REMAIN。
  3. 結べない site は UNLINKED とし、CELL_COLLAPSED のまま残す (保守側。見落としを作らない)。
既定の判定 (audit_lsf_ssa.py の出力) は変えない。本ツールは別の TSV / JSON を出すだけ。
使い方: python3 site_gran_4556.py IR_BEFORE.ll IR_AFTER.ll IMAGE.bin 'CFG_GLOB' AUDIT_BEFORE.json AUDIT_AFTER.json
                                  [--tsv OUT.tsv] [--json OUT.json]
"""
import argparse
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import audit_lsf_ssa as S  # noqa: E402
import fix_d17 as F  # noqa: E402
import link_d17 as L  # noqa: E402
import value_flow_5243 as V  # noqa: E402


def bodies(text):
    for m in F.DEF_RE.finditer(text):
        end = text.index('\n}', m.end()) + 2
        yield m.group(1), text[m.start():end].split('\n')


def labels_of(lines):
    return sorted(int(mm.group(1), 16) for mm in (L.LABEL.match(ln) for ln in lines) if mm)


def frame_collapsed(audit):
    """audit JSON -> {(va, addr): site} (frame かつ cell CELL_COLLAPSED)"""
    out = {}
    for va, v in audit['functions'].items():
        for s in v['sites']:
            if s.get('frame') and (s.get('cell') or {}).get('verdict') == 'CELL_COLLAPSED':
                out[(va, s['addr'])] = s
    return out


def judge_fn(mach, before, after, sites):
    """sites: 同一関数の CELL_COLLAPSED の frame site -> [(site, verdict, blk, K, reason)]"""
    ks = {int(s['cell']['k'], 16) for s in sites}
    labels = labels_of(before)
    chains = V.mach_chains(mach, labels, ks, 'rmw')
    bl = [x for x in L.ir_loads(before) if not x[4].startswith('%cellps.')]
    al = L.ir_loads(after) if after is not None else None
    out = []
    for s in sites:
        K = int(s['cell']['k'], 16)
        src = int(s['cell']['src'], 16)
        mine = [c for c in chains.get(K, []) if c[4] == src]
        if not mine:
            out.append((s, 'UNLINKED', None, K, 'no_chain'))
            continue
        blk, w, why, _used, _a = mine[0]
        if why is not None or w is None:
            out.append((s, 'UNLINKED', blk, K, why or 'no_width'))
            continue
        irs = [x for x in bl if x[3] == K and x[1] == blk]
        ms = [c for c in chains.get(K, []) if c[0] == blk]
        if not (len(irs) == 1 and len(ms) == 1 and irs[0][2] == w):
            out.append((s, 'UNLINKED', blk, K, 'no_1to1'))
            continue
        if al is None:
            out.append((s, 'REMAIN', blk, K, 'fn_missing_after'))
            continue
        remain = [x for x in al if x[3] == K and x[1] == blk and not x[4].startswith('%cellps.')]
        out.append((s, 'REMAIN' if remain else 'REPAIRED', blk, K, 'ir_load_remains' if remain else 'ir_load_gone'))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ir_before')
    ap.add_argument('ir_after')
    ap.add_argument('image')
    ap.add_argument('cfg')
    ap.add_argument('audit_before')
    ap.add_argument('audit_after')
    ap.add_argument('--tsv')
    ap.add_argument('--json')
    a = ap.parse_args()
    before_txt = open(a.ir_before, errors='replace').read()
    after_txt = open(a.ir_after, errors='replace').read()
    aud_b = json.load(open(a.audit_before))
    aud_a = json.load(open(a.audit_after))
    mach = S.ImageMachine(a.image, a.cfg)

    spill_b = frame_collapsed(aud_b)
    after_set = frame_collapsed(aud_a)
    if not set(after_set) <= set(spill_b):
        print('FAIL: 修復後の spill 宛 CELL_COLLAPSED が修復前の集合に含まれない', file=sys.stderr)
        sys.exit(1)

    by_fn = collections.defaultdict(list)
    for (va, _addr), s in spill_b.items():
        by_fn[va].append(s)
    bb = dict(bodies(before_txt))
    ab = dict(bodies(after_txt))

    rows = []
    for va in sorted(by_fn, key=lambda x: int(x, 16)):
        sites = sorted(by_fn[va], key=lambda s: int(s['addr'], 16))
        for s, verdict, blk, K, reason in judge_fn(mach, bb[va], ab.get(va), sites):
            rows.append(dict(fn=va, addr=s['addr'], k='%x' % K, blk=blk or '-', verdict=verdict, reason=reason,
                             in_after=(va, s['addr']) in after_set, text=s.get('text', '')))

    # 修復後の判定: 修復後 audit で CELL_COLLAPSED の site (after_set) のうち、site 単位で REPAIRED のものを外す
    by_key = {(r['fn'], r['addr']): r for r in rows}
    still = [k for k in after_set if not (by_key.get(k) and by_key[k]['verdict'] == 'REPAIRED')]
    func_k_after = len(after_set)
    site_after = len(still)
    summ = collections.Counter(r['verdict'] for r in rows if r['in_after'])
    fn_after = len({k[0] for k in after_set})
    fn_site_after = len({k[0] for k in still})
    print('site 単位 (#4556・非既定): spill 宛 CELL_COLLAPSED 関数×K 判定の後 %d site / %d 関数 -> site 単位の後 %d site / %d 関数'
          % (func_k_after, fn_after, site_after, fn_site_after))
    print('修復後 audit 上の内訳: ' + ' '.join('%s=%d' % (k, summ.get(k, 0)) for k in ('REPAIRED', 'REMAIN', 'UNLINKED')))

    if a.tsv:
        lines = ['fn\tsite\tk\tblk\tverdict\treason\tin_after\ttext']
        for r in rows:
            lines.append('\t'.join([r['fn'], r['addr'], r['k'], r['blk'], r['verdict'], r['reason'],
                                    'yes' if r['in_after'] else 'no', r['text']]))
        with open(a.tsv, 'w') as f:
            f.write('\n'.join(lines) + '\n')
    if a.json:
        json.dump(dict(rows=rows, func_k_after=func_k_after, site_after=site_after,
                       fn_after=fn_after, fn_site_after=fn_site_after),
                  open(a.json, 'w'), indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
