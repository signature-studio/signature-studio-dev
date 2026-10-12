#!/usr/bin/env python3
"""LD-7 (#307): m11 wasm_trap/unreachable 218 件の native/wasm trace 分岐点を独立に再計算する。

各関数の最初の unreachable case について trace_head (関数入口 VA 列) を native/wasm で比較し、
先頭から最初に食い違う位置の直前の関数 L (= 最後の共通 entry) を求める。L の機械語 (PE) に
メモリ間接 call (`call qword ptr [reg+disp]`、rip 相対 = IAT 経由は除く) があるか、
lift 後 IR (boot_final3.ll) の L に対応する call 数が機械語の直接 call 数以下かを調べる。

  python3 tests/trace_diverge_unreachable.py [--pe PE.bin] [batch.jsonl] [boot_final3.ll] > results/m11_unreachable_diverge.md

--pe 省略時は $LD_M11_PE、無ければ targets/m11.json の pe。
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


def mach(va):
    """関数 va の機械語を ret/int3 (最初の無条件終端) まで線形に読み、(直接 call 先集合, メモリ間接 call 数) を返す。
    分岐先の先読みはしない近似だが、対象は短い Delphi RTL 関数のみ。"""
    data = pe.read(va - pe.base, 0x600)
    direct, mem_ind, reg_ind = set(), 0, 0
    for i in md.disasm(data, va):
        if i.id == X.X86_INS_CALL:
            op = i.operands[0]
            if op.type == X.X86_OP_IMM:
                direct.add(op.imm)
            elif op.type == X.X86_OP_MEM:
                if op.mem.base == X.X86_REG_RIP:
                    pass
                else:
                    mem_ind += 1
            else:
                reg_ind += 1
        if i.id in (X.X86_INS_RET, X.X86_INS_INT3):
            break
    return direct, mem_ind, reg_ind


def ir_calls(ir_text_by_fn, va):
    body = ir_text_by_fn.get('function_%x' % va)
    if body is None:
        return None
    return len(re.findall(r'\bcall\b', body))


def load_ir(path, want):
    out = {}
    cur, buf = None, []
    pat = re.compile(r'^define .*@(function_[0-9a-f]+)\(')
    for line in open(path):
        if cur is None:
            m = pat.match(line)
            if m and m.group(1) in want:
                cur, buf = m.group(1), [line]
        else:
            buf.append(line)
            if line.startswith('}'):
                out[cur] = ''.join(buf)
                cur = None
    return out


def main():
    rows = [json.loads(l) for l in open(A.batch)]
    un = []
    for r in rows:
        cs = [c for c in r['cases'] if c['outcome'] == 'wasm_trap']
        if cs and (cs[0].get('wasm_detail') or '').startswith('unreachable') and cs[0].get('wasm_status') != 'badjson':
            un.append((r, cs[0]))
    div = collections.Counter()
    ex = {}
    for r, c in un:
        N = [int(t[0], 16) for t in c['raw']['native']['trace_head']]
        W = [int(t[0], 16) for t in c['raw']['wasm']['trace_head']]
        i = 0
        while i < len(N) and i < len(W) and N[i] == W[i]:
            i += 1
        L = N[i - 1] if i else None
        nn = N[i] if i < len(N) else None
        ww = W[i] if i < len(W) else None
        div[(L, nn, ww)] += 1
        ex.setdefault((L, nn, ww), r['function']['va'])
    last = collections.Counter()
    for (L, nn, ww), n in div.items():
        last[L] += n
    irs = load_ir(A.ir, {'function_%x' % L for L in last if L})

    w = print
    w('<!-- 自動生成: python3 tools/liftdiff/tests/trace_diverge_unreachable.py (LD-7, #307) -->')
    w('# m11 unreachable の native/wasm trace 分岐点 (LD-7, #307)')
    w('')
    w('対象 = 最初の wasm_trap case が unreachable の関数 **%d** (batch jsonl %d 行)。' % (len(un), len(rows)))
    w('trace_head (関数入口 VA 列、最大 12 件) を native/wasm で先頭から比較し、最初に食い違う直前の関数 L を求める。')
    w('')
    w('## 1. 最後の共通 entry L ごとの件数')
    w('')
    w('| L | 件数 | L の直接 call 数 | L のメモリ間接 call (非 rip) | L のレジスタ間接 call | lift 後 IR の call 数 | 判定 |')
    w('|---|---:|---:|---:|---:|---:|---|')
    drop_total = 0
    for L, n in last.most_common():
        if L is None:
            w('| (先頭から不一致) | %d | | | | | |' % n)
            continue
        d, mi, ri = mach(L)
        ic = ir_calls(irs, L)
        drop = mi > 0 and ic is not None and ic <= len(d)
        if drop:
            drop_total += n
        w('| 0x%x | %d | %d | %d | %d | %s | %s |' % (L, n, len(d), mi, ri, ic if ic is not None else '-',
                                                    '**メモリ間接 call が IR で脱落 (D15 型)**' if drop else ''))
    w('')
    w('メモリ間接 call を持ち IR の call 数が直接 call 数以下 (= 間接 call 脱落) の L に該当する件数: **%d / %d**' % (drop_total, len(un)))
    w('')
    w('## 2. 分岐 (L, native 次, wasm 次) 上位')
    w('')
    w('| L | native 次 | wasm 次 | 件数 | 例 |')
    w('|---|---|---|---:|---|')
    f = lambda v: '-' if v is None else '0x%x' % v
    for (L, nn, ww), n in div.most_common(12):
        w('| %s | %s | %s | %d | %s |' % (f(L), f(nn), f(ww), n, ex[(L, nn, ww)]))


if __name__ == '__main__':
    main()
