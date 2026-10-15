#!/usr/bin/env python3
"""audit_frame_store_callee_3228.py — ONLY_ENTRY_AFTER_CALL の site の call 越え判定 (#3228 / 親 #2211)。

audit_frame_store_alias_2211.py と同じ CFG 逆向き探索・同じ 3 値判定を使い、call の扱いだけ変える。

前提 (2211 の仮定を引き継ぐ): 呼び出し先が frame の番地を得る経路は、引数・戻り値・メモリだけ。
frame の番地はこの関数の rbp/rsp 派生からしか生まれない (入口の引数は frame の番地ではない)。

各 call の引数 (rcx・rdx・r8・r9) の由来:
  FRAME(K)   直前の定義が [rbp+K] の番地 (lea / mov rbp)
  MAYFRAME   frame 派生の値を書いた slot ([rbp+X]) から読んだ値 (frame の番地かもしれない)
  NONFRAME   入口の値、即値、rip 相対、frame 派生を書いていない slot から読んだ値
  UNKNOWN    判定不能 (分岐をまたぐ・式が複雑) → 打ち切り
呼び出し先の判定 (直接 call のみ。間接 call で frame の番地を渡すと打ち切り):
  FRAME(K) を受けた呼び出し先の機械語で、R (引数) に派生した値の [R+d] への store を caller の [rbp+K+d] への書きと見る。
    - 読みの slot を全て覆う plain store が、分岐も ret も無い先頭の直線部にある → DEF (全経路で定義)
    - 一部だけ重なる・RMW → BARRIER(CALLEE_PARTIAL / CALLEE_RMW)
    - R 由来の値を、レジスタ値として他へ出す (store の値・rax で ret・push・call の引数) → BARRIER(CALLEE_ESCAPE)
    - R 由来の値を添字・base にした別 store、メモリ読みで得た値 (保存された番地かもしれない) を base にした store → BARRIER(CALLEE_TAINTED)
    - 呼び出し先が call を含む → CALLEE_CALL (先の call は見ない)
  MAYFRAME を受けた呼び出し先は、R 由来の書きが 1 つでもあれば BARRIER(CALLEE_MAYFRAME)。
  frame の番地を渡さない call: その関数が frame の番地を外部メモリへ漏らさない (ext_leak が無い) なら透過。
  漏らす関数では CALL (call 越え) のまま残す。

使い方: python3 audit_frame_store_callee_3228.py PE.bin AUDIT.json F4.json OUT.json [--negctl-transparent]
  --negctl-transparent: frame の番地を渡す call を全て透過にする (ネガティブコントロール: 呼び出し先の判定が効いていることの確認用)
"""
import collections
import json
import os
import sys

import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ldmach  # noqa: E402
from ldmach import Machine, memops_of  # noqa: E402
import audit_frame_store_verdict as v1  # noqa: E402
import audit_frame_store_alias_2211 as a2  # noqa: E402

ARG_REGS = ('rcx', 'rdx', 'r8', 'r9')
TRANSPARENT = False


def rnm(cs, rid):
    n = cs.reg_name(rid)
    return ldmach._REG_ALIAS.get(n, n) if n else None


def is_store_to_mem(ins):
    return bool(ins.operands) and ins.operands[0].type == capstone.CS_OP_MEM and a2.writes_dst(ins.mnemonic)


def frame_slots(cs, seq, F):
    """frame 派生の値 (F の reg) を [rbp+X] へ書く store の slot 集合 (base, disp, size)。"""
    out = []
    for x in seq:
        if not is_store_to_mem(x) or len(x.operands) < 2:
            continue
        m = x.operands[0].mem
        if m.base and rnm(cs, m.base) == 'rbp' and not m.index and x.operands[1].type == capstone.CS_OP_REG and rnm(cs, x.operands[1].reg) in F:
            out.append((m.disp, x.operands[0].size or 8))
    return out


def ext_leak(cs, seq, F):
    """frame 派生の値が frame の外のメモリへ書かれるか (base が F 外の store)。"""
    for x in seq:
        if not is_store_to_mem(x) or len(x.operands) < 2:
            continue
        m = x.operands[0].mem
        if m.base and cs.reg_name(m.base) == 'rip':
            base_in = False
        else:
            base_in = bool(m.base) and rnm(cs, m.base) in F
        if base_in or (m.index and rnm(cs, m.index) in F):
            continue
        if x.operands[1].type == capstone.CS_OP_REG and rnm(cs, x.operands[1].reg) in F:
            return True
    return False


def arg_kind(cs, seq, preds, j, reg, slots):
    """call (seq[j]) の引数 reg の由来。戻り値: ('FRAME', K) / ('MAYFRAME',) / ('NONFRAME',) / ('UNKNOWN',)"""
    k = j - 1
    while k >= 0:
        x = seq[k]
        if x.mnemonic.startswith('call'):
            return ('NONFRAME',)
        if x.mnemonic.startswith(('j', 'ret')):
            return ('UNKNOWN',)
        if any(p != x.address for p in preds.get(k + 1, [])) and k + 1 != j:
            return ('UNKNOWN',)
        if x.operands and x.operands[0].type == capstone.CS_OP_REG and rnm(cs, x.operands[0].reg) == reg and a2.writes_dst(x.mnemonic):
            src = x.operands[1] if len(x.operands) == 2 else None
            if src is None:
                return ('UNKNOWN',)
            if x.mnemonic.startswith('lea') and src.type == capstone.CS_OP_MEM:
                m = src.mem
                if m.base and cs.reg_name(m.base) == 'rip':
                    return ('NONFRAME',)
                if m.base and rnm(cs, m.base) == 'rbp' and not m.index:
                    return ('FRAME', m.disp)
                return ('UNKNOWN',)
            if x.mnemonic == 'mov' and src.type == capstone.CS_OP_REG and rnm(cs, src.reg) == 'rbp':
                return ('FRAME', 0)
            if x.mnemonic == 'mov' and src.type == capstone.CS_OP_IMM:
                return ('NONFRAME',)
            if x.mnemonic == 'mov' and src.type == capstone.CS_OP_MEM:
                m = src.mem
                if m.base and cs.reg_name(m.base) == 'rip':
                    return ('NONFRAME',)
                if m.base and rnm(cs, m.base) == 'rbp' and not m.index:
                    hit = any(sd < m.disp + 8 and m.disp < sd + ss for sd, ss in slots)
                    return ('MAYFRAME',) if hit else ('NONFRAME',)
                return ('UNKNOWN',)
            if x.mnemonic == 'xor' and src.type == capstone.CS_OP_REG and rnm(cs, src.reg) == reg:
                return ('NONFRAME',)
            return ('UNKNOWN',)
        k -= 1
    return ('NONFRAME',)


def straight_prefix_end(seq, addr):
    """addr より前に分岐・ret が無いか。"""
    for x in seq:
        if x.address >= addr:
            break
        if x.mnemonic.startswith(('j', 'ret')):
            return False
    return True


def callee_effect(mach, va, R_idx, K, slot):
    """呼び出し先 va の引数 R_idx (rcx=0..r9=3) に caller の [rbp+K] の番地を渡したとき、caller の slot への効果。
    K が None のときは番地の位置が分からない (MAYFRAME)。戻り値: ('NONE',) / ('DEF',) / ('BARRIER', 理由)"""
    cs = mach.cs
    seq = mach.disasm_fn(va) or []
    if not seq or mach.fns.get(va) is None:
        return ('BARRIER', 'CALLEE_NOFN')
    R = ARG_REGS[R_idx]
    sdisp, ssize = slot[1], slot[2]
    T = {R}
    changed = True
    while changed:
        changed = False
        for x in seq:
            if not x.operands or x.operands[0].type != capstone.CS_OP_REG or not a2.writes_dst(x.mnemonic):
                continue
            dst = rnm(cs, x.operands[0].reg)
            if dst is None or dst in T:
                continue
            hit = False
            for op in x.operands[1:]:
                if op.type == capstone.CS_OP_REG and rnm(cs, op.reg) in T:
                    hit = True
                if op.type == capstone.CS_OP_MEM:
                    if (op.mem.base and rnm(cs, op.mem.base) in T) or (op.mem.index and rnm(cs, op.mem.index) in T):
                        hit = True
                    elif not (op.mem.base and (rnm(cs, op.mem.base) in ('rsp', 'rbp') or cs.reg_name(op.mem.base) == 'rip')):
                        hit = True
            if hit:
                T.add(dst)
                changed = True
    if any(x.mnemonic.startswith('call') for x in seq):
        return ('BARRIER', 'CALLEE_CALL')
    if K is None:
        for x in seq:
            if is_store_to_mem(x) and x.operands[0].mem.base and rnm(cs, x.operands[0].mem.base) in T:
                return ('BARRIER', 'CALLEE_MAYFRAME')
        return ('NONE',)
    res = ('NONE',)
    for x in seq:
        m = x.mnemonic
        if not x.operands:
            continue
        op0 = x.operands[0]
        if op0.type == capstone.CS_OP_REG and rnm(cs, op0.reg) == R and a2.writes_dst(m):
            return ('BARRIER', 'CALLEE_REASSIGN')
        if m.startswith('ret') and 'rax' in T:
            return ('BARRIER', 'CALLEE_ESCAPE')
        if m.startswith('push') and op0.type == capstone.CS_OP_REG and rnm(cs, op0.reg) in T:
            return ('BARRIER', 'CALLEE_ESCAPE')
        if is_store_to_mem(x):
            mm = op0.mem
            bn = rnm(cs, mm.base) if mm.base and cs.reg_name(mm.base) != 'rip' else None
            iname = rnm(cs, mm.index) if mm.index else None
            if mm.base and cs.reg_name(mm.base) == 'rip':
                pass
            elif bn == 'rsp' and not iname:
                pass
            elif (bn in T) or (iname in T):
                if bn == R and not iname and bn == R:
                    lo = K + mm.disp
                    hi = lo + (op0.size or 8)
                    if sdisp < hi and lo < sdisp + ssize:
                        if m in ldmach.STORE_MN and lo <= sdisp and sdisp + ssize <= hi and straight_prefix_end(seq, x.address):
                            res = ('DEF',)
                        else:
                            return ('BARRIER', 'CALLEE_PARTIAL')
                else:
                    return ('BARRIER', 'CALLEE_TAINTED')
        for op in x.operands[1:]:
            if op.type == capstone.CS_OP_REG and rnm(cs, op.reg) in T and is_store_to_mem(x):
                return ('BARRIER', 'CALLEE_ESCAPE')
    return res


def effect2(mach, cs, seq, preds, F, glk, leak_ext, slots, sync, slot_in, ins, j, slot):
    if not ins.mnemonic.startswith('call'):
        return a2.effect(cs, glk, F, ins, slot, sync, slot_in)
    if not glk:
        return None
    kinds = [arg_kind(cs, seq, preds, j, r, slots) for r in ARG_REGS]
    kinds = [('MAYFRAME',) if k[0] == 'UNKNOWN' else k for k in kinds]
    frame_args = [(i, k) for i, k in enumerate(kinds) if k[0] in ('FRAME', 'MAYFRAME')]
    if not frame_args:
        return ('CALL',) if leak_ext else None
    if ins.operands[0].type != capstone.CS_OP_IMM:
        return ('BARRIER', 'INDIRECT_FRAMEARG')
    if TRANSPARENT:
        return None
    if slot[0] == 'rsp' and not (sync is not None and sync[0] < ins.address < sync[1]):
        return ('BARRIER', 'MIXED_BASE')
    outs = []
    for i, k in frame_args:
        K = k[1] if k[0] == 'FRAME' else None
        outs.append(callee_effect(mach, ins.operands[0].imm, i, K, slot))
    for o in outs:
        if o[0] == 'BARRIER':
            return o
    if any(o[0] == 'DEF' for o in outs):
        return ('DEF',)
    return ('CALL',) if leak_ext else None


def walk(mach, cs, seq, preds, F, glk, leak_ext, slots, ridx, slot, sync):
    if ridx == 0:
        return {'ENTRY'}, [], []
    slot_in = sync is not None and sync[0] < seq[ridx].address < sync[1]
    outs, stores, barr = set(), [], []
    stack = [(p, False) for p in preds.get(ridx, [])]
    seen = set()
    while stack:
        j, crossed = stack.pop()
        if (j, crossed) in seen:
            continue
        seen.add((j, crossed))
        e = effect2(mach, cs, seq, preds, F, glk, leak_ext, slots, sync, slot_in, seq[j], j, slot)
        if e is not None and e[0] == 'DEF':
            outs.add('STORE')
            stores.append('%x %s %s' % (seq[j].address, seq[j].mnemonic, seq[j].op_str))
            continue
        if e is not None and e[0] == 'BARRIER':
            outs.add('BARRIER:' + e[1])
            barr.append('%x %s %s [%s]' % (seq[j].address, seq[j].mnemonic, seq[j].op_str, e[1]))
            continue
        if e is not None and e[0] == 'CALL':
            crossed = True
        if j == 0:
            outs.add('ENTRY_AFTER_CALL' if crossed else 'ENTRY')
        stack.extend((p, crossed) for p in preds.get(j, []))
    return outs, stores, barr


def main():
    global TRANSPARENT
    args = sys.argv[1:]
    TRANSPARENT = '--negctl-transparent' in args
    args = [a for a in args if not a.startswith('--')]
    pe, audit_path, f4_path, out = args[:4]
    mach = Machine(pe)
    cs = mach.cs
    audit = json.load(open(audit_path))
    f4 = set(json.load(open(f4_path))['f4_vas'])
    rows = [s for s in audit['frame_in_escaped'] if s['fn'] not in f4]
    fns = collections.defaultdict(list)
    for s in rows:
        fns[s['fn']].append(s)
    verdict, fn_info, per_site = {}, {}, []
    for fn, sites in sorted(fns.items()):
        va = int(fn, 16)
        seq = mach.disasm_fn(va) or []
        ent = mach.fns.get(va)
        if not seq or ent is None:
            verdict[fn] = 'UNDETERMINED'
            for s in sites:
                per_site.append(dict(fn=fn, ty=s['ty'], verdict='NOADDR'))
            continue
        preds, ijmp = v1.build_preds(cs, seq, va, ent[1])
        F = a2.frame_derived(cs, seq)
        leaks = a2.leak_sites(cs, seq, F)
        leak = leaks[0] if leaks else None
        glk = leak is not None
        leak_ext = ext_leak(cs, seq, F)
        slots = frame_slots(cs, seq, F)
        sync = a2.sync_range(cs, seq)
        fn_info[fn] = dict(ijmp=ijmp, glk=glk, leak_ext=leak_ext, leak=None if leak is None else '%s [%s]' % leak,
                           frame_slots=['%+#x/%d' % s for s in slots], sync=None if sync is None else '%x-%x' % sync)
        idx_of = {x.address: i for i, x in enumerate(seq)}
        for s in sites:
            addr = int(s['detail'][0].split()[0], 16) if s.get('detail') else None
            ridx = idx_of.get(addr)
            if ridx is None:
                per_site.append(dict(fn=fn, ty=s['ty'], verdict='NOADDR'))
                continue
            ins = seq[ridx]
            rd = next((mo for mo in memops_of(cs, ins) if mo['kind'] in ('load', 'rmw', 'other')), None)
            if rd is None or rd.get('rip_rva') is not None or rd['index'] is not None or rd['base'] not in a2.FRAME_REGS:
                per_site.append(dict(fn=fn, ty=s['ty'], addr='%x' % addr, verdict='PTR_READ'))
                continue
            slot = (rd['base'], rd['disp'], (rd['size_bits'] or 64) // 8)
            outs, stores, barr = walk(mach, cs, seq, preds, F, glk, leak_ext, slots, ridx, slot, sync)
            if ijmp:
                v, why = 'UNDETERMINED', 'IJMP'
            elif any(o.startswith('BARRIER:') for o in outs):
                v = 'UNDETERMINED'
                why = 'BARRIER(' + ','.join(sorted(o[8:] for o in outs if o.startswith('BARRIER:'))) + ')'
            elif outs == {'STORE'}:
                v, why = 'DROP', 'ALL_PATHS_STORE'
            elif outs == {'ENTRY'}:
                v, why = 'LIVE-IN', 'NO_DEF_ON_ANY_PATH'
            elif outs == {'ENTRY_AFTER_CALL'}:
                v, why = 'UNDETERMINED', 'ONLY_ENTRY_AFTER_CALL'
            else:
                v, why = 'UNDETERMINED', 'MIXED_OR_UNREACHABLE'
            per_site.append(dict(fn=fn, ty=s['ty'], addr='%x' % addr, mnem='%s %s' % (ins.mnemonic, ins.op_str),
                                 slot='%s%+#x' % (slot[0], slot[1]), outcomes=sorted(outs), verdict=v, why=why,
                                 store_addrs=stores[:4], barrier_addrs=barr[:4]))
        judged = [p['verdict'] for p in per_site if p['fn'] == fn and p['verdict'] in ('DROP', 'LIVE-IN', 'UNDETERMINED')]
        if judged and all(v == 'DROP' for v in judged):
            verdict[fn] = 'DROP'
        elif judged and all(v == 'LIVE-IN' for v in judged):
            verdict[fn] = 'LIVE-IN'
        else:
            verdict[fn] = 'UNDETERMINED'
    tally = collections.Counter(verdict.values())
    site_tally = collections.Counter(p['verdict'] for p in per_site)
    json.dump(dict(functions=len(verdict), by_verdict=dict(tally), site_by_verdict=dict(site_tally),
                   negctl_transparent=TRANSPARENT, verdict=verdict, fn_info=fn_info, sites=per_site),
              open(out, 'w'), indent=1)
    print('functions', len(verdict), dict(tally), 'sites', dict(site_tally))


if __name__ == '__main__':
    main()
