#!/usr/bin/env python3
"""scan_spill_deref_2502.py — #2502 受入 2: 同類型 (スピルした引数経由の 1 段 deref を call 引数へ渡す形) の機械語候補を数える。

定義 (機械語・capstone 線型 disasm・関数は .pdata 区間):
  S: `mov qword ptr [rsp + X], R` (R ∈ rcx/rdx/r8/r9 = 引数レジスタの退避)
  L: `mov Ra, qword ptr [rsp + X]` (同じ slot を読み直す)
  D: `mov Rb, qword ptr [Ra]` (読み直した値を 1 段 deref)
  C: Rb が引数レジスタ (rcx/rdx/r8/r9) で、D の後 6 命令以内に `call`
  候補 = S→L→D→C が順に現れる関数。1 関数に複数あれば件数は deref 箇所の数。
対象: IR (`define` 行) に存在する function_<VA> のうち .pdata に載る関数 (closure)。
IR 側の判定 (base IR がこの deref を落としているか) は本 script では行わない (未解決として REPORT に記載)。

使い方: python3 scan_spill_deref_2502.py IR.ll --pe PE.bin --out OUT.json
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ldmach import Machine  # noqa: E402

ARG = ('rcx', 'rdx', 'r8', 'r9')
NOWRITE = ('cmp', 'test')
S_RE = re.compile(r'^qword ptr \[rsp \+ (0x[0-9a-f]+)\], (\w+)$')
REG2_RE = re.compile(r'^(\w+), (\w+)$')
SLOT_RE = re.compile(r'^(\w+), qword ptr \[rsp \+ (0x[0-9a-f]+)\]$')
DEREF_RE = re.compile(r'^(\w+), qword ptr \[(\w+)\]$')
DST_RE = re.compile(r'^(\w+), ')
SUB32 = {'eax': 'rax', 'ebx': 'rbx', 'ecx': 'rcx', 'edx': 'rdx', 'esi': 'rsi', 'edi': 'rdi', 'ebp': 'rbp', 'esp': 'rsp'}


def full(r):
    """32bit / r8d 形の部分レジスタを 64bit 名へ寄せる (書込みで alias を正しく消すため)"""
    if r in SUB32:
        return SUB32[r]
    m = re.match(r'^(r\d+)d$', r)
    return m.group(1) if m else r


def scan(ins, copy_alias=False):
    """alias: 引数の値 (ポインタ) を保持するレジスタ → 引数レジスタ / spill: 退避スロット → 引数レジスタ.
    レジスタを書く命令 (mov 以外も含む) は、その宛先の alias を消す (cmp/test は書かない)。
    copy_alias=True は `mov R, argreg` の複写も alias に入れる (正常な間接参照も拾うため既定では無効)"""
    spill, alias, hits = {}, {}, []
    for i, x in enumerate(ins):
        op = x.op_str
        dst = DST_RE.match(op)
        if x.mnemonic != 'mov':
            if dst and x.mnemonic not in NOWRITE:
                alias.pop(full(dst.group(1)), None)
            continue
        m = S_RE.match(op)
        if m and m.group(2) in ARG:
            spill[m.group(1)] = m.group(2)
            continue
        m = REG2_RE.match(op)
        if copy_alias and m and m.group(2) in ARG and m.group(1) not in ARG:
            alias[full(m.group(1))] = m.group(2)
            continue
        m = SLOT_RE.match(op)
        if m and m.group(2) in spill:
            alias[full(m.group(1))] = spill[m.group(2)]
            continue
        m = DEREF_RE.match(op)
        if m and full(m.group(2)) in alias and m.group(1) in ARG:
            for z in ins[i + 1:i + 7]:
                if z.mnemonic == 'call':
                    hits.append({'va': '0x%x' % x.address, 'base': full(m.group(2)), 'arg': alias[full(m.group(2))],
                                 'deref_reg': m.group(1), 'call_va': '0x%x' % z.address})
                    break
            alias.pop(m.group(1), None)
            continue
        if dst:
            alias.pop(full(dst.group(1)), None)
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ir')
    ap.add_argument('--pe', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--copy-alias', action='store_true')
    a = ap.parse_args()
    names = re.findall(r'^define [^\n]*@function_([0-9a-f]+)\(', open(a.ir, errors='replace').read(), re.M)
    m = Machine(a.pe)
    seen = 0
    res = {}
    for nm in names:
        va = int(nm, 16)
        ins = m.disasm_fn(va)
        if ins is None:
            continue
        seen += 1
        h = scan(ins, a.copy_alias)
        if h:
            res['0x%x' % va] = h
    out = {'mode': 'copy_alias' if a.copy_alias else 'spill', 'ir_functions': len(names), 'with_pdata': seen, 'candidates': len(res),
           'deref_sites': sum(len(v) for v in res.values()), 'functions': res}
    json.dump(out, open(a.out, 'w'), indent=1, ensure_ascii=False)
    print('[scan_2502] IR 関数 %d / .pdata 有り %d / 候補関数 %d / deref 箇所 %d' %
          (out['ir_functions'], out['with_pdata'], out['candidates'], out['deref_sites']))


if __name__ == '__main__':
    main()
