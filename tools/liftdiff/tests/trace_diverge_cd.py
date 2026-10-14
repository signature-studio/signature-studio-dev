#!/usr/bin/env python3
"""LD-28 (#1035): m11 unreachable の型 C・D (LD-17 / #864) の原因候補を機械的に分類する。

trace_diverge_unreachable.py と同じ食い違い (最後の共通 entry L・native/wasm の次 entry) を取り、
原因候補を次の順で割り当てる。call site と IR block は対応づけない (候補であり確定ではない)。

  P1 L 内の直接 call 脱落: L の機械語の直接 call 先のうち IR の L に無いものが、次 entry に一致
  P2 呼出元の直接 call 脱落: L の一つ前の entry F が L を直接 call し (L ∈ direct_calls(F))、F の直接 call 先のうち IR の F に無いものが、次 entry に一致
  P3 未特定: 上記いずれでもない

  python3 tools/liftdiff/tests/trace_diverge_cd.py > tools/liftdiff/results/m11_unreachable_cd.md

入力既定 = tools/liftdiff/work/m11/batch_closure.jsonl・tools/m11/work/boot_final3.ll。PE = $LD_M11_PE または --pe。
"""
import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from ldlib.pe import PE  # noqa: E402
import capstone  # noqa: E402
from capstone import x86_const as X  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('batch', nargs='?', default=os.path.join(ROOT, 'work/m11/batch_closure.jsonl'))
ap.add_argument('ir', nargs='?', default=os.path.join(ROOT, '../m11/work/boot_final3.ll'))
ap.add_argument('--pe', default=os.environ.get('LD_M11_PE') or json.load(open(os.path.join(ROOT, 'targets/m11.json')))['pe'])
A = ap.parse_args()

pe = PE(A.pe)
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
ir_text = open(A.ir).read()
_cache = {}


def direct_calls(va):
    """関数 va を ret/int3 まで線形に読み、直接 call 先の集合を返す (trace_diverge_unreachable.mach と同じ走査)。"""
    if va not in _cache:
        s = set()
        for i in md.disasm(pe.read(va - pe.base, 0x600), va):
            if i.id == X.X86_INS_CALL and i.operands[0].type == X.X86_OP_IMM:
                s.add(i.operands[0].imm)
            if i.id in (X.X86_INS_RET, X.X86_INS_INT3):
                break
        _cache[va] = s
    return _cache[va]


def ir_targets(va):
    m = re.search(r'^define [^\n]*@function_%x\(.*?^}' % va, ir_text, re.S | re.M)
    if m is None:
        return None
    return set(int(x, 16) for x in re.findall(r'@function_([0-9a-f]+)\(', m.group(0)))


def missing(va):
    """機械語の直接 call 先のうち IR の関数 va に無いもの (脱落候補)。IR に関数が無い場合は None。"""
    t = ir_targets(va)
    return None if t is None else direct_calls(va) - t


def mem_indirect(va):
    """関数 va のメモリ間接 call (rip 相対以外) 数。trace_diverge_unreachable.mach と同じ走査。"""
    n = 0
    for i in md.disasm(pe.read(va - pe.base, 0x600), va):
        if i.id == X.X86_INS_CALL and i.operands[0].type == X.X86_OP_MEM and i.operands[0].mem.base != X.X86_REG_RIP:
            n += 1
        if i.id in (X.X86_INS_RET, X.X86_INS_INT3):
            break
    return n


def is_leaf_no_tail(va):
    """#864 型 B: ret まで call 無し・レジスタ/メモリ間接 call 無し・tail jump 無し。"""
    ins = []
    for i in md.disasm(pe.read(va - pe.base, 0x600), va):
        ins.append(i)
        if i.id in (X.X86_INS_RET, X.X86_INS_INT3):
            break
    if any(i.id == X.X86_INS_CALL for i in ins):
        return False
    end = ins[-1].address
    return not any(i.id == X.X86_INS_JMP and i.operands[0].type == X.X86_OP_IMM
                   and not (va <= i.operands[0].imm <= end) for i in ins)


def type_ab(L):
    """#864 の型 A (D15 型候補) または B (leaf) に該当するなら True。C・D の対象から除く。"""
    d = direct_calls(L)
    ic = ir_calls(L)
    if mem_indirect(L) > 0 and ic is not None and ic <= len(d):
        return True
    return is_leaf_no_tail(L)


def ir_calls(va):
    m = re.search(r'^define [^\n]*@function_%x\(.*?^}' % va, ir_text, re.S | re.M)
    return None if m is None else len(re.findall(r'\bcall\b', m.group(0)))


def main():
    rows = [json.loads(l) for l in open(A.batch)]
    un = []
    for r in rows:
        cs = [c for c in r['cases'] if c['outcome'] == 'wasm_trap']
        if cs and (cs[0].get('wasm_detail') or '').startswith('unreachable') and cs[0].get('wasm_status') != 'badjson':
            un.append((r, cs[0]))
    cnt = collections.Counter()
    by_key = collections.defaultdict(collections.Counter)
    ex = {}
    for r, c in un:
        N = [int(t[0], 16) for t in c['raw']['native']['trace_head']]
        W = [int(t[0], 16) for t in c['raw']['wasm']['trace_head']]
        i = 0
        while i < len(N) and i < len(W) and N[i] == W[i]:
            i += 1
        if i == len(N) == len(W) or i == 0:
            continue
        L = N[i - 1]
        if type_ab(L):
            continue
        nn = N[i] if i < len(N) else None
        ww = W[i] if i < len(W) else None
        kind = 'C' if {nn, ww} & direct_calls(L) else 'D'
        F = N[i - 2] if i >= 2 else None
        if nn in (missing(L) or set()):
            cause, site = 'P1 L 内の直接 call 脱落 (native の次 entry が IR に無い)', L
        elif F is not None and L in direct_calls(F) and nn in (missing(F) or set()):
            cause, site = 'P2 呼出元の直接 call 脱落 (native の次 entry が IR の呼出元に無い)', F
        else:
            cause, site = 'P3 未特定 (両側の次 entry とも IR に call あり)', L
        key = (kind, cause)
        cnt[key] += 1
        by_key[key][site] += 1
        ex.setdefault(key, (int(r['function']['va'], 16), L, site))

    n_all = sum(cnt.values())
    f = lambda v: '-' if v is None else '0x%x' % v
    print('<!-- 自動生成: python3 tools/liftdiff/tests/trace_diverge_cd.py > tools/liftdiff/results/m11_unreachable_cd.md (LD-28 / #1035) -->')
    print('# m11 unreachable の型 C・D の原因候補 (LD-28, #1035)')
    print('')
    print('対象 = trace_diverge_unreachable.py の型 C・D (食い違い観測のうち L の直接 call 先に分岐が無いもの・あるもの) %d 件。' % n_all)
    print('原因候補 = 機械語の直接 call 先のうち IR の対応関数に無いもの (脱落候補) が、食い違いの次 entry に一致するかで判定。')
    print('call site と IR block は対応づけていない。P1・P2 は候補であり、確定ではない。')
    print('')
    print('| 型 | 原因候補 | 件数 | 上位 関数 (件数) | 例 (batch 関数 / L / 原因関数) |')
    print('|---|---|---:|---|---|')
    for key in sorted(cnt, key=lambda k: (k[0], -cnt[k])):
        top = ', '.join('%s (%d)' % (f(s), m) for s, m in by_key[key].most_common(3))
        e = ex[key]
        print('| %s | %s | %d | %s | %s / %s / %s |' % (key[0], key[1], cnt[key], top, f(e[0]), f(e[1]), f(e[2])))


if __name__ == '__main__':
    main()
