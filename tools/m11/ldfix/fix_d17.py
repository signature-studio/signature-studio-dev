#!/usr/bin/env python3
"""fix_d17.py — D17 修復 pass (#968 / LD-21): rip 相対ポインタセルの 2 段 deref 潰れを IR で直す。

対象は audit_lsf_ssa.py の CELL_COLLAPSED のうち、store 宛 (frame=False) かつ、その関数内でセル K を読む IR load が
ちょうど 1 本の site。機械語 `mov rA,[rip+X]; mov rD,[rA]` の 2 段目が、IR では `load T, inttoptr K` の 1 段に潰れている。
修復: `%v = load T, ptr inttoptr K` を
   %cellp.K = load ptr, ptr inttoptr K        (セル内容 = 変数のアドレス)
   %v = load T, ptr %cellp.K                  (その先を読む = 元の機械語の意味)
に置き換える。他の use は %v の値をそのまま見るので無変更。

入力: 修復前 IR / audit_lsf_ssa.py の --json 出力 (site 詳細) / 出力 IR / 修復関数の一覧 JSON (任意)。
使い方: python3 fix_d17.py IN.ll AUDIT.json OUT.ll [--report OUT.json]
"""
import argparse
import collections
import json
import re

DEF_RE = re.compile(r'^define [^\n]*@function_([0-9a-f]+)\(', re.M)


def targets(audit):
    """va_hex → 修復対象セル K (int, セル自身の LVA) の集合"""
    out = collections.OrderedDict()
    for va, v in audit['functions'].items():
        for s in v['sites']:
            c = s.get('cell')
            if not c or c.get('verdict') != 'CELL_COLLAPSED' or s.get('frame'):
                continue
            out.setdefault(va, set()).add(int(c['k'], 16))
    return out


def fix_text(ir, tgt):
    """→ (新しい IR 本文, {va: [K]})。関数ごとに K を読む load が 1 本のときだけ直す"""
    fixed = collections.OrderedDict()
    parts = []
    last = 0
    for m in DEF_RE.finditer(ir):
        va = m.group(1)
        if va not in tgt:
            continue
        end = ir.index('\n}', m.end()) + 2
        body = ir[m.start():end]
        new = body
        done = []
        for K in sorted(tgt[va]):
            pat = re.compile(r'^(\s*)(%\S+) = load (\S+), ptr inttoptr \(i64 ' + str(K) + r' to ptr\)([^\n]*)$', re.M)
            hits = pat.findall(new)
            if len(hits) != 1:
                continue
            def rep(mm, K=K):
                ind, name, ty, rest = mm.group(1), mm.group(2), mm.group(3), mm.group(4)
                p = '%%cellp.%x' % K
                return (ind + p + ' = load ptr, ptr inttoptr (i64 ' + str(K) + ' to ptr)' + rest + '\n'
                        + ind + name + ' = load ' + ty + ', ptr ' + p + rest)
            new = pat.sub(rep, new, count=1)
            done.append(K)
        if done:
            fixed[va] = done
            parts.append(ir[last:m.start()])
            parts.append(new)
            last = end
    parts.append(ir[last:])
    return ''.join(parts), fixed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('infile')
    ap.add_argument('audit')
    ap.add_argument('outfile')
    ap.add_argument('--report')
    a = ap.parse_args()
    audit = json.load(open(a.audit))
    ir = open(a.infile, errors='replace').read()
    out, fixed = fix_text(ir, targets(audit))
    open(a.outfile, 'w').write(out)
    rep = {'fixed_fns': len(fixed), 'fixed': {k: [hex(x) for x in v] for k, v in fixed.items()}}
    print('fixed_fns=%d fixed_cells=%d' % (len(fixed), sum(len(v) for v in fixed.values())))
    if a.report:
        json.dump(rep, open(a.report, 'w'), indent=1)


if __name__ == '__main__':
    main()
