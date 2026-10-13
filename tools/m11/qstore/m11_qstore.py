#!/usr/bin/env python3
"""m11_qstore.py — 64bit スタック局所への即値 store が IR で 4B に縮む欠陥 (D17 案, #516) の検出 + 修復 pass.

機械語 `mov qword ptr [rbp|rsp + d], imm32` (8B store, imm は符号拡張) が、RetDec IR では
  `store ptr null, ptr %stack_var_N`   (wasm32 の ptr = 4B) または
  `store i32 imm, ptr %stack_var_N`    (4B)
に縮む。上位 4B は未初期化のまま残り、8B で読む側 (C 転記の Q() 等) が非 0 のゴミを拾う
(idx 87 = 0x59f9a0, idx 898 = 0x1306110 の実退行; tools/m11/REPORT.md §11)。

方針 (alloca pass R7 を machine 正本化): 機械語 (capstone, .pdata 区間) で slot 単位に突合し、
**確定した site だけ** `store i64 <sext imm>` に書換える。IR 側 alloca が 8B 未満なら `alloca i64` に拡幅する。
  slot N = entry rsp 基準のオフセット (RetDec の `%stack_var_N` 命名と同じ。rbp/rsp 基準の disp は
  entry block の prologue (push/sub rsp/mov rbp,rsp/lea rbp,[rsp+K]) を追跡して換算する)。
  確定条件 (slot N, 値 v ごと): 同 slot に 8B 未満の機械語 store (即値/reg/RMW 問わず) が 1 つも無く、8B store が 1 つ以上ある。
  (verdict `fix` = さらに IR の幅不足 store の個数 == 機械語 qword-imm store (値 v) の個数、`fix_slot` = 個数不一致 or reg 経由の 8B store)。
  8B 未満の機械語 store が同 slot にある (`machine_narrow`) / 機械語に slot store が無い (`no_machine_store`) は書換えず報告のみ。
  直接 `%stack_var_N` (bitcast 別名含む) への store のみ対象。ptrtoint+add 等の計算アドレスは追跡しない (報告で件数を出す)。

使い方: m11_qstore.py <in.ll> <out.ll> --pe PE.bin [--report r.json] [--detect-only] [--sites sites.tsv]
  idempotent: 書換え後は `store i64` になるので 2 回目は不変。
"""
import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'ldfix'))
import capstone  # noqa: E402
from ldmach import Machine, norm_reg  # noqa: E402

DEF_RE = re.compile(r'^define [^@]*@function_(?P<va>[0-9a-f]+)\(')
ALLOCA_RE = re.compile(r'^(\s*)(%stack_var_(-?\d+)) = alloca (?P<ty>[^,]+?)(?P<rest>(?:, align \d+)?)\s*$')
BITCAST_RE = re.compile(r'^\s*(%[\w.$-]+) = bitcast ptr (%stack_var_-?\d+) to ptr\s*$')
STORE_RE = re.compile(r'^(?P<ind>\s*)store (?P<ty>i32|i64|ptr) (?P<val>-?\d+|null), ptr (?P<dst>%[\w.$-]+)(?P<al>, align \d+)?\s*$')
SZ32 = {'i1': 1, 'i8': 1, 'i16': 2, 'i32': 4, 'ptr': 4, 'float': 4}   # datalayout p:32 (boot_final.ll 先頭)


def slot_of(name):
    m = re.match(r'%stack_var_(-?\d+)$', name)
    return int(m.group(1)) if m else None


def prologue_frame(ins_list):
    """entry の制御転送までを追跡 → (rsp_off, rbp_off|None). off = entry rsp からのバイト差"""
    rsp, rbp = 0, None
    for ins in ins_list:
        mn = ins.mnemonic
        if mn in ('call', 'ret', 'jmp') or (mn.startswith('j') and mn != 'jmp'):
            break
        ops = ins.operands
        if mn == 'push':
            rsp -= 8
        elif mn == 'pop':
            rsp += 8
        elif mn in ('sub', 'add') and len(ops) == 2 and ops[0].type == capstone.CS_OP_REG and \
                ops[1].type == capstone.CS_OP_IMM and ins.reg_name(ops[0].reg) == 'rsp':
            rsp += -ops[1].imm if mn == 'sub' else ops[1].imm
        elif mn == 'mov' and len(ops) == 2 and ops[0].type == capstone.CS_OP_REG and ops[1].type == capstone.CS_OP_REG \
                and ins.reg_name(ops[0].reg) == 'rbp' and ins.reg_name(ops[1].reg) == 'rsp':
            rbp = rsp
        elif mn == 'lea' and len(ops) == 2 and ops[0].type == capstone.CS_OP_REG and ops[1].type == capstone.CS_OP_MEM \
                and ins.reg_name(ops[0].reg) == 'rbp' and ins.reg_name(ops[1].mem.base) == 'rsp' and not ops[1].mem.index:
            rbp = rsp + ops[1].mem.disp
    return rsp, rbp


def machine_stores(mach, va):
    """関数の stack store を slot 単位で収集 → {(slot, size_bytes, imm|None): [addr...]} (imm = 即値 store の値, 符号付き)"""
    ins_list = mach.disasm_fn(va)
    if ins_list is None:
        return None
    rsp, rbp = prologue_frame(ins_list)
    out = collections.defaultdict(list)
    cs = mach.cs
    for ins in ins_list:
        mn = ins.mnemonic
        if not ins.operands:
            continue
        op0 = ins.operands[0]
        if op0.type != capstone.CS_OP_MEM or mn in ('lea', 'cmp', 'test', 'push', 'call', 'jmp'):
            continue
        mem = op0.mem
        if mem.index:
            continue
        base = norm_reg(cs, mem.base) if mem.base else None
        if base == 'rbp' and rbp is not None:
            slot = rbp + mem.disp
        elif base == 'rsp':
            slot = rsp + mem.disp
        else:
            continue
        imm = None
        if mn == 'mov' and len(ins.operands) == 2 and ins.operands[1].type == capstone.CS_OP_IMM:
            imm = ins.operands[1].imm
        out[(slot, op0.size, imm)].append(ins.address)
    return out


def scan_functions(lines):
    """[(va_hex, start_idx, end_idx)] (define 行 .. '}')"""
    out, cur = [], None
    for i, l in enumerate(lines):
        m = DEF_RE.match(l)
        if m:
            cur = (m.group('va'), i)
        elif cur and l.startswith('}'):
            out.append((cur[0], cur[1], i))
            cur = None
    return out


def process(lines, mach, detect_only):
    stats = collections.Counter()
    sites = []
    new_lines = list(lines)
    for va_hex, s, e in scan_functions(lines):
        va = int(va_hex, 16)
        alias = {}
        allocas = {}
        for i in range(s, e):
            m = ALLOCA_RE.match(lines[i])
            if m:
                allocas[m.group(2)] = i
                continue
            m = BITCAST_RE.match(lines[i])
            if m:
                alias[m.group(1)] = m.group(2)
        narrow = collections.defaultdict(list)   # (slot, v) -> [line idx]
        wide_ir = collections.Counter()
        for i in range(s, e):
            m = STORE_RE.match(lines[i])
            if not m:
                continue
            dst = alias.get(m.group('dst'), m.group('dst'))
            slot = slot_of(dst)
            if slot is None or dst not in allocas:
                continue
            ty, val = m.group('ty'), m.group('val')
            v = 0 if val == 'null' else int(val)
            if ty == 'i64':
                wide_ir[(slot, v)] += 1
            else:
                if ty == 'ptr' and val != 'null':
                    continue
                narrow[(slot, v)].append(i)
        ms = None
        if narrow or True:
            ms = machine_stores(mach, va)
        stats['functions'] += 1
        if ms is None:
            stats['fn_no_pdata'] += 1
            stats['ir_narrow_imm_stores_no_pdata'] += sum(len(x) for x in narrow.values())
            continue
        mq = collections.Counter()   # (slot, v): qword imm store 個数
        mn_ = collections.Counter()  # (slot, v): 8B 未満 imm store 個数
        q8 = collections.Counter()   # slot: 8B store 個数 (即値/reg/RMW 問わず)
        small = collections.Counter()  # slot: 8B 未満 store 個数 (同上)
        for (slot, size, imm), addrs in ms.items():
            if size == 8:
                q8[slot] += len(addrs)
            elif size < 8:
                small[slot] += len(addrs)
            if imm is None:
                continue
            if size == 8:
                mq[(slot, imm)] += len(addrs)
            else:
                mn_[(slot, imm)] += len(addrs)
        stats['machine_qword_imm_stack_stores'] += sum(mq.values())
        stats['machine_qword_imm_stack_stores_zero'] += sum(c for (sl, v), c in mq.items() if v == 0)
        for key, cnt in mq.items():
            stats['machine_qword_matched_ir_i64'] += min(cnt, wide_ir.get(key, 0))
        for key, idxs in sorted(narrow.items()):
            slot, v = key
            n_ir, n_q, n_n = len(idxs), mq.get(key, 0), mn_.get(key, 0)
            stats['ir_narrow_imm_stores'] += n_ir
            if n_q > 0 and n_q == n_ir and n_n == 0 and small[slot] == 0:
                verdict = 'fix'                    # 個数一致 (imm 値まで機械語と 1:1)
            elif q8[slot] > 0 and small[slot] == 0:
                verdict = 'fix_slot'               # 同 slot の機械語 store が全て 8B (個数/値は不一致 or reg 経由)
            elif small[slot] > 0:
                verdict = 'machine_narrow'         # 同 slot に 8B 未満の機械語 store あり = 幅が正しい可能性 (触らない)
            else:
                verdict = 'no_machine_store'       # 機械語側に slot store 無し (別 base / 計算アドレス)
            stats['ir_narrow_' + verdict] += n_ir
            for i in idxs:
                sites.append((va_hex, slot, v, verdict, i + 1, lines[i].strip()))
            if verdict not in ('fix', 'fix_slot'):
                continue
            stats['fixed_stores'] += n_ir
            if detect_only:
                continue
            for i in idxs:
                m = STORE_RE.match(lines[i])
                new_lines[i] = '%sstore i64 %d, ptr %s%s' % (m.group('ind'), v, m.group('dst'), m.group('al') or '')
            name = '%%stack_var_%d' % slot
            ai = allocas[name]
            am = ALLOCA_RE.match(new_lines[ai])
            ty = am.group('ty').strip()
            if SZ32.get(ty, 8) < 8:
                new_lines[ai] = '%s%s = alloca i64, align 8' % (am.group(1), am.group(2))
                stats['alloca_widened'] += 1
    return new_lines, stats, sites


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('inp')
    ap.add_argument('out')
    ap.add_argument('--pe', required=True)
    ap.add_argument('--report')
    ap.add_argument('--sites')
    ap.add_argument('--detect-only', action='store_true')
    a = ap.parse_args()
    lines = open(a.inp, encoding='latin1', newline='').read().split('\n')
    mach = Machine(a.pe)
    new_lines, stats, sites = process(lines, mach, a.detect_only)
    if not a.detect_only:
        open(a.out, 'w', encoding='latin1', newline='').write('\n'.join(new_lines))
    else:
        open(a.out, 'w', encoding='latin1', newline='').write('\n'.join(lines))
    rep = dict(stats)
    rep['detect_only'] = a.detect_only
    if a.report:
        json.dump(rep, open(a.report, 'w'), indent=1, sort_keys=True)
    if a.sites:
        with open(a.sites, 'w') as f:
            f.write('function\tslot\tvalue\tverdict\tir_line\tir_text\n')
            for r in sites:
                f.write('\t'.join(['function_' + r[0]] + [str(x) for x in r[1:]]) + '\n')
    print('[qstore] ' + ' '.join('%s=%d' % (k, v) for k, v in sorted(stats.items())))


if __name__ == '__main__':
    main()
