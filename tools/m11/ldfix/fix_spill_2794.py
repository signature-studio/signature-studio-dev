#!/usr/bin/env python3
"""fix_spill_2794.py — spill 宛 TRUE_DROP の修復 pass (#2794 / LD-130。#2910 / LD-137 で根拠の 2 本目を追加)。

対象は audit_lsf_ssa.py の spill 宛 (frame=True) CELL_COLLAPSED のうち、判定 TSV で TRUE_DROP の site。
各 site は次のどちらかの根拠を持つ場合だけ直す (gate)。
  1to1    : 関数内で rip セル X に触れる機械語命令が ちょうど 1 つ (site の `mov reg,[rip+X]`) で、
            IR の `i64 K to ptr` の出現も ちょうど 1 つ。さらに、その IR load の幅 N = 機械語 store の幅 w。
  callarg : (#2910) 機械語で、site が `mov dword ptr [rsp+0x20+8j], reg32` (outgoing 引数 argi = 4+j 番目) の store で、
            その直前の rip 読み出し R (`mov Rr,[rip+X]`) から site まで分岐・call が無く、R と site の間はちょうど 1 命令で
            `mov Sr32,[Rr]` (disp 0。store のレジスタ Sr は R の値の逆参照で得た値)、site の直後 (4 命令以内) の direct call が
            callee F。IR では F の呼び出しの引数 argi (0 始まり) が、K の load の値 (sext/zext 1 段まで) に一致し、
            その組が 1 つだけ。幅 N = w = 4。
            根拠の無い site (ローカル変数 [rbp+d] へ流れる等) はこの gate では直さない。
修復は fix_d17.py と同じ 2 段分割: `%v = load iN, ptr inttoptr K` を
   %cellps.K = load ptr, ptr inttoptr K    (セル内容 = 変数のアドレス)
   %v = load iN, ptr %cellps.K              (その先を読む = 機械語の 2 段目の deref)
に置き換える。store の有無は要らない (spill 宛は IR に store が無いことがあるが、直すのは K の load だけ)。

入力: 修復前 IR / audit_lsf_ssa.py の --json 出力 (site の cell 情報) / 機械語 (IMG・CFG)。
使い方: python3 fix_spill_2794.py IN.ll AUDIT.json IMG CFG OUT.ll --tsv SPILL37.tsv --report OUT.json [--gate both]
  --gate both (既定) : 1to1 か callarg の根拠がある site を直す
  --gate 1to1        : 1to1 の根拠だけ (#2794 の 9 site に相当)
  --gate none        : 判定を外す (ネガティブコントロール用。修復件数が増えることを確かめる)
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
LOAD_RE = r'^(\s*)(%%\S+) = load (i(\d+)), ptr inttoptr \(i64 %d to ptr\)([^\n]*)$'


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
    """関数 va の機械語で rip 相対メモリオペランドを持つ命令 -> ({X: [(命令アドレス, mnemonic, 先頭オペランドが reg か)]}, 命令列)。
    X = 絶対アドレス。命令集合は audit_lsf_ssa.py と同じ (audit_lsf.descend: IR ラベルを root にした再帰降下)"""
    labels = [int(x, 16) for x in re.findall(r'^dec_label_pc_([0-9a-f]+)[:.]', body, re.M)]
    ins = A.descend(mach, va, labels) or []
    out = collections.defaultdict(list)
    for i in ins:
        for o in i.operands:
            if o.type == capstone.CS_OP_MEM and o.mem.base and mach.cs.reg_name(o.mem.base) == 'rip':
                reg_load = i.mnemonic == 'mov' and i.operands[0].type == capstone.CS_OP_REG
                out[i.address + i.size + o.mem.disp].append((i.address, i.mnemonic, reg_load))
    return out, ins


def judge_1to1(body, site, touches):
    """1to1 の根拠。→ (ok, reason, IR の結果名)。機械語側は X を読む命令が 1 つで、それが `mov reg,[rip+X]` であること"""
    addr, K, X, w = site
    refs = touches.get(X, [])
    if len(refs) != 1:
        return False, 'machine_refs=%d' % len(refs), None
    if not refs[0][2]:
        return False, 'machine_ref_not_reg_load', None
    occ = re.findall(r'i64 %d to ptr\b' % K, body)
    if len(occ) != 1:
        return False, 'ir_refs=%d' % len(occ), None
    m = re.search(LOAD_RE % K, body, re.M)
    if not m:
        return False, 'ir_not_intload', None
    n = int(m.group(4))
    if n != w:
        return False, 'width IR=i%d machine=%d' % (n, w), None
    return True, 'ok', m.group(2)


def split_args(s):
    """call の引数列 (括弧の内側の文字列) を最上位の ', ' で割る"""
    out, depth, cur = [], 0, ''
    for ch in s:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if ch == ',' and depth == 0:
            out.append(cur.strip())
            cur = ''
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def judge_callarg(mach, body, site, ins, m_refs, i_refs):
    """callarg の根拠。→ (ok, reason, IR の結果名, 根拠の要約)。M = I (機械語の読み出し数と IR の K の出現数が一致) を必須にする
    (M > I は B 分類の欠落の疑いで、本 issue の範囲外)"""
    addr, K, X, w = int(site[0], 16), site[1], site[2], site[3]
    if w != 32:
        return False, 'callarg_width=%d' % w, None, None
    if m_refs != i_refs:
        return False, 'callarg_m_ne_i=%d/%d' % (m_refs, i_refs), None, None
    by_addr = {i.address: i for i in ins}
    st = by_addr.get(addr)
    if st is None or st.mnemonic != 'mov' or len(st.operands) != 2:
        return False, 'callarg_site_not_mov', None, None
    d0, d1 = st.operands
    if d0.type != capstone.CS_OP_MEM or d1.type != capstone.CS_OP_REG:
        return False, 'callarg_site_not_reg_store', None, None
    if mach.cs.reg_name(d0.mem.base) != 'rsp' or d0.mem.index:
        return False, 'callarg_site_not_rsp', None, None
    disp = d0.mem.disp
    if disp < 0x20 or (disp - 0x20) % 8:
        return False, 'callarg_site_not_stack_arg', None, None
    argi = 4 + (disp - 0x20) // 8
    reads = sorted((t for t in ins_reads(mach, X, ins) if t[0] < addr), key=lambda t: t[0])
    if not reads:
        return False, 'callarg_no_prior_read', None, None
    r, _, r_load = reads[-1]
    if not r_load:
        return False, 'callarg_read_not_reg_load', None, None
    between = [i for i in ins if r < i.address < addr]
    if any(i.mnemonic in ('call', 'ret', 'jmp') or i.mnemonic.startswith('j') for i in between):
        return False, 'callarg_read_not_straight', None, None
    if len(between) != 1:
        return False, 'callarg_no_deref_chain', None, None
    dr = between[0]
    rdst = mach.cs.reg_name(by_addr[r].operands[0].reg)
    if dr.mnemonic != 'mov' or len(dr.operands) != 2:
        return False, 'callarg_no_deref_chain', None, None
    e0, e1 = dr.operands
    if e0.type != capstone.CS_OP_REG or e1.type != capstone.CS_OP_MEM or not e1.mem.base or e1.mem.index or e1.mem.disp:
        return False, 'callarg_no_deref_chain', None, None
    if rdst[0] != 'r' or rdst.endswith('d') or reg_fam(mach.cs.reg_name(e1.mem.base)) != reg_fam(rdst):
        return False, 'callarg_no_deref_chain', None, None
    if reg_fam(mach.cs.reg_name(e0.reg)) != reg_fam(mach.cs.reg_name(d1.reg)):
        return False, 'callarg_no_deref_chain', None, None
    nxt = [i for i in ins if i.address > addr][:4]
    call = None
    for i in nxt:
        if i.mnemonic == 'call':
            call = i
            break
        if i.mnemonic in ('jmp', 'ret') or i.mnemonic.startswith('j'):
            break
    if call is None or not call.operands or call.operands[0].type != capstone.CS_OP_IMM:
        return False, 'callarg_no_direct_call', None, None
    callee = 'function_%x' % call.operands[0].imm
    names = []
    for lm in re.finditer(LOAD_RE % K, body, re.M):
        if int(lm.group(4)) != w:
            continue
        srcs = {lm.group(2)}
        for hop in re.finditer(r'^\s*(%\S+) = (?:sext|zext|trunc) i\d+ (%\S+) to i\d+', body, re.M):
            if hop.group(2) in srcs:
                srcs.add(hop.group(1))
        for cm in re.finditer(r'^\s*%\S+ = call [^@\n]*@' + callee + r'\((.*)\)[^\n]*$', body, re.M):
            args = split_args(cm.group(1))
            if len(args) > argi and args[argi].split()[-1] in srcs:
                names.append(lm.group(2))
    names = sorted(set(names))
    if len(names) != 1:
        return False, 'callarg_ir_matches=%d' % len(names), None, None
    return True, 'ok', names[0], 'read=%x call=%s argi=%d' % (r, callee, argi)


def reg_fam(n):
    """32 bit と 64 bit の汎用レジスタを同じ族にする (eax → rax・r8d → r8)"""
    if len(n) == 3 and n[0] == 'e':
        return 'r' + n[1:]
    if n.startswith('r') and n.endswith('d'):
        return n[:-1]
    return n


def ins_reads(mach, X, ins):
    """命令列のうち、rip 相対で X に触れる命令 -> [(命令アドレス, mnemonic, 先頭が reg の load か)]"""
    out = []
    for i in ins:
        for o in i.operands:
            if o.type == capstone.CS_OP_MEM and o.mem.base and mach.cs.reg_name(o.mem.base) == 'rip':
                if i.address + i.size + o.mem.disp == X:
                    out.append((i.address, i.mnemonic, i.mnemonic == 'mov' and i.operands[0].type == capstone.CS_OP_REG))
    return out


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
        touches, ins = rip_touches(mach, int(va, 16), body)
        new = body
        for site in tg[va]:
            addr, K, X, w = site
            m_refs = len(touches.get(X, []))
            i_refs = len(re.findall(r'i64 ' + str(K) + r' to ptr\b', new))
            ev, name = None, None
            if gate == 'none':
                ok, why = True, 'gate-off'
            else:
                ok, why, name = judge_1to1(new, site, touches) if gate in ('both', '1to1') else (False, 'gate-1to1-off', None)
                if ok:
                    ev = '1to1'
                elif gate == 'both':
                    ok, why, name, detail = judge_callarg(mach, new, site, ins, m_refs, i_refs)
                    if ok:
                        ev = 'callarg:' + detail
            if not ok:
                skipped.append(dict(fn=va, site=addr, K='%x' % K, why=why, m=m_refs, i=i_refs))
                continue
            pat = LOAD_RE % K if name is None else r'^(\s*)(%s) = load (i(\d+)), ptr inttoptr \(i64 %d to ptr\)([^\n]*)$' % (re.escape(name), K)
            mm = re.search(pat, new, re.M)
            if mm is None:
                skipped.append(dict(fn=va, site=addr, K='%x' % K, why='ir_not_intload_at_apply', m=m_refs, i=i_refs))
                continue
            ind, nm, ty, rest = mm.group(1), mm.group(2), mm.group(3), mm.group(5)
            p = '%%cellps.%x' % K
            if re.search(re.escape(p) + r'(?![\w.])', new):
                p = '%%cellps.%x.%s' % (K, nm.lstrip('%'))
            rep = (ind + p + ' = load ptr, ptr inttoptr (i64 ' + str(K) + ' to ptr)' + rest + '\n'
                   + ind + nm + ' = load ' + ty + ', ptr ' + p + rest)
            new = new[:mm.start()] + rep + new[mm.end():]
            fixed.append(dict(fn=va, site=addr, K='%x' % K, X='%x' % X, ty=ty, w=w, m=m_refs, i=i_refs,
                              ev=ev or '1to1', ir_name=nm))
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
    ap.add_argument('--gate', choices=['both', '1to1', 'none'], default='both')
    a = ap.parse_args()
    audit = json.load(open(a.audit))
    ir = open(a.infile, errors='replace').read()
    mach = ImageMachine(a.image, a.cfg)
    out, fixed, skipped = fix_text(ir, mach, audit, true_drop_set(a.tsv), a.gate)
    open(a.outfile, 'w').write(out)
    rep = dict(gate=a.gate, fixed=fixed, skipped=skipped)
    print('spill fixed=%d skipped=%d fixed_fns=%d' % (len(fixed), len(skipped), len({x['fn'] for x in fixed})))
    for x in fixed:
        if x['ev'] != '1to1':
            print('  fixed %s %s K=%s %s' % (x['fn'], x['site'], x['K'], x['ev']))
    for x in skipped:
        print('  skip %s %s K=%s %s' % (x['fn'], x['site'], x['K'], x['why']))
    if a.report:
        json.dump(rep, open(a.report, 'w'), indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
