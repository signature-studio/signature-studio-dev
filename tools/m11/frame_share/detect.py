#!/usr/bin/env python3
"""detect.py: 入れ子手続の親フレーム共有 site を機械語から検出する (D23, #2444 / SHX-T28)。

検出条件 (機械語 = capstone の .pdata 区間の線型逆アセンブル。IR は見ない):
  1. 親関数 P の call 直前 (同一基本ブロック内・最大 12 命令) で rcx に `mov rcx, rbp` または
     `lea rcx, [rbp+K]` が入り、続けて `call <imm>` (callee C) がある。
  2. C の先頭から (線型順に) rcx の別名 (`mov reg, rcx` / `lea reg, [alias+d]` / add・sub imm) を
     追い、別名を base にしたメモリ命令を集める。オフセットは親の rbp 基準 (= rcx の初期値 + disp)。
  3. C が触るオフセットのうち、親 P が rbp 基準で直接触るもの (バイト範囲の重なり) があれば
     「親フレーム共有 site」(shared)。無ければ「callee のみが rbp 経由で触る」(callee_only)。
制限: 制御フローは無視して線型に走る (分岐先の別名状態は区別しない)。32bit 書込みは 64bit 名に畳む。
使い方:
  python3 tools/m11/frame_share/detect.py [--ir work/boot_final3.ll] [--pe PE] [--out work/frame_share.json]
  PE は FL_WIN64_DIR (tools/shared/env.sh) 経由の block00031_PE.bin を既定にする。
"""
import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
M11 = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(M11, 'ldfix'))
from ldmach import Machine, memops_of  # noqa: E402
import capstone  # noqa: E402

DEF_RE = re.compile(r'^define [^@]*@(function_[0-9a-f]+)\(', re.M)
GPR64 = {'rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'rbp', 'rsp', 'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15'}
CALLER_SAVED = {'rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'}
G = {'eax': 'rax', 'ebx': 'rbx', 'ecx': 'rcx', 'edx': 'rdx', 'esi': 'rsi', 'edi': 'rdi', 'ebp': 'rbp', 'esp': 'rsp'}
for i in range(8, 16):
    G['r%dd' % i] = 'r%d' % i


def reg_name(cs, rid):
    n = cs.reg_name(rid) if rid else None
    if not n:
        return None
    n = n.lower()
    if n in G:
        return G[n]
    return n if n in GPR64 else None


def ops_of(cs, ins):
    return ins.operands


def is_reg(op):
    return op.type == capstone.CS_OP_REG


def walk_callee(cs, ins_list, start_off):
    """callee の線型走査。rcx の別名を追い、別名 base のメモリ命令 (addr, kind, size, off, mnem) を返す。"""
    alias = {'rcx': start_off}
    hits = []
    for ins in ins_list:
        for m in memops_of(cs, ins):
            if m.get('rip_rva') is not None or m['index'] is not None:
                continue
            b = m['base']
            if b in alias:
                hits.append(dict(addr=ins.address, mnem=ins.mnemonic, kind=m['kind'],
                                 size=(m['size_bits'] or 0) // 8, off=alias[b] + m['disp']))
        mn = ins.mnemonic
        ops = ops_of(cs, ins)
        if mn == 'call':
            for r in list(alias):
                if r in CALLER_SAVED:
                    del alias[r]
            continue
        if len(ops) >= 1 and is_reg(ops[0]):
            dst = reg_name(cs, ops[0].reg)
            if dst is None:
                continue
            if mn == 'mov' and len(ops) == 2 and is_reg(ops[1]):
                src = reg_name(cs, ops[1].reg)
                if src in alias and ops[0].size == 8:
                    alias[dst] = alias[src]
                elif dst in alias:
                    del alias[dst]
            elif mn == 'lea' and len(ops) == 2 and ops[1].type == capstone.CS_OP_MEM \
                    and ops[1].mem.index == 0 and reg_name(cs, ops[1].mem.base) in alias:
                alias[dst] = alias[reg_name(cs, ops[1].mem.base)] + ops[1].mem.disp
            elif mn in ('add', 'sub') and len(ops) == 2 and ops[1].type == capstone.CS_OP_IMM and dst in alias:
                alias[dst] += ops[1].imm if mn == 'add' else -ops[1].imm
            elif mn in ('cmp', 'test'):
                pass
            elif dst in alias:
                del alias[dst]
    return hits


def call_site_base(cs, ins_list, i):
    """ins_list[i] が call のとき、直前の rcx 設定が rbp 由来なら (base_off, 'mov'|'lea') を返す。無ければ None。
    mov = 親の rbp そのものを渡す (D23 の検出対象)。lea = 局所 1 個の番地を渡す (通常の var 参照渡し・参考のみ)。"""
    for j in range(i - 1, max(-1, i - 13), -1):
        p = ins_list[j]
        if p.mnemonic in ('call', 'jmp', 'ret') or p.mnemonic.startswith('j'):
            return None
        ops = p.operands
        if not ops or not is_reg(ops[0]) or reg_name(cs, ops[0].reg) != 'rcx':
            continue
        if p.mnemonic == 'mov' and len(ops) == 2 and is_reg(ops[1]) and reg_name(cs, ops[1].reg) == 'rbp' \
                and ops[0].size == 8:
            return 0, 'mov'
        if p.mnemonic == 'lea' and len(ops) == 2 and ops[1].type == capstone.CS_OP_MEM \
                and ops[1].mem.index == 0 and reg_name(cs, ops[1].mem.base) == 'rbp':
            return ops[1].mem.disp, 'lea'
        return None
    return None


def parent_rbp_ranges(cs, ins_list):
    """親が rbp 基準で触る (off, size) の集合。"""
    out = set()
    for ins in ins_list:
        for m in memops_of(cs, ins):
            if m['base'] == 'rbp' and m['index'] is None and m.get('rip_rva') is None:
                out.add((m['disp'], (m['size_bits'] or 0) // 8))
    return out


def overlaps(off, size, ranges):
    hit = []
    for (d, s) in ranges:
        if off < d + max(s, 1) and d < off + max(size, 1):
            hit.append(d)
    return sorted(set(hit))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ir', default=os.path.join(M11, 'work', 'boot_final3.ll'))
    ap.add_argument('--pe', default=os.path.join(os.environ.get('FL_WIN64_DIR', ''), 'extracted', 'block00031_PE.bin'))
    ap.add_argument('--out')
    ap.add_argument('--show', default='function_448490', help='この親の site を詳細表示')
    a = ap.parse_args()
    text = open(a.ir, errors='replace').read()
    closure = sorted(set(int(n[len('function_'):], 16) for n in DEF_RE.findall(text)))
    mach = Machine(a.pe)
    cs = mach.cs
    in_closure = set(closure)
    sites = []
    n_rbp_pass = 0
    no_disasm = 0
    for pva in closure:
        pins = mach.disasm_fn(pva)
        if not pins:
            no_disasm += 1
            continue
        prng = parent_rbp_ranges(cs, pins)
        for i, ins in enumerate(pins):
            if ins.mnemonic != 'call' or not ins.operands or ins.operands[0].type != capstone.CS_OP_IMM:
                continue
            got = call_site_base(cs, pins, i)
            if got is None:
                continue
            base, how = got
            n_rbp_pass += 1
            cva = ins.operands[0].imm
            cins = mach.disasm_fn(cva)
            if not cins:
                continue
            hits = walk_callee(cs, cins, base)
            if not hits:
                continue
            offs = collections.OrderedDict()
            for h in hits:
                ov = overlaps(h['off'], h['size'], prng)
                offs.setdefault((h['off'], h['size'], h['kind']), ov)
            shared_offs = sorted(set(o for k, ov in offs.items() for o in ov))
            cls = 'shared' if shared_offs else 'callee_only'
            sites.append(dict(parent='function_%x' % pva, call_at='0x%x' % ins.address,
                              callee='function_%x' % cva, callee_in_closure=cva in in_closure,
                              base_off=base, how=how, cls=cls,
                              callee_access=[dict(off=k[0], size=k[1], kind=k[2]) for k in offs],
                              parent_overlap=['0x%x' % o for o in shared_offs]))
    mov = [s for s in sites if s['how'] == 'mov']
    shared = [s for s in mov if s['cls'] == 'shared']
    summary = dict(ir=os.path.relpath(a.ir, M11), closure_functions=len(closure),
                   closure_without_disasm=no_disasm,
                   calls_with_rcx_from_rbp=n_rbp_pass,
                   mov_rbp_sites_callee_frame_access=len(mov),
                   d23_shared_sites=len(shared),
                   d23_shared_parent_fns=len(set(s['parent'] for s in shared)),
                   d23_shared_callee_fns=len(set(s['callee'] for s in shared)),
                   d23_shared_parents=sorted(set(s['parent'] for s in shared)),
                   d23_shared_callees=sorted(set(s['callee'] for s in shared)),
                   mov_rbp_callee_only_sites=len(mov) - len(shared),
                   lea_sites_with_callee_frame_access=len(sites) - len(mov))
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print('-- sites with parent=%s --' % a.show)
    for s in sites:
        if s['parent'] == a.show:
            print(json.dumps(s, ensure_ascii=False))
    if a.out:
        with open(a.out, 'w') as f:
            json.dump(dict(summary=summary, sites=sites), f, ensure_ascii=False, indent=1)
            f.write('\n')


if __name__ == '__main__':
    main()
