#!/usr/bin/env python3
"""audit_frame_store_alias_2211.py — FRAME_IN_ESCAPED 残件の別名・呼び出し越えの判定 (#2211 / 親 #2185)。

audit_frame_store_verdict.py (#2185) と同じ CFG 逆向き探索・同じ 3 値判定を使う。違いは次の 4 点だけ:
  1. メモリ参照の読み書きを命令内の位置で決める (mem が第 1 オペランドのときだけ書き)。
     旧判定は `sub ecx, [rax]` のような読みを RMW として書きと見なし、打ち切っていた。
  2. 読みは定義にならないので透過する。旧判定は frame 基底の重なる読みで打ち切っていた。
  3. 漏出 (glk): frame 派生レジスタ F (rbp/rsp と、lea・mov・算術で得た値) が
     メモリへ書かれる / call の引数 (rcx, rdx, r8, r9) に入る / rax で ret する、のいずれかが
     関数内にあれば glk=True。glk が無い関数では
       - ポインタ経由の store は frame に届かない (別名なし) → 透過
       - call は frame を得られない → 透過 (CALL にしない)
     glk が有る関数では旧判定と同じく、ポインタ store と call で打ち切る。
  4. rbp = rsp の区間 (sync_range) では rsp と rbp を同じ frame 座標として比べる。
     区間は `mov rbp, rsp` (rsp のみの関数では `sub rsp, N`) からエピローグの
     `lea rsp, [rbp+N]` (または `add rsp, N`) まで。区間内で rsp が動かず、区間外から飛び込む分岐が無い場合だけ有効。
  5. 打ち切りの理由を分けて記録する: ALIAS_FRAME_PTR (F のポインタ経由 store) /
     LEAK_STORE (glk 関数のポインタ store) / MIXED_BASE (区間外の rsp・rbp 混在) /
     INDEXED / PARTIAL_OR_RMW (部分重なり・RMW) / CALL (glk 関数の call)。

仮定 (未検証): 呼び出し先が frame を得る経路は引数・戻り値・メモリ (漏出) だけ。
保存レジスタ rbp を呼び出し先が読んで外へ出すケースは見ない。戻り値は rax のみを見る。
glk 関数の call は呼び出し先の書き込みを見ていない (子 issue の範囲)。
frame アドレスを自分の frame に書く store (`mov [rbp+X], rbp`) も漏出と数える (保守的)。

使い方: python3 audit_frame_store_alias_2211.py PE.bin AUDIT.json F4.json OUT.json [--negctl-glk] [--negctl-nosync]
  --negctl-glk:    全関数の glk を強制 True にする (ネガティブコントロール: 漏出規則が効いていることの確認用)
  --negctl-nosync: 区間 sync を無効にする (ネガティブコントロール: rsp/rbp 同一視の規則が効いていることの確認用)
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

FRAME_REGS = ('rbp', 'rsp')
ARG_REGS = ('rcx', 'rdx', 'r8', 'r9')
NO_WRITE_PREFIX = ('test', 'ucomi', 'comi', 'vucomi', 'vcomi', 'push', 'call', 'j', 'ret', 'nop')
STORE_MN = ldmach.STORE_MN


def rname(cs, rid):
    n = cs.reg_name(rid)
    if not n:
        return None
    return ldmach._REG_ALIAS.get(n, n)


def is_read_only(m):
    if m == 'bt':
        return True
    return m.startswith(('cmp', 'test', 'ucomi', 'comi', 'vucomi', 'vcomi')) and not m.startswith('cmpxchg')


def writes_dst(m):
    return not (m.startswith(NO_WRITE_PREFIX) or is_read_only(m) or m.startswith('lea'))


def frame_derived(cs, seq):
    """frame 派生レジスタ集合 F (flow-insensitive の不動点)。rbp/rsp を含む。"""
    F = {'rbp', 'rsp'}
    changed = True
    while changed:
        changed = False
        for ins in seq:
            ops = ins.operands
            if not ops or ops[0].type != capstone.CS_OP_REG or not writes_dst(ins.mnemonic):
                continue
            dst = rname(cs, ops[0].reg)
            if dst is None or dst in F:
                continue
            src = False
            for op in ops[1:]:
                if op.type == capstone.CS_OP_REG and rname(cs, op.reg) in F:
                    src = True
                elif op.type == capstone.CS_OP_MEM and ins.mnemonic.startswith('lea'):
                    if (op.mem.base and rname(cs, op.mem.base) in F) or (op.mem.index and rname(cs, op.mem.index) in F):
                        src = True
            if src:
                F.add(dst)
                changed = True
    return F


def leak_site(cs, seq, F):
    """漏出の最初の命令 (addr, 理由) を返す。無ければ None。"""
    for ins in seq:
        ops = ins.operands
        m = ins.mnemonic
        a = '%x %s %s' % (ins.address, m, ins.op_str)
        if m.startswith('call'):
            if any(r in F for r in ARG_REGS):
                return a, 'CALL_ARG'
            continue
        if m.startswith('ret'):
            if 'rax' in F:
                return a, 'RET_PTR'
            continue
        if ops and ops[0].type == capstone.CS_OP_MEM and writes_dst(m):
            if any(op.type == capstone.CS_OP_REG and rname(cs, op.reg) in F for op in ops[1:]):
                return a, 'STORE_PTR'
    return None


NO_SYNC = False


def sync_range(cs, seq):
    """rbp = rsp の区間 (A, L) を返す。A は `mov rbp, rsp`、L は エピローグの `lea rsp, [rbp+N]`。
    区間内で rsp・rbp が書かれず、区間の外から飛び込む分岐が無いときだけ有効 (それ以外は None)。"""
    if NO_SYNC:
        return None
    movs = [x.address for x in seq if x.mnemonic == 'mov' and x.op_str == 'rbp, rsp']
    if len(movs) > 1:
        return None
    if movs:
        A = movs[0]
        lea = [x.address for x in seq if x.address > A and x.mnemonic == 'lea' and x.op_str.startswith('rsp, [rbp')]
        if not lea:
            return None
        L = lea[0]
    else:
        subs = [x.address for x in seq if x.mnemonic == 'sub' and x.op_str.startswith('rsp, ')]
        if not subs:
            return None
        A = subs[0]
        adds = [x.address for x in seq if x.address > A and x.mnemonic == 'add' and x.op_str.startswith('rsp, ')]
        if not adds:
            return None
        L = adds[0]
    for x in seq:
        if x.mnemonic.startswith('j') and x.operands and x.operands[0].type == capstone.CS_OP_IMM:
            t = x.operands[0].imm
            if seq[0].address <= t <= A:
                return None
            if A < t < L and not (A < x.address < L):
                return None
    for x in seq:
        if A < x.address < L and x.operands and x.operands[0].type == capstone.CS_OP_REG and writes_dst(x.mnemonic):
            if rname(cs, x.operands[0].reg) in ('rsp', 'rbp'):
                return None
        if A < x.address < L and x.mnemonic in ('push', 'pop', 'leave'):
            return None
    return (A, L)


def effect(cs, glk, F, ins, slot, sync=None, slot_in=False):
    """命令 ins が slot (base, disp, size) に対して行うこと。
    None (透過) / ('DEF',) / ('BARRIER', 理由) / ('CALL',)
    sync: rbp = rsp の区間 (A, L)。区間内で slot_in (読みの位置も区間内) のとき rsp・rbp は同じ frame 座標。"""
    m = ins.mnemonic
    if m.startswith('call'):
        return ('CALL',) if glk else None
    if is_read_only(m) or m.startswith('lea'):
        return None
    base, sdisp, ssize = slot
    in_sync = sync is not None and sync[0] < ins.address < sync[1]
    res = None
    for mi, op in enumerate(ins.operands):
        if op.type != capstone.CS_OP_MEM:
            continue
        if op.mem.base and cs.reg_name(op.mem.base) == 'rip':
            continue
        write = (mi == 0 or m.startswith(('xchg', 'xadd', 'cmpxchg'))) and writes_dst(m)
        if not write:
            continue
        size = op.size or 8
        bname = rname(cs, op.mem.base) if op.mem.base else None
        iname = rname(cs, op.mem.index) if op.mem.index else None
        if bname in FRAME_REGS:
            if op.mem.index:
                return ('BARRIER', 'INDEXED')
            same = bname == base and (bname == 'rbp' or (in_sync and slot_in))
            if not same and not (in_sync and slot_in):
                return ('BARRIER', 'MIXED_BASE')
            lo, hi = op.mem.disp, op.mem.disp + size
            if m in STORE_MN and mi == 0:
                if lo <= sdisp and sdisp + ssize <= hi:
                    res = ('DEF',)
                    continue
            if lo < sdisp + ssize and sdisp < hi:
                return ('BARRIER', 'PARTIAL_OR_RMW')
            continue
        if bname in F or iname in F:
            return ('BARRIER', 'ALIAS_FRAME_PTR')
        if glk:
            return ('BARRIER', 'LEAK_STORE')
    return res


def walk(cs, seq, preds, glk, F, ridx, slot, sync):
    """読み ridx から逆向きに辿る。戻り値: (outcome 集合, store 命令, barrier 命令)"""
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
        e = effect(cs, glk, F, seq[j], slot, sync, slot_in)
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
    global NO_SYNC
    args = sys.argv[1:]
    force_glk = '--negctl-glk' in args
    NO_SYNC = '--negctl-nosync' in args
    args = [a for a in args if not a.startswith('--')]
    pe, audit_path, f4_path, out = args[:4]
    mach = Machine(pe)
    audit = json.load(open(audit_path))
    f4 = set(json.load(open(f4_path))['f4_vas'])
    rows = [s for s in audit['frame_in_escaped'] if s['fn'] not in f4]
    fns = collections.defaultdict(list)
    for s in rows:
        fns[s['fn']].append(s)
    verdict = {}
    fn_info = {}
    per_site = []
    for fn, sites in sorted(fns.items()):
        va = int(fn, 16)
        seq = mach.disasm_fn(va) or []
        ent = mach.fns.get(va)
        if not seq or ent is None:
            verdict[fn] = 'UNDETERMINED'
            fn_info[fn] = dict(reason='NOFN')
            for s in sites:
                per_site.append(dict(fn=fn, ty=s['ty'], verdict='NOADDR'))
            continue
        esc = v1.frame_escaped(mach.cs, seq)
        preds, ijmp = v1.build_preds(mach.cs, seq, va, ent[1])
        F = frame_derived(mach.cs, seq)
        leak = leak_site(mach.cs, seq, F)
        glk = (leak is not None) or force_glk
        sync = sync_range(mach.cs, seq)
        fn_info[fn] = dict(escaped=esc, ijmp=ijmp, n_ins=len(seq), glk=glk,
                           leak=None if leak is None else '%s [%s]' % leak,
                           derived=sorted(F - set(FRAME_REGS)),
                           sync=None if sync is None else '%x-%x' % sync)
        idx_of = {x.address: i for i, x in enumerate(seq)}
        for s in sites:
            addr = int(s['detail'][0].split()[0], 16) if s.get('detail') else None
            ridx = idx_of.get(addr)
            if ridx is None:
                per_site.append(dict(fn=fn, ty=s['ty'], verdict='NOADDR'))
                continue
            ins = seq[ridx]
            rd = next((mo for mo in memops_of(mach.cs, ins) if mo['kind'] in ('load', 'rmw', 'other')), None)
            if rd is None or rd.get('rip_rva') is not None or rd['index'] is not None or rd['base'] not in FRAME_REGS:
                per_site.append(dict(fn=fn, ty=s['ty'], addr='%x' % addr,
                                     mnem='%s %s' % (ins.mnemonic, ins.op_str), verdict='PTR_READ'))
                continue
            slot = (rd['base'], rd['disp'], (rd['size_bits'] or 64) // 8)
            outs, stores, barr = walk(mach.cs, seq, preds, glk, F, ridx, slot, sync)
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
                   negctl_glk=force_glk, verdict=verdict, fn_info=fn_info, sites=per_site),
              open(out, 'w'), indent=1)
    print('functions', len(verdict), dict(tally), 'sites', dict(site_tally))


if __name__ == '__main__':
    main()
