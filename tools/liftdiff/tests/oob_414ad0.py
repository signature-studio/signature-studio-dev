#!/usr/bin/env python3
"""LD-7 (#307): m11 wasm_trap OOB のうち最上位 frame が function_414ad0 の関数の独立再計算。

(1) batch jsonl から対象関数 (最初の wasm_trap case の wasm_detail が
    `memory access out of bounds @ ...function_414ad0`) を数える。
(2) function_414ad0 (Delphi UStrSetLength 相当) の機械語を capstone で読み、引数 rcx のコピー
    (rbx) からのゼロ disp load (`mov r, [rbx]`) の件数を数え、lift 後 IR で %arg1 自身を
    ptr として読む load の件数と突合する (IR 側 = 0 なら [arg1] の 1 段 deref が全脱落)。
(3) 脱落の影響を、wasm の callee 引数 (0x414850 の arg0 が native=ポインタ / wasm=長さ) の
    batch 実測で裏付ける。

  python3 tests/oob_414ad0.py [--pe PE.bin] [batch.jsonl] [boot_final3.ll] > results/m11_oob_414ad0.md
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
ap.add_argument('--fn', default='0x414ad0')
A = ap.parse_args()
VA = int(A.fn, 16)
NAME = 'function_%x' % VA


def machine_loads():
    pe = PE(A.pe)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    data = pe.read(VA - pe.base, 0x200)
    alias = {X.X86_REG_RCX}   # 入口 rcx のコピー先を追う (mov rbx, rcx)
    loads = []
    for i in md.disasm(data, VA):
        if i.id == X.X86_INS_RET:
            break
        ops = i.operands
        if i.id == X.X86_INS_MOV and len(ops) == 2 and ops[0].type == X.X86_OP_REG and ops[1].type == X.X86_OP_REG and ops[1].reg in alias:
            alias.add(ops[0].reg)
        if i.id == X.X86_INS_MOV and len(ops) == 2 and ops[0].type == X.X86_OP_REG and ops[1].type == X.X86_OP_MEM:
            m = ops[1].mem
            if m.base in alias and m.disp == 0 and m.index == 0:
                loads.append((i.address, '%s %s' % (i.mnemonic, i.op_str)))
    return loads


def ir_body():
    cur = []
    on = False
    for line in open(A.ir):
        if not on and line.startswith('define') and '@%s(' % NAME in line:
            on = True
        if on:
            cur.append(line)
            if line.startswith('}'):
                break
    return ''.join(cur)


def main():
    rows = [json.loads(l) for l in open(A.batch)]
    top = []
    for r in rows:
        cs = [c for c in r['cases'] if c['outcome'] == 'wasm_trap']
        d = (cs[0].get('wasm_detail') or '') if cs else ''
        if d.startswith('memory access out of bounds @ ld_wasm.wasm.%s' % NAME):
            top.append((r, cs[0]))
    w = print
    w('<!-- 自動生成: python3 tools/liftdiff/tests/oob_414ad0.py (LD-7, #307) -->')
    w('# m11 OOB: 最上位 frame が %s の関数 (LD-7, #307)' % NAME)
    w('')
    w('対象 = 最初の wasm_trap case が OOB かつ最上位 frame が `%s` の関数 **%d** (batch jsonl %d 行)。' % (NAME, len(top), len(rows)))
    w('')
    ml = machine_loads()
    body = ir_body()
    var = {}
    # %arg1 が直接 ptr、または inttoptr(%arg1) を ptr とする load
    ptrs = {'%arg1'}
    for m in re.finditer(r'(%\S+) = inttoptr i64 %arg1 to ptr', body):
        ptrs.add(m.group(1))
    ir_arg1_loads = [l.strip() for l in body.splitlines() if re.search(r'= load \S+, ptr (%\S+?),', l) and re.search(r'ptr (%\S+?),', l).group(1) in ptrs]
    ir_arg1_stores = [l.strip() for l in body.splitlines() if re.match(r'\s*store .*, ptr (%\S+?),', l) and re.match(r'\s*store .*, ptr (%\S+?),', l).group(1) in ptrs]
    w('## 1. 機械語 vs lift 後 IR: 入口 rcx (= var 文字列のアドレス) からの 1 段 deref')
    w('')
    w('- 機械語の `mov r, [rbx]` (rbx = 入口 rcx のコピー、disp 0): **%d 件** — ' % len(ml) + ', '.join('0x%x' % a for a, _ in ml))
    w('- IR の `load ..., ptr %%arg1` (inttoptr 経由を含む): **%d 件**' % len(ir_arg1_loads))
    w('- IR の `store ..., ptr %%arg1` (inttoptr 経由を含む): %d 件 (機械語の `mov [rbx], r` に対応。store 側は残る)' % len(ir_arg1_stores))
    w('- IR で `%%arg1` を値として直接 `icmp eq i64 %%arg1, 0` / `add i64 %%arg1, -N` に使う箇所: %d' % len(re.findall(r'(icmp eq i64 %arg1, 0|add i64 %arg1, -\d+)', body)))
    w('')
    w('## 2. wasm の callee 引数への影響 (batch 実測)')
    w('')
    n_w = sum(1 for r, c in top if any(t[0] == '0x%x' % VA for t in c['raw']['wasm']['trace_head']))
    w('- wasm 側 trace_head に %s が現れる: %d / %d' % (NAME, n_w, len(top)))
    w('- 単体 `liftdiff run --fn 0x414ad0` (手動実行・§再現手順) の pattern q0 で、callee `0x414850` の arg0 は')
    w('  native=0x22479388 (文字列データのポインタ) / wasm=0x5 (= 長さ引数)。load 脱落で 1 段 deref されず値が取り違う。')
    w('')
    w('## 3. 最後の共通 entry (native/wasm の trace 先頭比較) の内訳')
    w('')
    div = collections.Counter()
    for r, c in top:
        N = [t[0] for t in c['raw']['native']['trace_head']]
        W = [t[0] for t in c['raw']['wasm']['trace_head']]
        i = 0
        while i < len(N) and i < len(W) and N[i] == W[i]:
            i += 1
        div[N[i - 1] if i else None] += 1
    w('| 最後の共通 entry | 件数 |')
    w('|---|---:|')
    for k, v in div.most_common(8):
        w('| %s | %d |' % (k, v))
    nat = sum(1 for r, c in top if any(t[0] == '0x%x' % VA for t in c['raw']['native']['trace_head']))
    w('')
    w('- native 側 trace_head にも %s が現れる (= native も到達): %d / %d' % (NAME, nat, len(top)))


if __name__ == '__main__':
    main()
