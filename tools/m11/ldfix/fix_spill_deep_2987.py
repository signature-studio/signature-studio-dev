#!/usr/bin/env python3
"""fix_spill_deep_2987.py — spill 宛 CELL_DEEP の TRUE_DROP site の修復 pass (#2987 / LD-143)。

対象は candidate_verdicts_2921.jsonl (等) の TRUE_DROP のうち、audit_lsf_ssa.py で cell 判定が CELL_DEEP の site。
fix_spill_2794.py は CELL_COLLAPSED (幅 64 以外、または alg3 SHALLOW) だけを対象にするため、
幅 64 の定数 load を 2 段と見て保留された CELL_DEEP の site は直さない。本 pass はそれを直す。
ddf630 の 4 site がこれに当たる (`REPORT_2921.md` §2)。
根拠 gate は fix_spill_2794.judge_1to1 と同じ 1 対 1 (機械語で X に触れる命令がちょうど 1 つ・`mov reg,[rip+X]`・
IR の `i64 K to ptr` がちょうど 1 つ・幅一致)。gate を外れた site は直さない。
修復は fix_spill_2794 と同じ 2 段分割: `%v = load iN, ptr inttoptr K` を
   %cellps.K = load ptr, ptr inttoptr K    (セル内容 = 変数のアドレス)
   %v = load iN, ptr %cellps.K              (その先を読む = 機械語の 2 段目の deref)
に置き換える。store 宛 (複写) の site は IR に定数 load が無く、直すのは load だけで足りる
(複写元の SSA 値が 2 段の値になるため、store 行は変えない)。

入力: 修復前 IR / audit_lsf_ssa.py の --json 出力 (ssa.json) / 機械語 (IMG・CFG) / 判定 JSONL (--verdicts、複数可)。
使い方: python3 fix_spill_deep_2987.py IN.ll AUDIT.json IMG CFG OUT.ll --verdicts results/candidate_verdicts_2921.jsonl --report OUT.json
"""
import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ldmach_img import ImageMachine  # noqa: E402
import fix_spill_2794 as F  # noqa: E402


def true_drop_keys(paths):
    """判定 JSONL の TRUE_DROP (fn, site) の集合"""
    out = set()
    for p in paths:
        for ln in open(p):
            r = json.loads(ln)
            if r['verdict'] == 'TRUE_DROP':
                out.add((r['fn'], r['site']))
    return out


def deep_targets(audit, allow):
    """va_hex -> [(site_addr_hex, K, X, w)]: CELL_DEEP の frame 宛 site のうち、判定で TRUE_DROP のもの"""
    out = collections.OrderedDict()
    for va, v in audit['functions'].items():
        for s in v['sites']:
            c = s.get('cell')
            if not c or c.get('verdict') != 'CELL_DEEP' or not s.get('frame'):
                continue
            if (va, s['addr']) not in allow:
                continue
            out.setdefault(va, []).append((s['addr'], int(c['k'], 16), int(c['cell'], 16), s['w']))
    return out


def fix_text(ir, mach, audit, allow):
    """→ (新しい IR 本文, 修復リスト, 見送りリスト)。判定の単位はセル X (同じ X を読む site は 1 つの load を直す)"""
    tg = deep_targets(audit, allow)
    fixed, skipped = [], []
    parts, last = [], 0
    for m in F.DEF_RE.finditer(ir):
        va = m.group(1)
        if va not in tg:
            continue
        end = ir.index('\n}', m.end()) + 2
        body = ir[m.start():end]
        touches, _ins = F.rip_touches(mach, int(va, 16), body)
        new = body
        cells = collections.OrderedDict()
        for site in tg[va]:
            cells.setdefault(site[2], []).append(site)
        for X, group in cells.items():
            addr, K, _X, w = group[0]
            sites = [g[0] for g in group]
            ok, why, name = F.judge_1to1(new, group[0], touches)
            if not ok:
                skipped += [dict(fn=va, site=s, K='%x' % K, why=why) for s in sites]
                continue
            mm = re.search(F.LOAD_RE % K, new, re.M)
            if mm is None:
                skipped += [dict(fn=va, site=s, K='%x' % K, why='ir_not_intload_at_apply') for s in sites]
                continue
            ind, nm, ty, rest = mm.group(1), mm.group(2), mm.group(3), mm.group(5)
            p = '%%cellps.%x' % K
            if re.search(re.escape(p) + r'(?![\w.])', new):
                p = '%%cellps.%x.%s' % (K, nm.lstrip('%'))
            rep = (ind + p + ' = load ptr, ptr inttoptr (i64 ' + str(K) + ' to ptr)' + rest + '\n'
                   + ind + nm + ' = load ' + ty + ', ptr ' + p + rest)
            new = new[:mm.start()] + rep + new[mm.end():]
            fixed.append(dict(fn=va, sites=sites, K='%x' % K, X='%x' % X, ty=ty, w=w, ir_name=nm,
                              copies='store 宛の複写は SSA 伝播で 2 段の値になる (store 行は不変)'))
        if new != body:
            parts.append(ir[last:m.start()])
            parts.append(new)
            last = end
    parts.append(ir[last:])
    return ''.join(parts), fixed, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('infile')
    ap.add_argument('audit')
    ap.add_argument('image')
    ap.add_argument('cfg')
    ap.add_argument('outfile')
    ap.add_argument('--verdicts', action='append', required=True, help='判定 JSONL (TRUE_DROP だけを対象にする。複数可)')
    ap.add_argument('--report')
    a = ap.parse_args()
    audit = json.load(open(a.audit))
    ir = open(a.infile, errors='replace').read()
    mach = ImageMachine(a.image, a.cfg)
    out, fixed, skipped = fix_text(ir, mach, audit, true_drop_keys(a.verdicts))
    open(a.outfile, 'w').write(out)
    print('deep fixed_cells=%d covered_sites=%d skipped=%d fixed_fns=%d' % (
        len(fixed), sum(len(x['sites']) for x in fixed), len(skipped), len({x['fn'] for x in fixed})))
    for x in fixed:
        print('  fixed %s sites=%s K=%s X=%s w=%s' % (x['fn'], ','.join(x['sites']), x['K'], x['X'], x['w']))
    for x in skipped:
        print('  skip %s %s K=%s %s' % (x['fn'], x['site'], x['K'], x['why']))
    if a.report:
        json.dump(dict(fixed=fixed, skipped=skipped), open(a.report, 'w'), indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
