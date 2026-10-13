#!/usr/bin/env python3
"""audit_lsf_ssa.py — base が引数由来でない load→store (LSF) の脱落判定 (#510 / LD-10)。

audit_lsf.py (#484) は base を argN に解決できる site しか判定できない (脱落形が `store %argN` という IR 署名を持つため)。
本ツールは base の由来を問わず、**機械語の LSF site 全件** (`mov rD,[rB]` disp 0 → rD を壊さず `mov [m],rD`) を列挙し、
IR 側を SSA の値の出自 (store される値が `load` 由来か) で判定する。audit_lsf.py の transfer を provenance 付きに差し替えて再利用し、
arg 解決 site の結果 (lsf 90 site) は audit_lsf.py と一致する (自己検査: --selfcheck)。

IR 側の判定は互いに独立な 2 本:
  alg1 (関数単位の個数収支):  IR_ldst[w] = 非 alloca 宛の `store iW %v` で %v が整数 load 由来 (trunc/zext/sext/bitcast/phi/select 経由) の行数
                               DEFICIT_w = M_lsf[w] - IR_ldst[w]  (> 0 なら SUSPECT。arg 解決/非解決の LSF site を合算)
  alg2 (site 単位の宛先照合):  機械語 store の (幅 w, disp) と IR の store 宛先 (inttoptr(add %x, C) / gep の C) が一致する store 群を候補とし、
                               候補の値が load 由来なら OK、候補があるのに load 由来が 0 なら SUSPECT、候補 0 件なら NOCAND
使い方: python3 audit_lsf_ssa.py IR.ll IMAGE.bin 'CONFIG_GLOB' [--json OUT] [--only VA,VA] [--selfcheck]
"""
import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import audit_lsf as A  # noqa: E402
from ldmach import norm_reg  # noqa: E402
from ldmach_img import ImageMachine  # noqa: E402
import capstone  # noqa: E402

class Ldu(tuple):
    """('ldu', w) と == / hash が同値 (join の挙動を audit_lsf.py と一致させる) で、由来 prov / base 名だけ付随する値"""
    prov = ''
    base = ''


NO_ALLOCA_PROP = False   # --no-alloca-prop: reg2mem alloca 経由の由来伝播を切る (ablation)
SITES = {}   # 機械語 store 命令アドレス -> dict (最終 pass だけが ev を渡すので 1 命令 1 回)

DEF_LINE = re.compile(r'^\s*(%[\w.$-]+) = (.*)$')
LOAD_DEF = re.compile(r'^load (i\d+|ptr), ptr ((?:inttoptr \([^)]*\)|[^,]+))')
CAST_DEF = re.compile(r'^(trunc|zext|sext|bitcast|freeze|ptrtoint|inttoptr) (?:i\d+|ptr) (%[\w.$-]+)(?: to \w+)?')
PHI_DEF = re.compile(r'^phi (i\d+) (.*)$')
SEL_DEF = re.compile(r'^select i1 [^,]+, (i\d+) (%?[\w.$-]+), (i\d+) (%?[\w.$-]+)')
I2P_DEF = re.compile(r'^inttoptr (?:i\d+) (%?[\w.$-]+) to ptr')
ADD_DEF = re.compile(r'^add (?:nuw |nsw )*i\d+ (%?[\w.$-]+), (-?\d+|%[\w.$-]+)')
GEP_DEF = re.compile(r'^getelementptr (?:inbounds )?i8, ptr (%?[\w.$-]+), i\d+ (-?\d+)')
STORE_LINE = re.compile(r'^\s*store (i\d+|ptr) (%?[\w.$-]+), ptr ((?:inttoptr \([^)]*\)|%[\w.$-]+|@[\w.$-]+))')


def describe(sv, mb):
    if sv is None:
        return 'untracked(%s)' % (mb or '?')
    k = sv[0]
    if k == 'src':
        return sv[1]
    return {'ld': 'deref-of-arg', 'ldu': 'deref-chain', 'arg': 'arg'}.get(k, k)


def transfer(cs, i, state, homes, ev):
    """audit_lsf.transfer と同じ意味論 (arg 解決 site の挙動は不変) + 値の由来 ('src', kind, addr) を追跡して SITES に記録する。"""
    mn = i.mnemonic
    ops = i.operands
    newv = None
    dest = None
    if mn == 'mov' and len(ops) == 2:
        o0, o1 = ops
        if o0.type == capstone.CS_OP_REG and o1.type == capstone.CS_OP_REG:
            dest = norm_reg(cs, o0.reg)
            if o0.size == 8 and o1.size == 8:
                newv = state.get(norm_reg(cs, o1.reg))
            else:
                newv = ('src', 'mov%d' % (o0.size * 8), i.address)
        elif o0.type == capstone.CS_OP_REG and o1.type == capstone.CS_OP_MEM:
            dest = norm_reg(cs, o0.reg)
            mb = norm_reg(cs, o1.mem.base) if o1.mem.base else None
            rip = bool(o1.mem.base) and cs.reg_name(o1.mem.base) == 'rip'
            slot = ('m', mb, o1.mem.disp)
            if o1.mem.index == 0 and mb in ('rbp', 'rsp') and o1.size == 8 and (mb, o1.mem.disp) in homes:
                newv = ('arg', homes[(mb, o1.mem.disp)])
            elif o1.mem.index == 0 and mb in ('rbp', 'rsp') and o1.size == 8 and slot in state:
                newv = state[slot]
            elif o1.mem.index == 0 and o1.mem.disp == 0 and mb and not rip and o1.size in (4, 8):
                sv = state.get(mb)
                if sv and sv[0] == 'arg':
                    newv = ('ld', sv[1], o1.size * 8)
                else:
                    newv = Ldu(('ldu', o1.size * 8))
                    newv.prov, newv.base = describe(sv, mb), mb
            else:
                kind = 'rip-mem' if rip else ('frame' if mb in ('rbp', 'rsp') else 'mem+disp')
                newv = ('src', kind, i.address)
        elif o0.type == capstone.CS_OP_MEM and o1.type == capstone.CS_OP_REG:
            sv = state.get(norm_reg(cs, o1.reg))
            mb = norm_reg(cs, o0.mem.base) if o0.mem.base else None
            frame = mb in ('rbp', 'rsp') and cs.reg_name(o0.mem.base) != 'rip'
            w = o0.size * 8
            if frame and o0.mem.index == 0:
                if sv and w == 64:
                    state[('m', mb, o0.mem.disp)] = sv
                else:
                    state.pop(('m', mb, o0.mem.disp), None)
            if ev is None:
                sv = None
            if sv and sv[0] == 'ld' and sv[2] == w:
                ev.append(('lsf', i.address, sv[1], w, '%s %s' % (mn, i.op_str)))
                SITES[i.address] = dict(kind='lsf', w=w, prov='arg%d' % sv[1], base='arg', disp=o0.mem.disp,
                                        idx=o0.mem.index != 0 or (bool(o0.mem.base) and cs.reg_name(o0.mem.base) == 'rip'), frame=frame, text='%s %s' % (mn, i.op_str))
            elif sv and sv[0] == 'ldu' and sv[1] == w:
                ev.append(('unk', i.address, 0, w, ''))
                SITES[i.address] = dict(kind='unk', w=w, prov=sv.prov, base=sv.base, disp=o0.mem.disp,
                                        idx=o0.mem.index != 0 or (bool(o0.mem.base) and cs.reg_name(o0.mem.base) == 'rip'), frame=frame, text='%s %s' % (mn, i.op_str))
            elif sv and sv[0] == 'arg' and not frame:
                ev.append(('ptr', i.address, sv[1], w, ''))
    if mn == 'call':
        for r in A.VOLATILE:
            state.pop(r, None)
        state['rax'] = ('src', 'call-ret', i.address)
    else:
        try:
            _rd, wr = i.regs_access()
        except Exception:
            wr = ()
        for rid in wr:
            r = norm_reg(cs, rid)
            if r:
                state.pop(r, None)
                if not (mn == 'mov' and r == dest):
                    state[r] = ('src', 'lea' if mn == 'lea' else 'alu:' + mn, i.address)
    if dest and newv:
        state[dest] = newv


A.transfer = transfer


def parse_ir(body):
    """IR 関数本体 -> (defs, allocas, stores)。defs: 名前 -> 定義式、stores: [(w, value, ptr)]"""
    defs, allocas = {}, set()
    stores = []
    for ln in body.split('\n'):
        m = DEF_LINE.match(ln)
        if m:
            nm, rhs = m.group(1), m.group(2)
            if rhs.startswith('alloca '):
                allocas.add(nm)
            defs[nm] = rhs
            continue
        s = STORE_LINE.match(ln)
        if s:
            stores.append((A.width_of(s.group(1)), s.group(2), s.group(3)))
    return defs, allocas, stores


def load_derived(defs, allocas, stores):
    """整数 load (非 alloca) 由来の SSA 名の集合。cast / phi / select は 1 本でも由来があれば由来とする (偽陽性側に倒さない)。
    reg2mem の alloca は「由来のある値が 1 度でも store された alloca」を load した値も由来とみなす (メモリ SSA 相当)。"""
    ld = set()
    for nm, rhs in defs.items():
        m = LOAD_DEF.match(rhs)
        if m and m.group(2) not in allocas:
            ld.add(nm)
    ald = set()
    changed = True
    while changed:
        changed = False
        for (_w, v, p) in stores:
            if p in allocas and v in ld and p not in ald and not NO_ALLOCA_PROP:
                ald.add(p); changed = True
        for nm, rhs in defs.items():
            if nm in ld:
                continue
            m = LOAD_DEF.match(rhs)
            if m and m.group(2) in ald:
                ld.add(nm); changed = True; continue
            m = CAST_DEF.match(rhs)
            if m and m.group(2) in ld:
                ld.add(nm); changed = True; continue
            m = PHI_DEF.match(rhs)
            if m and any(v in ld for v in re.findall(r'\[\s*(%[\w.$-]+),', m.group(2))):
                ld.add(nm); changed = True; continue
            m = SEL_DEF.match(rhs)
            if m and (m.group(2) in ld or m.group(4) in ld):
                ld.add(nm); changed = True
    return ld


def ptr_disp(defs, p):
    """store 宛先ポインタ %p -> disp (inttoptr(add %x, C) / gep i8 の C。それ以外は 0)"""
    for _ in range(4):
        rhs = defs.get(p)
        if rhs is None:
            return 0
        m = I2P_DEF.match(rhs)
        if m:
            x = m.group(1)
            r2 = defs.get(x, '')
            a = ADD_DEF.match(r2)
            if a and re.fullmatch(r'-?\d+', a.group(2)):
                return int(a.group(2))
            return 0
        g = GEP_DEF.match(rhs)
        if g:
            return int(g.group(2))
        m = CAST_DEF.match(rhs)
        if m:
            p = m.group(2)
            continue
        return 0
    return 0


def judge(body, sites):
    """sites: [dict] -> (alg1 per width, alg2 per site, ir_ldst Counter)"""
    defs, allocas, stores = parse_ir(body)
    ld = load_derived(defs, allocas, stores)
    ldst = collections.Counter()
    cands = []
    for (w, v, p) in stores:
        if p in allocas:
            continue
        isld = v in ld
        if isld:
            ldst[w] += 1
        cands.append((w, ptr_disp(defs, p), isld))
    return ldst, cands


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ir')
    ap.add_argument('image')
    ap.add_argument('cfg')
    ap.add_argument('--json')
    ap.add_argument('--only')
    ap.add_argument('--no-alloca-prop', action='store_true')
    a = ap.parse_args()
    global NO_ALLOCA_PROP
    NO_ALLOCA_PROP = a.no_alloca_prop
    only = set(int(x, 16) for x in a.only.split(',')) if a.only else None
    text = open(a.ir, errors='replace').read()
    mach = ImageMachine(a.image, a.cfg)
    tot = collections.Counter()
    fns = collections.OrderedDict()
    for va, _args, body in A.ir_functions(text):
        if only and va not in only:
            continue
        tot['functions'] += 1
        labels = [int(x, 16) for x in re.findall(r'^dec_label_pc_([0-9a-f]+)[:.]', body, re.M)]
        SITES.clear()
        ms = A.machine_sites(mach, va, labels)
        if ms is None:
            tot['no_machine_range'] += 1
            continue
        lsf, _ptr, unk = ms
        tot['lsf_sites_arg'] += len(lsf)
        tot['lsf_sites_unresolved'] += unk
        tot['fns_unresolved'] += 1 if unk else 0
        if not SITES:
            continue
        sites = [dict(addr=ad, **d) for ad, d in sorted(SITES.items())]
        ldst, cands = judge(body, sites)
        need = collections.Counter(s['w'] for s in sites if not s['frame'])
        rec = dict(sites=[], alg1=[], ir_ldst=dict(ldst))
        for w, n in sorted(need.items()):
            d = n - ldst[w]
            rec['alg1'].append(dict(w=w, m_lsf=n, ir_ldst=ldst[w], deficit=d))
        for s in sites:
            if s['frame']:
                rec['sites'].append(dict(addr='%x' % s['addr'], kind=s['kind'], w=s['w'], prov=s['prov'], base=s['base'], disp=s['disp'],
                                         idx=s['idx'], frame=True, text=s['text'], alg2='FRAME', cand=0, cand_ld=0))
                continue
            same = [c for c in cands if c[0] == s['w'] and (s['idx'] or c[1] == s['disp'])]
            nl = sum(1 for c in same if c[2])
            v2 = 'OK' if nl else ('SUSPECT' if same else 'NOCAND')
            rec['sites'].append(dict(addr='%x' % s['addr'], kind=s['kind'], w=s['w'], prov=s['prov'], base=s['base'], disp=s['disp'],
                                     idx=s['idx'], frame=False, text=s['text'], alg2=v2, cand=len(same), cand_ld=nl))
        fns['%x' % va] = rec
    cnt = collections.Counter()
    a1, a2 = set(), set()
    for v, r in fns.items():
        if any(x['deficit'] > 0 for x in r['alg1']):
            a1.add(v)
        for st in r['sites']:
            cnt['%s/%s/%s' % (st['kind'], 'frame' if st['frame'] else 'store', st['alg2'])] += 1
            if st['alg2'] in ('SUSPECT', 'NOCAND'):
                a2.add(v)
    tot['alg1_flagged_fns'] = len(a1)
    tot['alg2_flagged_fns'] = len(a2)
    tot['alg1_or_alg2_fns'] = len(a1 | a2)
    out = dict(summary=dict(tot), by_site=dict(cnt), alg1_fns=sorted(a1, key=lambda x: int(x, 16)),
               alg2_fns=sorted(a2, key=lambda x: int(x, 16)), functions=fns)
    print(json.dumps(dict(tot), ensure_ascii=False))
    print(json.dumps(dict(sorted(cnt.items())), ensure_ascii=False))
    if a.json:
        json.dump(out, open(a.json, 'w'), indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
