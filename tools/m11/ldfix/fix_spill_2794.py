#!/usr/bin/env python3
"""fix_spill_2794.py — spill 宛 TRUE_DROP の修復 pass (#2794 / LD-130)。

対象は audit_lsf_ssa.py の spill 宛 (frame=True) CELL_COLLAPSED のうち、次の 3 条件をすべて満たす site だけ。
  機械語  : 関数内で rip セル X に触れる命令が ちょうど 1 つ (site の `mov rA,[rip+X]`)。他の参照があれば 1 対 1 が決まらない
  IR      : 関数内で `i64 K to ptr` の出現が ちょうど 1 つで、それが `load iN, ptr inttoptr (K)` (N は整数幅。ptr の load は対象外)
  幅      : IR の load 幅 N = 機械語 store の幅 w (1003c20 のように IR が i32 で機械語が 64 bit の site は対象外)
修復は fix_d17.py と同じ 2 段分割: `%v = load iN, ptr inttoptr K` を
   %cellps.K = load ptr, ptr inttoptr K    (セル内容 = 変数のアドレス)
   %v = load iN, ptr %cellps.K              (その先を読む = 機械語の 2 段目の deref)
に置き換える。store の有無は要らない (spill 宛は IR に store が無いことがあるが、直すのは K の load だけ)。

入力: 修復前 IR / audit_lsf_ssa.py の --json 出力 (site の cell 情報) / 機械語 (IMG・CFG)。
使い方: python3 fix_spill_2794.py IN.ll AUDIT.json IMG CFG OUT.ll --report OUT.json [--gate none]
  --gate none: 1 対 1 の判定を外す (ネガティブコントロール用。修復件数が増えることを確かめる)
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
import audit_lsf as A  # noqa: E402
import capstone  # noqa: E402

DEF_RE = re.compile(r'^define [^\n]*@function_([0-9a-f]+)\(', re.M)
INT_W = re.compile(r'^i(\d+)$')


def spill_targets(audit, allow):
    """va_hex -> [(site_addr_hex, K, X, w)]: spill 宛 CELL_COLLAPSED の site のうち、判定 TSV で TRUE_DROP のもの (allow = {(va, site)})"""
    out = collections.OrderedDict()
    for va, v in audit['functions'].items():
        for s in v['sites']:
            c = s.get('cell')
            if not c or c.get('verdict') != 'CELL_COLLAPSED' or not s.get('frame'):
                continue
            if (va, s['addr']) not in allow:
                continue
            out.setdefault(va, []).append((s['addr'], int(c['k'], 16), int(c['cell'], 16), s['w']))
    return out


def true_drop_set(tsv_path):
    """spill37_1169.tsv の TRUE_DROP (fn, site) の集合"""
    rows = [l.rstrip('\n').split('\t') for l in open(tsv_path)][1:]
    return {(r[0], r[1]) for r in rows if len(r) > 3 and r[3] == 'TRUE_DROP'}


def rip_touches(mach, va, body):
    """関数 va の機械語で rip 相対メモリオペランドを持つ命令 -> {X: [(命令アドレス, mnemonic, 先頭オペランドが reg か)]} (X = 絶対アドレス)。
    命令集合は audit_lsf_ssa.py と同じ (audit_lsf.descend: IR ラベルを root にした再帰降下)"""
    labels = [int(x, 16) for x in re.findall(r'^dec_label_pc_([0-9a-f]+)[:.]', body, re.M)]
    ins = A.descend(mach, va, labels) or []
    out = collections.defaultdict(list)
    for i in ins:
        for o in i.operands:
            if o.type == capstone.CS_OP_MEM and o.mem.base and mach.cs.reg_name(o.mem.base) == 'rip':
                reg_load = i.mnemonic == 'mov' and i.operands[0].type == capstone.CS_OP_REG
                out[i.address + i.size + o.mem.disp].append((i.address, i.mnemonic, reg_load))
    return out


def judge_one(body, site, touches, gate):
    """1 site の判定 -> (ok: bool, reason: str)。機械語側は X を読む命令が 1 つで、それが `mov reg,[rip+X]` であること"""
    addr, K, X, w = site
    if gate == 'none':
        return True, 'gate-off'
    refs = touches.get(X, [])
    if len(refs) != 1:
        return False, 'machine_refs=%d' % len(refs)
    if not refs[0][2]:
        return False, 'machine_ref_not_reg_load'
    occ = re.findall(r'i64 %d to ptr\b' % K, body)
    if len(occ) != 1:
        return False, 'ir_refs=%d' % len(occ)
    m = re.search(r'^(\s*)(%\S+) = load (i(\d+)), ptr inttoptr \(i64 ' + str(K) + r' to ptr\)([^\n]*)$', body, re.M)
    if not m:
        return False, 'ir_not_intload'
    n = int(m.group(4))
    if n != w:
        return False, 'width IR=i%d machine=%d' % (n, w)
    return True, 'ok'


def fix_text(ir, mach, audit, allow, gate):
    """→ (新しい IR 本文, 修復リスト, 見送りリスト)"""
    tg = spill_targets(audit, allow)
    fixed, skipped = [], []
    parts, last = [], 0
    for m in DEF_RE.finditer(ir):
        va = m.group(1)
        if va not in tg:
            continue
        end = ir.index('\n}', m.end()) + 2
        body = ir[m.start():end]
        touches = rip_touches(mach, int(va, 16), body)
        new = body
        for site in tg[va]:
            addr, K, X, w = site
            m_refs = len(touches.get(X, []))
            i_refs = len(re.findall(r'i64 ' + str(K) + r' to ptr\b', new))
            ok, why = judge_one(new, site, touches, gate)
            if not ok:
                skipped.append(dict(fn=va, site=addr, K='%x' % K, why=why, m=m_refs, i=i_refs))
                continue
            pat = re.compile(r'^(\s*)(%\S+) = load (i\d+), ptr inttoptr \(i64 ' + str(K) + r' to ptr\)([^\n]*)$', re.M)
            mm = pat.search(new)
            if mm is None:
                skipped.append(dict(fn=va, site=addr, K='%x' % K, why='ir_not_intload_at_apply', m=m_refs, i=i_refs))
                continue
            ind, name, ty, rest = mm.group(1), mm.group(2), mm.group(3), mm.group(4)
            p = '%%cellps.%x' % K
            rep = (ind + p + ' = load ptr, ptr inttoptr (i64 ' + str(K) + ' to ptr)' + rest + '\n'
                   + ind + name + ' = load ' + ty + ', ptr ' + p + rest)
            new = new[:mm.start()] + rep + new[mm.end():]
            fixed.append(dict(fn=va, site=addr, K='%x' % K, X='%x' % X, ty=ty, w=w, m=m_refs, i=i_refs))
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
    ap.add_argument('--tsv', required=True, help='spill37_1169.tsv (判定。TRUE_DROP だけを対象にする)')
    ap.add_argument('--report')
    ap.add_argument('--gate', choices=['1to1', 'none'], default='1to1')
    a = ap.parse_args()
    audit = json.load(open(a.audit))
    ir = open(a.infile, errors='replace').read()
    mach = ImageMachine(a.image, a.cfg)
    out, fixed, skipped = fix_text(ir, mach, audit, true_drop_set(a.tsv), a.gate)
    open(a.outfile, 'w').write(out)
    rep = dict(gate=a.gate, fixed=fixed, skipped=skipped)
    print('spill fixed=%d skipped=%d fixed_fns=%d' % (len(fixed), len(skipped), len({x['fn'] for x in fixed})))
    for x in skipped:
        print('  skip %s %s K=%s %s' % (x['fn'], x['site'], x['K'], x['why']))
    if a.report:
        json.dump(rep, open(a.report, 'w'), indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
