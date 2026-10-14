#!/usr/bin/env python3
"""audit_frame_store_verdict.py — FRAME_IN_ESCAPED 候補の 3 値判定 (#2185 / #2144 残件 / #1866)。

入力: 旧監査の結果 JSON (audit_undefload_564_full.json 形式) と F4 修復済み関数リスト (f4_564_post.json)。
各 FRAME_IN_ESCAPED site の読み (機械語 !insn.addr の命令) について、同じ関数の機械語 CFG を逆向きに辿り、
同じ frame slot への書き込みに達するかを見る。分岐・合流はブロック境界として CFG の辺で越える
(直前の straight-line 区間だけを見る旧判定は行わない)。

経路の辿りで最初に当たった事象で分類する (各ノードの効果は経路に依存しない):
  STORE    slot を完全に覆う rbp/rsp 基底の単純 store → その経路の reaching def
  ENTRY    関数先頭まで store に当たらない → 関数内で定義されない (caller 由来 / 未初期化)
  BARRIER  判定を打ち切る事象:
           - slot が関数内でアドレス取得されている (escaped) 場合の call・ポインタ経由 store
           - 基底が異なる / 部分的に重なる / RMW・indexed の rbp/rsp store
  関数内に間接 jmp (IJMP) がある場合は CFG が不完全なので全 site を未判定とする。

site 判定:
  DROP         全経路が STORE → 機械語上は store があるのに IR の読みが undef (脱落候補)
  LIVE-IN      全経路が ENTRY → 関数内に定義が無い (live-in 候補)
  UNDETERMINED 上記以外 (経路の混在・BARRIER・IJMP・到達不能)
  NOADDR / NOSLOT  命令特定不可 / slot (rbp・rsp 基底の単純メモリ) 以外
関数判定: 判定可能な site が全て DROP なら DROP、全て LIVE-IN なら LIVE-IN、それ以外 UNDETERMINED。

近似: escaped 判定は lea と「dst が rbp/rsp 以外の mov への rbp/rsp 値の複製」だけを見る。
確定判定ではない (別名・動的な rsp 変動は見ない)。

使い方: python3 audit_frame_store_verdict.py PE.bin AUDIT.json F4.json OUT.json
"""
import collections
import json
import os
import sys

import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ldmach import Machine, memops_of  # noqa: E402

READ_ONLY_PREFIX = ('cmp', 'test', 'ucomi', 'comi', 'vucomi', 'vcomi')
FRAME_REGS = ('rbp', 'rsp')


def jtarget(cs, ins):
    if ins.operands and ins.operands[0].type == capstone.CS_OP_IMM:
        return ins.operands[0].imm
    return None


def frame_escaped(cs, seq):
    for ins in seq:
        ops = ins.operands
        if ins.mnemonic.startswith('lea'):
            for op in ops:
                if op.type == capstone.CS_OP_MEM and op.mem.base and cs.reg_name(op.mem.base) in FRAME_REGS:
                    return True
        elif ins.mnemonic.startswith('mov') and len(ops) == 2 and ops[0].type == capstone.CS_OP_REG \
                and ops[1].type == capstone.CS_OP_REG and cs.reg_name(ops[1].reg) in FRAME_REGS \
                and cs.reg_name(ops[0].reg) not in FRAME_REGS:
            return True
    return False


def build_preds(cs, seq, va, size):
    """逆向き辺 (node index -> predecessor indices) と間接 jmp の有無"""
    addr_idx = {x.address: i for i, x in enumerate(seq)}
    hi = va + size
    preds = collections.defaultdict(list)
    ijmp = False
    for i, x in enumerate(seq):
        m = x.mnemonic
        nxt = i + 1 if i + 1 < len(seq) else None
        if m.startswith('ret'):
            continue
        if m == 'jmp' or m.startswith('j'):
            t = jtarget(cs, x)
            if t is not None and va <= t < hi and t in addr_idx:
                preds[addr_idx[t]].append(i)
            else:
                ijmp = True
            if m == 'jmp':
                continue
        if nxt is not None:
            preds[nxt].append(i)
    return preds, ijmp


def effect(cs, esc, ins, slot):
    """命令 ins が slot (base, disp, size) に対して行うこと: 'BARRIER' / 'DEF' / None (透過)"""
    m = ins.mnemonic
    if m.startswith('call'):
        return 'BARRIER' if esc else None
    if m.startswith(READ_ONLY_PREFIX) or m == 'bt':
        return None
    base, sdisp, ssize = slot
    res = None
    for mo in memops_of(cs, ins):
        if mo['kind'] == 'load' or mo.get('rip_rva') is not None:
            continue
        size = (mo['size_bits'] or 64) // 8
        if mo['base'] in FRAME_REGS:
            if mo['index'] is not None or mo['base'] != base:
                return 'BARRIER'
            lo, hi = mo['disp'], mo['disp'] + size
            if mo['kind'] != 'store':
                if lo < sdisp + ssize and sdisp < hi:
                    return 'BARRIER'
                continue
            if lo <= sdisp and sdisp + ssize <= hi:
                res = 'DEF'
            elif lo < sdisp + ssize and sdisp < hi:
                return 'BARRIER'
        elif esc:
            return 'BARRIER'
    return res


def walk(cs, seq, preds, esc, ridx, slot):
    """読み ridx から逆向きに辿る。戻り値: (outcome 集合, store 命令 addr, barrier 命令 addr)"""
    if ridx == 0:
        return {'ENTRY'}, [], []
    outs, stores, barr = set(), [], []
    stack = list(preds.get(ridx, []))
    seen = set()
    while stack:
        j = stack.pop()
        if j in seen:
            continue
        seen.add(j)
        e = effect(cs, esc, seq[j], slot)
        if e == 'DEF':
            outs.add('STORE')
            stores.append('%x %s %s' % (seq[j].address, seq[j].mnemonic, seq[j].op_str))
            continue
        if e == 'BARRIER':
            outs.add('BARRIER')
            barr.append('%x %s %s' % (seq[j].address, seq[j].mnemonic, seq[j].op_str))
            continue
        if j == 0:
            outs.add('ENTRY')
        stack.extend(preds.get(j, []))
    return outs, stores, barr


def main():
    pe, audit_path, f4_path, out = sys.argv[1:5]
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
        esc = frame_escaped(mach.cs, seq)
        preds, ijmp = build_preds(mach.cs, seq, va, ent[1])
        fn_info[fn] = dict(escaped=esc, ijmp=ijmp, n_ins=len(seq))
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
                per_site.append(dict(fn=fn, ty=s['ty'], addr='%x' % addr, verdict='NOSLOT'))
                continue
            slot = (rd['base'], rd['disp'], (rd['size_bits'] or 64) // 8)
            outs, stores, barr = walk(mach.cs, seq, preds, esc, ridx, slot)
            if ijmp:
                v = 'UNDETERMINED'
                why = 'IJMP'
            elif 'BARRIER' in outs:
                v, why = 'UNDETERMINED', 'BARRIER'
            elif outs == {'STORE'}:
                v, why = 'DROP', 'ALL_PATHS_STORE'
            elif outs == {'ENTRY'}:
                v, why = 'LIVE-IN', 'NO_DEF_ON_ANY_PATH'
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
                   verdict=verdict, fn_info=fn_info, sites=per_site),
              open(out, 'w'), indent=1)
    print('functions', len(verdict), dict(tally), 'sites', dict(site_tally))


if __name__ == '__main__':
    main()
