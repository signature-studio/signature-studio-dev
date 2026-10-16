#!/usr/bin/env python3
"""cfg_check.py: 301 site の call 直前 rcx が親の rbp 由来かを、制御フローを考慮して機械語で確定する (#5575 / SHX-T48)。

確定条件 (site ごと・親関数 P の機械語):
  - 直前の `mov rcx, rbp` (位置 j) から call (位置 i) までの線型区間 (j, i] に、分岐先 (合流点) が無い。
    無ければ、call に到達する実行経路は必ず j を通る (区間への入口は j からの fallthrough だけ)。
  - 区間 (j, i) に rcx (ecx/cx/cl を含む) への書込みが無い。
  - P の rbp は prologue の `mov rbp, rsp` 以外で書かれていない (関数全体。エピローグの `pop rbp` は除く)。
上の 3 条件をすべて満たす site を `confirmed` とする。満たさないものは理由を付けて残す。
callee 側は site_check.site_record の access_class (write_local / read_local / arg_home_only) を使う。

使い方:
  FL_WIN64_DIR=<展開先> python3 frame_share/cfg_check.py --sites work/base_check.json --out work/cfg_check.json
"""
import argparse
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
M11 = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(M11, 'ldfix'))
sys.path.insert(0, HERE)
from ldmach import Machine  # noqa: E402
import detect  # noqa: E402
import site_check  # noqa: E402
import capstone  # noqa: E402

RCX_ALIAS = {'rcx', 'ecx', 'cx', 'cl', 'ch'}
WRITERS_NOT_DST = {'cmp', 'test', 'push', 'call', 'jmp', 'ret'}


def dst_reg(cs, ins):
    ops = ins.operands
    if not ops or ops[0].type != capstone.CS_OP_REG:
        return None
    return (cs.reg_name(ops[0].reg) or '').lower()


def jump_targets(pins):
    out = set()
    for x in pins:
        if x.mnemonic.startswith('j') or x.mnemonic in ('loop', 'loope', 'loopne', 'jrcxz'):
            if x.operands and x.operands[0].type == capstone.CS_OP_IMM:
                out.add(x.operands[0].imm)
    return out


def rbp_written_elsewhere(cs, pins):
    hits = []
    for x in pins:
        if x.mnemonic in WRITERS_NOT_DST or x.mnemonic == 'pop':
            continue
        d = dst_reg(cs, x)
        if d == 'rbp' or d == 'ebp' or d == 'bp':
            if x.mnemonic == 'mov' and x.op_str == 'rbp, rsp':
                continue
            hits.append('0x%x %s %s' % (x.address, x.mnemonic, x.op_str))
    return hits


def judge(cs, pins, targets, rbp_bad, i, cva):
    """pins[i] が call (VA cva) のときの判定。"""
    if rbp_bad:
        return 'rbp_written', None
    j = None
    for k in range(i - 1, max(-1, i - 13), -1):
        p = pins[k]
        if p.mnemonic in ('call', 'jmp', 'ret') or p.mnemonic.startswith('j'):
            break
        if p.mnemonic == 'mov' and p.op_str.lower().replace('qword ptr ', '') == 'rcx, rbp':
            j = k
            break
    if j is None:
        return 'no_mov', None
    mov_va = pins[j].address
    for t in targets:
        if mov_va < t <= cva:
            return 'label_between', '0x%x' % t
    for k in range(j + 1, i):
        if dst_reg(cs, pins[k]) in RCX_ALIAS:
            return 'rcx_rewritten', '0x%x' % pins[k].address
    return 'confirmed', '0x%x' % mov_va


def step(cs, ins, alias, hits):
    """detect.walk_callee の 1 命令分の処理。alias (reg -> 親 rbp 基準の off) を in-place で更新し、メモリ命令を hits に追加する。"""
    for m in detect.memops_of(cs, ins):
        if m.get('rip_rva') is not None or m['index'] is not None:
            continue
        b = m['base']
        if b in alias:
            hits.append(dict(addr=ins.address, kind=m['kind'], size=(m['size_bits'] or 0) // 8,
                             off=alias[b] + m['disp']))
    mn = ins.mnemonic
    ops = detect.ops_of(cs, ins)
    if mn == 'call':
        for r in list(alias):
            if r in detect.CALLER_SAVED:
                del alias[r]
        return
    if len(ops) >= 1 and detect.is_reg(ops[0]):
        dst = detect.reg_name(cs, ops[0].reg)
        if dst is None:
            return
        if mn == 'mov' and len(ops) == 2 and detect.is_reg(ops[1]):
            src = detect.reg_name(cs, ops[1].reg)
            if src in alias and ops[0].size == 8:
                alias[dst] = alias[src]
            elif dst in alias:
                del alias[dst]
        elif mn == 'lea' and len(ops) == 2 and ops[1].type == capstone.CS_OP_MEM \
                and ops[1].mem.index == 0 and detect.reg_name(cs, ops[1].mem.base) in alias:
            alias[dst] = alias[detect.reg_name(cs, ops[1].mem.base)] + ops[1].mem.disp
        elif mn in ('add', 'sub') and len(ops) == 2 and ops[1].type == capstone.CS_OP_IMM and dst in alias:
            alias[dst] += ops[1].imm if mn == 'add' else -ops[1].imm
        elif mn in ('cmp', 'test'):
            pass
        elif dst in alias:
            del alias[dst]


def walk_callee_flow(cs, mach, cva, start_off):
    """callee を基本ブロックに分けて、別名の状態を流れに沿って追う。合流では値が一致する別名だけ残す (保守的)。
    戻り値: (hits, ok)。ok=False は間接ジャンプ等で追えなかったことを表す (その場合 hits は使わない)。"""
    ins_list = mach.disasm_fn(cva)
    if not ins_list:
        return [], False
    by_va = {x.address: k for k, x in enumerate(ins_list)}
    leaders = {0}
    for k, x in enumerate(ins_list):
        if x.mnemonic.startswith('j') or x.mnemonic in ('loop', 'loope', 'loopne', 'jrcxz'):
            if not (x.operands and x.operands[0].type == capstone.CS_OP_IMM and x.operands[0].imm in by_va):
                return [], False
            leaders.add(by_va[x.operands[0].imm])
            if k + 1 < len(ins_list):
                leaders.add(k + 1)
        if x.mnemonic in ('ret', 'jmp') and k + 1 < len(ins_list):
            leaders.add(k + 1)
    starts = sorted(leaders)
    blk_of = {}
    blocks = []
    for n, s in enumerate(starts):
        e = starts[n + 1] if n + 1 < len(starts) else len(ins_list)
        blocks.append((s, e))
        for k in range(s, e):
            blk_of[k] = n

    def succ(n):
        s, e = blocks[n]
        last = ins_list[e - 1]
        out = []
        if last.mnemonic == 'ret':
            return out
        if last.mnemonic == 'jmp':
            return [blk_of[by_va[last.operands[0].imm]]]
        if last.mnemonic.startswith('j') or last.mnemonic in ('loop', 'loope', 'loopne', 'jrcxz'):
            out.append(blk_of[by_va[last.operands[0].imm]])
        if e < len(ins_list):
            out.append(blk_of[e])
        return out

    state_in = {0: {'rcx': start_off}}
    work = [0]
    out_state = {}
    while work:
        n = work.pop()
        alias = dict(state_in[n])
        s, e = blocks[n]
        for k in range(s, e):
            step(cs, ins_list[k], alias, [])
        if out_state.get(n) == alias:
            continue
        out_state[n] = alias
        for t in succ(n):
            if t not in state_in:
                state_in[t] = dict(alias)
                work.append(t)
            else:
                merged = {r: v for r, v in state_in[t].items() if alias.get(r) == v}
                if merged != state_in[t]:
                    state_in[t] = merged
                    work.append(t)
    hits = []
    for n in state_in:
        alias = dict(state_in[n])
        s, e = blocks[n]
        for k in range(s, e):
            step(cs, ins_list[k], alias, hits)
    return hits, True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sites', required=True, help='base_check.json (301 site)')
    ap.add_argument('--out', required=True)
    ap.add_argument('--pe', default=os.path.join(os.environ.get('FL_WIN64_DIR', ''), 'extracted', 'block00031_PE.bin'))
    a = ap.parse_args()
    mach = Machine(a.pe)
    cs = mach.cs
    sites = json.load(open(a.sites))['sites']
    cache = {}
    recs = []
    for s in sites:
        p = s['parent']
        if p not in cache:
            pva = int(p.split('_')[1], 16)
            pins = mach.disasm_fn(pva) or []
            cache[p] = (pins, jump_targets(pins), rbp_written_elsewhere(cs, pins))
        pins, targets, rbp_bad = cache[p]
        cva = int(s['call_at'], 16)
        idx = [k for k, x in enumerate(pins) if x.address == cva]
        if not idx:
            recs.append(dict(parent=p, call_at=s['call_at'], verdict='call_not_in_disasm'))
            continue
        i = idx[0]
        verdict, where = judge(cs, pins, targets, rbp_bad, i, cva)
        r = site_check.site_record(mach, cs, pins, i, (0, 'mov'), pins[i], p)
        r['call_at'] = s['call_at']
        r['base_verdict'] = s.get('verdict')
        r['cfg_verdict'] = verdict
        r['cfg_where'] = where
        r['access_class'] = site_check.access_class(r)
        fhits, fok = walk_callee_flow(cs, mach, int(r['callee'].split('_')[1], 16), 0)
        r['flow_ok'] = fok
        if fok:
            acc = sorted(set((h['off'], h['size'], h['kind']) for h in fhits))
            r['flow_access'] = [dict(off=o, size=z, kind=k) for (o, z, k) in acc]
            r['flow_class'] = site_check.access_class(dict(callee_access=r['flow_access']))
            key = lambda L: sorted((x['off'], x['size'], x['kind']) for x in L)
            r['flow_same'] = key(r['flow_access']) == key(r['callee_access'])
        if rbp_bad:
            r['rbp_writes'] = rbp_bad[:3]
        recs.append(r)
    cnt = collections.Counter(r['cfg_verdict'] for r in recs)
    cls = collections.Counter((r['cfg_verdict'], r['access_class']) for r in recs if 'access_class' in r)
    print(json.dumps(dict(sites=len(recs), cfg=dict(cnt)), ensure_ascii=False))
    print(json.dumps({'%s/%s' % k: v for k, v in sorted(cls.items())}, ensure_ascii=False, indent=1))
    json.dump(dict(sites=recs), open(a.out, 'w'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
