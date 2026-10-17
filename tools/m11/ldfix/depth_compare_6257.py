#!/usr/bin/env python3
"""depth_compare_6257.py — #6257 (M11-N292): IR の 1 段読み (K = 18752024 の `load i32`) の段数を、
同じ基本ブロックの機械語と照合する (サイト単位)。

読みの数え方 (段数 = スロットを含む、値を得るまでのメモリ読みの回数):
  IR   : K の load を 1 とし、その値 (sext/zext/add/inttoptr を透過) を番地にした load ごとに +1。
         サイトの段数 = そのサイトの SSA 値の段数 (同じ IR ブロック内で追う)。
  機械語: `mov r,[rip+X]` (X = VA 0x15E2218) を 1 とし、r を基底にした `mov r',[r+d]` ごとに +1。
         ブロック内で、同じ r への再定義で打ち切る。ブロック = IR の dec_label_pc_<VA> と同じ番地で始まる範囲。

判定 (サイトごと。同じ IR ブロックに対応する機械語ブロックの chain の最大段数 M と、サイトの段数 I):
  EQ        : M == I
  MACH_DEEP : M > I  (機械語の方が深い。中間の deref が IR で落ちた候補 = lift 段)
  IR_DEEP   : M < I  (IR の方が深い。IR の読み誤り候補)
  NOMACH    : 対応する機械語ブロックに K の rip 読みが無い (判定不能)

注: 段数の一致は必要条件。一致しても同じ値とは言えない (幅・オフセットは見ない)。候補の件数であり、確定ではない。

使い方: python3 depth_compare_6257.py IR.ll --pe PE.bin --out OUT.tsv
"""
import argparse
import bisect
import collections
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ldmach import Machine  # noqa: E402

K = 18752024
SLOT_VA = K + 0x400000
SITE_RE = re.compile(r'^\s*%([\w.\-]+) = load i32, ptr inttoptr \(i64 ' + str(K) + r' to ptr\)')
DEF_RE = re.compile(r'^\s*%([\w.\-]+) = (.*)$')
FN_RE = re.compile(r'^define .*? @(function_[0-9a-f]+)\(')
LBL_RE = re.compile(r'^dec_label_pc_([0-9]+):')
PASS_OPS = ('sext', 'zext', 'trunc', 'add', 'sub', 'inttoptr', 'bitcast')
USE_RE = re.compile(r'%([\w.\-]+)')


def ir_functions(path):
    fns = collections.OrderedDict()
    cur = None
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        for ln, line in enumerate(f, 1):
            m = FN_RE.match(line)
            if m:
                cur = m.group(1)
                fns[cur] = []
            if cur is not None:
                fns[cur].append((ln, line.rstrip('\n')))
                if line.startswith('}'):
                    cur = None
    return fns


def ir_blocks(lines):
    """関数の行列 -> [(label_va or None, [(idx, text)])]。ラベル行が無い先頭は None。"""
    blocks = [(None, [])]
    for idx, (_, text) in enumerate(lines):
        m = LBL_RE.match(text)
        if m:
            blocks.append((int(m.group(1)), []))
        blocks[-1][1].append((idx, text))
    return blocks


def ir_chain(block_lines, site_name):
    """site_name の値の段数を、同じブロック内で追う。値 -> 段数 の辞書を返す (site から始めた分)。"""
    depth = {site_name: 1}
    for _, text in block_lines:
        dm = DEF_RE.match(text)
        if not dm:
            continue
        dn, rhs = dm.group(1), dm.group(2)
        srcs = [u for u in USE_RE.findall(rhs) if u in depth]
        if not srcs:
            continue
        if rhs.startswith('load'):
            depth[dn] = max(depth[u] for u in srcs) + 1
        elif rhs.startswith(PASS_OPS):
            depth[dn] = max(depth[u] for u in srcs)
    return depth


def ir_site_depth(block_lines, site_name):
    """スロット load を除いた deref の回数 (REPORT_APPENDIX_6211 §4 と同じ基準)。"""
    d = ir_chain(block_lines, site_name)
    return max(d.values()) - 1


def mach_block_chains(mach, ins_list):
    """機械語ブロック (命令列) 内の、スロット rip 読みごとの chain 段数。"""
    res = []
    for i, it in enumerate(ins_list):
        if it.mnemonic != 'mov' or len(it.operands) != 2:
            continue
        dst, src = it.operands[0], it.operands[1]
        if dst.type != 1 or src.type != 3:
            continue
        if mach.cs.reg_name(src.mem.base) != 'rip':
            continue
        if it.address + it.size + src.mem.disp != SLOT_VA:
            continue
        cur = mach.cs.reg_name(dst.reg)
        depth = 0
        for nxt in ins_list[i + 1:]:
            if nxt.mnemonic.startswith('j') or nxt.mnemonic in ('call', 'ret'):
                break
            ops = nxt.operands
            if nxt.mnemonic == 'mov' and len(ops) == 2 and ops[0].type == 1 and ops[1].type == 3:
                base = ops[1].mem.base
                if base and mach.cs.reg_name(base) == cur:
                    depth += 1
                    cur = mach.cs.reg_name(ops[0].reg)
                    continue
            if ops and ops[0].type == 1 and mach.cs.reg_name(ops[0].reg) == cur:
                break
        res.append((it.address, depth))
    return res


def mach_blocks(mach, fn_va, label_vas):
    """関数の機械語を IR ブロックの番地で区切る。label_va -> 命令列。"""
    ins = mach.disasm_fn(fn_va) or []
    starts = sorted(set(label_vas))
    out = collections.defaultdict(list)
    for it in ins:
        i = bisect.bisect_right(starts, it.address) - 1
        if i >= 0:
            out[starts[i]].append(it)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ir')
    ap.add_argument('--pe', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    mach = Machine(a.pe)
    rows = []
    cls = collections.Counter()
    for fn, lines in ir_functions(a.ir).items():
        if not any(SITE_RE.match(t) for _, t in lines):
            continue
        blocks = ir_blocks(lines)
        fn_va = int(fn.split('_', 1)[1], 16)
        label_vas = [fn_va] + [b for b, _ in blocks if b is not None]
        mb = mach_blocks(mach, fn_va, label_vas)
        for bva, blines in blocks:
            key = fn_va if bva is None else bva
            for idx, text in blines:
                m = SITE_RE.match(text)
                if not m:
                    continue
                name = m.group(1)
                ir_d = ir_site_depth(blines[blines.index((idx, text)):], name)
                if key not in mb:
                    c, mm, chains = 'NOMACH', 0, '-'
                else:
                    chs = mach_block_chains(mach, mb[key])
                    mm = max((d for _, d in chs), default=0)
                    chains = ','.join('%x:%d' % (x, y) for x, y in chs) or '-'
                    if mm == 0:
                        c = 'NOMACH'
                    elif mm == ir_d:
                        c = 'EQ'
                    elif mm > ir_d:
                        c = 'MACH_DEEP'
                    else:
                        c = 'IR_DEEP'
                cls[c] += 1
                rows.append((fn, lines[idx][0], name, '%x' % (bva or 0), ir_d, mm, chains, c))

    with open(a.out, 'w', encoding='utf-8') as f:
        f.write('function\tir_line\tssa\tir_block_va\tir_depth\tmach_max\tmach_chains\tclass\n')
        for r in rows:
            f.write('\t'.join(str(x) for x in r) + '\n')
    print('IR sites: %d' % len(rows))
    for k in ('EQ', 'MACH_DEEP', 'IR_DEEP', 'NOMACH'):
        print('%s: %d' % (k, cls.get(k, 0)))


if __name__ == '__main__':
    main()
