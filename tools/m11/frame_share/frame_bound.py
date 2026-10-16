#!/usr/bin/env python3
"""次の stack_var が無い組の親の枠内の空きを、機械語の prologue から測る (#5690 / SHX-T58)。

局所領域は [X, -8*push数)。X = rbp の entry 基準位置 = -(8*push数 + sub 量)、
-8*push数 から上は退避レジスタ域。枠内の空き avail = -8*push数 - X。
判定: E > avail なら枠超過。E <= avail でも、親が rbp+[0, E) または rsp+[0, E) の範囲を
自分の値に使っていれば衝突 (rsp は本体で rsp == rbp の区間だけを見る)。
両方を満たさないときだけ alloca 拡幅の候補とする。

使い方 (repo 直下。FL_WIN64_DIR は展開先):
  FL_WIN64_DIR=<展開先> python3 tools/m11/frame_share/frame_bound.py --report tools/m11/REPORT_SHX-T48.md
  --ir <IR> を付けると、親の alloca 集合に次の stack_var が無い組だけを測る (T51 §3 の 5 組)。
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
M11 = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(M11, 'ldfix'))
sys.path.insert(0, HERE)
from ldmach import Machine  # noqa: E402
import base_check  # noqa: E402


def parse_gap_rows(report):
    rows = []
    for line in open(report, encoding='utf-8'):
        m = re.match(r'\| `(function_[0-9a-f]+)` \| `(function_[0-9a-f]+)` \| \d+ \| `stack_var_(-?\d+)` \| -?\d+ \| \d+ \| (\d+) \|', line)
        if m:
            rows.append((m.group(1), m.group(2), int(m.group(3)), int(m.group(4))))
    return rows


def fn_lines(lines, name):
    start = None
    for i, line in enumerate(lines):
        if start is None:
            if re.match(r'define [^@]*@%s\(' % name, line):
                start = i
        elif line.startswith('}'):
            return lines[start:i]
    return []


def push_count_and_sub(mach, va):
    pushes = 0
    sub = 0
    for ins in mach.disasm_fn(va):
        if ins.mnemonic == 'push':
            pushes += 1
        elif ins.mnemonic == 'sub' and ins.op_str.startswith('rsp, '):
            sub += int(ins.op_str.split(', ')[1], 0)
        elif ins.mnemonic == 'mov' and ins.op_str == 'rbp, rsp':
            return pushes, sub
    return None


def parent_refs(mach, va):
    """本体 (mov rbp, rsp の後、rsp を書き換える命令・ret・leave の前) の [rbp+d] / [rsp+d] の d の集合。"""
    rbp_refs, rsp_refs = set(), set()
    in_body = False
    for ins in mach.disasm_fn(va):
        if not in_body:
            if ins.mnemonic == 'mov' and ins.op_str == 'rbp, rsp':
                in_body = True
            continue
        if ins.mnemonic in ('ret', 'leave') or ins.op_str.startswith('rsp,'):
            break
        for m in re.finditer(r'\[rbp \+ (0x[0-9a-f]+)\]', ins.op_str):
            rbp_refs.add(int(m.group(1), 16))
        for m in re.finditer(r'\[rsp \+ (0x[0-9a-f]+)\]', ins.op_str):
            rsp_refs.add(int(m.group(1), 16))
    return sorted(rbp_refs), sorted(rsp_refs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ir')
    ap.add_argument('--report', required=True)
    ap.add_argument('--pe', default=os.path.join(os.environ.get('FL_WIN64_DIR', ''), 'extracted', 'block00031_PE.bin'))
    a = ap.parse_args()
    mach = Machine(a.pe)
    lines = open(a.ir, errors='replace').read().split('\n') if a.ir else None
    seen = set()
    print('| 親 | callee | X | push | sub | 枠内の空き | E | rbp 衝突 [0,E) | rsp 衝突 [0,E) | 判定 |')
    print('|---|---|---|---|---|---|---|---|---|---|')
    for parent, callee, X, E in parse_gap_rows(a.report):
        if lines is not None:
            # IR 指定時は、親の alloca に次の stack_var が無い組だけを測る。同じ親は 1 回だけ
            if parent in seen:
                continue
            svs = set()
            for line in fn_lines(lines, parent):
                for m in re.finditer(r'%stack_var_(-?\d+) = alloca', line):
                    svs.add(int(m.group(1)))
            if [s for s in svs if s > X]:
                continue
            seen.add(parent)
        va = int(parent.split('_')[1], 16)
        pushes, sub = push_count_and_sub(mach, va)
        X_p = base_check.rbp_entry_offset(mach, va)
        avail = -8 * pushes - X_p
        rbp_refs, rsp_refs = parent_refs(mach, va)
        in_rbp = [r for r in rbp_refs if 0 <= r < E]
        in_rsp = [r for r in rsp_refs if 0 <= r < E]
        if E > avail:
            verdict = 'R8 不可 (枠超過: callee が親の保存域・戻り番地まで触る)'
        elif in_rbp or in_rsp:
            verdict = 'R8 不可 (枠内だが親の参照と衝突)'
        else:
            verdict = 'R8 候補 (枠内・衝突なし)'
        print('| `%s` | `%s` | %d | %d | %d | %d | %d | %s | %s | %s |' % (
            parent, callee, X_p, pushes, sub, avail, E,
            [hex(r) for r in in_rbp], [hex(r) for r in in_rsp], verdict))


if __name__ == '__main__':
    main()
