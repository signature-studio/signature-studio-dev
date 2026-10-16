#!/usr/bin/env python3
"""audit_lsf_ssa.py — base が引数由来でない load→store (LSF) の脱落判定 (#510 / LD-10)。

audit_lsf.py (#484) は base を argN に解決できる site しか判定できない (脱落形が `store %argN` という IR 署名を持つため)。
本ツールは base の由来を問わず、**機械語の LSF site 全件** (`mov rD,[rB]` disp 0 → rD を壊さず `mov [m],rD`) を列挙し、
IR 側を SSA の値の出自 (store される値が `load` 由来か・deref 段数) で判定する。audit_lsf.py の transfer を provenance 付きに差し替えて再利用し、
arg 解決 site (90) / 解決不能 site (370) / 関数 (169) の件数は audit_lsf.py と一致する (audit_lsf_ssa_e2e.sh の 1〜2/6 で突合)。
site は store 宛 (frame=False) と spill 宛 (frame=True: rbp/rsp 宛) に分ける。spill 宛は IR から消えるのが普通なので alg1〜3 の対象外。

IR 側の判定:
  alg1 (関数単位の個数収支):  IR_ldst[w] = 非 alloca 宛の `store iW %v` で %v が load 由来 (trunc/zext/sext/bitcast/phi/select、reg2mem alloca 経由を含む) の行数
                               DEFICIT_w = M_lsf[w] - IR_ldst[w]  (> 0 なら SUSPECT。arg 解決/非解決の LSF site を合算)
  alg2 (site 単位の宛先照合):  機械語 store の (幅 w, disp) と IR の store 宛先 (inttoptr(add %x, C) / gep の C) が一致する store 群を候補とし、
                               候補の値が load 由来なら OK、候補があるのに load 由来が 0 なら SUSPECT、候補 0 件なら NOCAND
  alg3 (deref 段数):          機械語の値の deref 段数 (argN の 1 段 = 1、rip 相対セル経由 = 2 …) <= 候補 store の値の IR load 入れ子段数なら OK、足りなければ SHALLOW
  cell oracle:                 rip 相対セル経由 (`mov rA,[rip+X]; mov rD,[rA]`) の site を image の実データで判定
                               (FOLDED_OK / CELL_COLLAPSED / CELL_DEEP。cell_check の docstring 参照)
使い方: python3 audit_lsf_ssa.py IR.ll IMAGE.bin 'CONFIG_GLOB' [--json OUT] [--only VA,VA] [--no-alloca-prop]
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
    depth = 1
    src = None


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


def depth_of(sv):
    """機械語側の値の deref 段数: arg / 不明 = 0、argN の 1 段 deref = 1、global セル・[reg+disp] から読んだポインタ = 1、Ldu = その段数"""
    if sv is None:
        return 0
    if sv[0] == 'ld':
        return 1
    if sv[0] == 'ldu':
        return getattr(sv, 'depth', 1)
    if sv[0] == 'src' and sv[1] in ('rip-mem', 'mem+disp'):
        return 1
    return 0


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
                    newv.depth = 1 + depth_of(sv)
                    newv.src = sv[2] if sv and sv[0] == 'src' else None
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
                SITES[i.address] = dict(kind='lsf', depth=1, cell_src=None, w=w, prov='arg%d' % sv[1], base='arg', disp=o0.mem.disp,
                                        idx=o0.mem.index != 0 or (bool(o0.mem.base) and cs.reg_name(o0.mem.base) == 'rip'), frame=frame, text='%s %s' % (mn, i.op_str))
            elif sv and sv[0] == 'ldu' and sv[1] == w:
                ev.append(('unk', i.address, 0, w, ''))
                SITES[i.address] = dict(kind='unk', depth=sv.depth, cell_src=sv.src, w=w, prov=sv.prov, base=sv.base, disp=o0.mem.disp,
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


def make_depth(defs, allocas, stores):
    """SSA 名 -> IR 側の deref 段数 (値を作る load の入れ子の深さ。定数アドレスからの load = 1、argN / call 戻り / 定数 = 0)。
    reg2mem alloca は store された値の最大を取る。循環は 0 で打ち切る (過小評価 = SHALLOW 側に倒れる)。"""
    ast = collections.defaultdict(list)
    for (_w, v, p) in stores:
        if p in allocas:
            ast[p].append(v)
    memo = {}

    def d(v, stack=()):
        if not v.startswith('%') or v in stack:
            return 0
        if v in memo:
            return memo[v]
        rhs = defs.get(v)
        if rhs is None or rhs.startswith('call') or rhs.startswith('alloca'):
            r = 0
        else:
            m = LOAD_DEF.match(rhs)
            if m:
                p = m.group(2).strip()
                if p in allocas:
                    r = max([d(x, stack + (v,)) for x in ast[p]] or [0])
                else:
                    r = 1 + (d(p, stack + (v,)) if p.startswith('%') else 0)
            else:
                r = max([d(o, stack + (v,)) for o in re.findall(r'%[\w.$-]+', rhs)] or [0])
        memo[v] = r
        return r
    return d


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


IR_CONST_LOAD = re.compile(r'load (i\d+|ptr), ptr inttoptr \(i64 (\d+) to ptr\)')


def cell_check(mach, body, site, alg3):
    """rip 相対セル経由 (機械語: `mov rA,[rip+X]; mov rD,[rA]`) の site を、image の実データで判定する。
    X のセル内容 V (image は reloc 済みの LVA 座標) を読み、IR の定数アドレス load を調べる:
      V を読む load がある            -> FOLDED_OK  (RetDec がセル内容を静的に解決して 1 段化。正しい)
      セル自身 K = X - base を読む load があり、かつ (幅が 64 でない = qword のセルを dword 以下で読んでいる、または alg3 が SHALLOW)。幅 64 の load は、対応する store の値が SHALLOW と確定した時だけ (store が IR に見つからない NOCAND では判定しない)
                                       -> CELL_COLLAPSED (2 段 deref が 1 段に潰れ、変数 V でなくセルを読む = 脱落)
      それ以外                         -> CELL_DEEP (IR に 2 段の連鎖がある、または定数 load が見当たらない)"""
    a = site.get('cell_src')
    if not a or site['prov'] != 'rip-mem':
        return None
    got = list(mach.cs.disasm(mach.read(a - mach.base, 16), a, 1))
    if not got:
        return None
    i = got[0]
    mem = [o for o in i.operands if o.type == capstone.CS_OP_MEM]
    if not mem or mach.cs.reg_name(mem[0].mem.base) != 'rip':
        return None
    x = i.address + i.size + mem[0].mem.disp
    k = x - mach.base
    raw = mach.read(x - mach.base, 8)
    v = int.from_bytes(raw, 'little') if len(raw) == 8 else None
    loads = [(A.width_of(t), int(c)) for t, c in IR_CONST_LOAD.findall(body)]
    w = site['w']
    if v is not None and any(c == v for _t, c in loads):
        r = 'FOLDED_OK'
    elif any(c == k and (t != 64 or alg3 == 'SHALLOW') for t, c in loads):
        r = 'CELL_COLLAPSED'
    else:
        r = 'CELL_DEEP'
    return dict(verdict=r, cell='%x' % x, k='%x' % k, content='%x' % v if v is not None else None, src='%x' % a)


def judge(body, sites):
    """sites: [dict] -> (alg1 per width, alg2 per site, ir_ldst Counter)"""
    defs, allocas, stores = parse_ir(body)
    ld = load_derived(defs, allocas, stores)
    dep = make_depth(defs, allocas, stores)
    ldst = collections.Counter()
    cands = []
    for (w, v, p) in stores:
        if p in allocas:
            continue
        isld = v in ld
        if isld:
            ldst[w] += 1
        cands.append((w, ptr_disp(defs, p), isld, dep(v)))
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
        lsf, _ptr, unk = ms[0], ms[1], ms[2]
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
                                         idx=s['idx'], frame=True, text=s['text'], alg2='FRAME', alg3='FRAME', depth=s['depth'], cell=cell_check(mach, body, s, 'FRAME'), cand=0, cand_ld=0))
                continue
            same = [c for c in cands if c[0] == s['w'] and (s['idx'] or c[1] == s['disp'])]
            nl = sum(1 for c in same if c[2])
            v2 = 'OK' if nl else ('SUSPECT' if same else 'NOCAND')
            v3 = ('OK' if any(c[3] >= s['depth'] for c in same) else 'SHALLOW') if same else 'NOCAND'
            rec['sites'].append(dict(addr='%x' % s['addr'], kind=s['kind'], w=s['w'], prov=s['prov'], base=s['base'], disp=s['disp'],
                                     idx=s['idx'], frame=False, text=s['text'], alg2=v2, alg3=v3, depth=s['depth'], ir_depth=max([c[3] for c in same] or [-1]), cell=cell_check(mach, body, s, v3), cand=len(same), cand_ld=nl))
        fns['%x' % va] = rec
    cnt = collections.Counter()
    a1, a2, a3 = set(), set(), set()
    cnt3 = collections.Counter()
    for v, r in fns.items():
        if any(x['deficit'] > 0 for x in r['alg1']):
            a1.add(v)
        for st in r['sites']:
            cnt['%s/%s/%s' % (st['kind'], 'frame' if st['frame'] else 'store', st['alg2'])] += 1
            if st['alg2'] in ('SUSPECT', 'NOCAND'):
                a2.add(v)
            if st['alg3'] in ('SHALLOW', 'NOCAND'):
                a3.add(v)
                cnt3['%s/%s' % (st['kind'], st['alg3'])] += 1
    tot['alg1_flagged_fns'] = len(a1)
    tot['alg2_flagged_fns'] = len(a2)
    tot['alg3_flagged_fns'] = len(a3)
    tot['alg1_or_alg2_fns'] = len(a1 | a2)
    tot['alg_any_fns'] = len(a1 | a2 | a3)
    out = dict(summary=dict(tot), by_site=dict(cnt), alg1_fns=sorted(a1, key=lambda x: int(x, 16)),
               alg2_fns=sorted(a2, key=lambda x: int(x, 16)), alg3_fns=sorted(a3, key=lambda x: int(x, 16)), by_site_alg3=dict(cnt3), functions=fns)
    print(json.dumps(dict(tot), ensure_ascii=False))
    print(json.dumps(dict(sorted(cnt.items())), ensure_ascii=False))
    print(json.dumps(dict(sorted(cnt3.items())), ensure_ascii=False))
    if a.json:
        json.dump(out, open(a.json, 'w'), indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
