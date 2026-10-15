#!/usr/bin/env python3
"""verify_deref_sites_2555.py — #2555 (CI-103): #2502 の走査候補 (scan_spill_deref_2502.py) 16 deref 箇所 + 0x7888f0 の IR 側判定。

判定の対象: 機械語で「スピルした引数 K の指す値 (*argK)」を、呼出し先の引数 p として渡す deref (D→C)。
IR の対応する call 引数 (呼出し先の p 番目) を次の 3 種に分ける:
  ADDR   : `%argK` そのもの (アドレスを値として渡している) → 誤り候補 (機械語は *argK を渡す)
  LOAD   : `%x = load ... ptr %p` の形で、%p が `%argK` 由来の 1 段 load → 正しい候補 (機械語と一致)
  OTHER  : 上のどちらでもない → 判定不能 (人手で REPORT に 1 箇所ずつ書く)
呼出しの対応は、機械語の同じ呼出し先への呼出し順 (k 番目) と IR の呼出し順 (k 番目) で取る。件数が合わなければ MISMATCH。

使い方: python3 verify_deref_sites_2555.py IR.ll --pe PE.bin --out OUT.json [--extra 0x7888f0]
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ldmach import Machine  # noqa: E402
from scan_spill_deref_2502 import scan, ARG  # noqa: E402

CALL_RE = re.compile(r'call [^@]*@function_([0-9a-f]+)\((.*)\)\s*$')
DEF_RE = re.compile(r'^\s*(%[\w.]+) = (.*)$')
ARG_DEF = {'rcx': 'arg1', 'rdx': 'arg2', 'r8': 'arg3', 'r9': 'arg4'}


def fn_bodies(ir_path, want):
    """必要な function_<VA> の定義本文だけを返す (1 関数 1 文字列)"""
    text = open(ir_path, errors='replace').read()
    out = {}
    for m in re.finditer(r'^define [^\n]*@function_([0-9a-f]+)\(.*?\n}\n', text, re.M | re.S):
        if m.group(1) in want:
            out[m.group(1)] = m.group(0)
    return out


def split_args(s):
    """`i64 %arg2, i64 %x` を引数の SSA 名 (または即値) のリストにする"""
    parts = [p.strip() for p in s.split(',') if p.strip()]
    return [p.split()[-1] if p.split() else p for p in parts]


def chain(body, name, depth=3):
    """SSA 名の定義行を depth 段までたどる (ASCII 表示用)"""
    lines = []
    cur = [name]
    for _ in range(depth):
        nxt = []
        for n in cur:
            for ln in body.splitlines():
                m = DEF_RE.match(ln)
                if m and m.group(1) == n:
                    lines.append(ln.strip())
                    nxt += re.findall(r'%[\w.]+', m.group(2))
                    break
        cur = [x for x in nxt if not x.startswith('%arg')]
        if not cur:
            break
    return lines


def judge_site(body, target, k, argpos, argk, ir_calls_same, machine_count):
    if len(ir_calls_same) != machine_count:
        return {'verdict': 'MISMATCH', 'reason': 'IR 呼出し %d 件 / 機械語 %d 件' % (len(ir_calls_same), machine_count)}
    if k >= len(ir_calls_same):
        return {'verdict': 'MISMATCH', 'reason': 'k 番目が無い'}
    m = ir_calls_same[k]
    args = split_args(m.group(2))
    if argpos >= len(args):
        return {'verdict': 'MISMATCH', 'reason': 'IR 引数 %d 個 (p=%d)' % (len(args), argpos)}
    a = args[argpos]
    rec = {'ir_call': m.group(0).strip(), 'ir_arg': a}
    if a == f'%arg{argk}':
        rec.update(verdict='ADDR', reason=f'IR が %arg{argk} (アドレス) を渡す。機械語は *arg{argk} を渡す')
        return rec
    d = chain(body, a)
    rec['def_chain'] = d
    if any(re.search(r'= load i\d+, ptr ', x) for x in d) and any(f'%arg{argk}' in x for x in d):
        rec.update(verdict='LOAD', reason=f'IR の引数が arg{argk} 由来の load')
    else:
        rec.update(verdict='OTHER', reason=f'arg{argk} 由来の load に当たらない (人手で判定)')
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ir')
    ap.add_argument('--pe', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--extra', action='append', default=[])
    a = ap.parse_args()
    m = Machine(a.pe)
    names = re.findall(r'^define [^\n]*@function_([0-9a-f]+)\(', open(a.ir, errors='replace').read(), re.M)
    cand = {}
    for nm in names:
        va = int(nm, 16)
        ins = m.disasm_fn(va)
        if ins is None:
            continue
        h = scan(ins, False)
        if h:
            cand['0x%x' % va] = (ins, h)
    for ex in a.extra:
        va = int(ex, 16)
        ins = m.disasm_fn(va)
        cand['0x%x' % va] = (ins, [])
    want = set(x[2:] for x in cand)
    bodies = fn_bodies(a.ir, want)
    rows = []
    for fva, (ins, hits) in sorted(cand.items()):
        body = bodies.get(fva[2:])
        if body is None:
            rows.append({'fn': fva, 'verdict': 'NO_IR'})
            continue
        if not hits:
            rows.append({'fn': fva, 'verdict': 'SCAN_MISS', 'note': '走査の取りこぼし (手で確認)'})
            continue
        for h in hits:
            call_ins = [x for x in ins if '0x%x' % x.address == h['call_va']][0]
            tgt = call_ins.op_str if call_ins.op_str.startswith('0x') else None
            cva = int(h['call_va'], 16)
            # 呼出し先への呼出し順 (機械語・同一関数内)
            calls_m = [x for x in ins if x.mnemonic == 'call' and x.op_str == tgt]
            k = [i for i, x in enumerate(calls_m) if x.address == cva][0]
            argk = ARG.index(h['arg']) + 1
            argpos = ARG.index(h['deref_reg'])
            same = [mm for mm in re.finditer(r'^\s*(?:%[\w.]+ = )?call [^\n]*@function_([0-9a-f]+)\((.*)\)\s*$', body, re.M)
                    if mm.group(1) == tgt[2:]]
            j = judge_site(body, tgt, k, argpos, argk, same, len(calls_m))
            rows.append(dict(fn=fva, deref_va=h['va'], call_va=h['call_va'], callee=tgt, arg_spilled=h['arg'],
                             deref_reg=h['deref_reg'], argpos=argpos + 1, k=k + 1, **j))
    json.dump(rows, open(a.out, 'w'), indent=1, ensure_ascii=False)
    from collections import Counter
    print('[verify_2555] 候補 %d 行: %s' % (len(rows), dict(Counter(r['verdict'] for r in rows))))


if __name__ == '__main__':
    main()
