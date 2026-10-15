#!/usr/bin/env python3
"""judge_copy_3382.py — #3382 (CI-153): scan_spill_deref_3328.py の COPY 候補 (複写経由・直接呼出し) の IR 側一次判定。

入力: scan_spill_deref_3328.py の出力 JSON (--scan) と IR・PE。
各 COPY 箇所 (関数 VA・deref VA・call VA) について、機械語の同じ呼出し先への k 番目の呼出しの引数 argpos を、
IR の同じ呼出し先への k 番目の呼出しの引数と突き合わせる (verify_deref_sites_2555.judge_site を流用)。
  ADDR  : IR が %argK (アドレス) を渡す。機械語は *argK を渡す → 誤り候補
  LOAD  : IR の引数が argK 由来の load → 正常な参照候補
  OTHER : どちらでもない → 判定不能 (人手で窓を読む対象)
  MISMATCH : 機械語と IR の呼出し件数が合わない・k 番目が無い → 判定不能

使い方: python3 judge_copy_3382.py IR.ll --pe PE.bin --scan SCAN.json --out OUT.json
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ldmach import Machine  # noqa: E402
from scan_spill_deref_2502 import ARG  # noqa: E402
from verify_deref_sites_2555 import fn_bodies, split_args, DEF_RE  # noqa: E402

BARE_ARG = re.compile(r'^%arg\d+$')


def judge(body, k, argpos, argk, same, machine_count):
    """COPY 1 箇所の判定。機械語は *argK を argpos 番目へ渡す。
    ERR_BARE : IR の引数が %argM (裸の引数) → 機械語の *argK と値が違う (誤り候補)
    ERR_OTHERARG : IR の引数が別の引数 (argM≠argK) 由来の load → 機械語の *argK と違う (誤り候補)
    OK_ARGK : IR の引数が argK 由来の load → 一致候補
    UNCLEAR : それ以外 (定数・別の式) → 人手で窓を読む
    MISMATCH : 呼出し件数が機械語と合わない"""
    if len(same) != machine_count:
        return {'verdict': 'MISMATCH', 'reason': 'IR 呼出し %d 件 / 機械語 %d 件' % (len(same), machine_count)}
    if k >= len(same):
        return {'verdict': 'MISMATCH', 'reason': 'k 番目が無い'}
    line = same[k].group(0).strip()
    args = split_args(same[k].group(2))
    if argpos >= len(args):
        return {'verdict': 'MISMATCH', 'reason': 'IR 引数 %d 個 (p=%d)' % (len(args), argpos)}
    a = args[argpos]
    rec = {'ir_call': line, 'ir_arg': a}
    if BARE_ARG.match(a):
        rec.update(verdict='ERR_BARE', reason='IR が %s を渡す。機械語は *arg%d を渡す' % (a, argk))
        return rec
    d = closure(body, a)
    rec['def_closure_n'] = len(d)
    has_load = any(re.search(r'= load i\d+, ptr ', x) for x in d)
    has_argk = any(re.search(r'%%arg%d\b' % argk, x) for x in d)
    other = sorted(set(re.findall(r'%arg\d+\b', ' '.join(d))) - {f'%arg{argk}'})
    if has_argk and has_load:
        rec.update(verdict='OK_ARGK', reason='IR の引数の定義閉包に arg%d と load' % argk)
    elif not has_argk:
        rec.update(verdict='ERR_CAND', reason='IR の引数の定義閉包に arg%d が無い (他の引数 %s・定数・非 arg 由来)' % (argk, other or '無し'))
    else:
        rec.update(verdict='UNCLEAR', reason='arg%d を含むが load 無し (人手で判定)' % argk)
    return rec


def closure(body, name, limit=40):
    """SSA 名の定義を推移的にたどり、行の集合を返す (引数名で止める)"""
    defs = {}
    for ln in body.splitlines():
        m = DEF_RE.match(ln)
        if m:
            defs.setdefault(m.group(1), ln.strip())
    seen, todo, out = set(), [name], []
    while todo and len(seen) < limit:
        n = todo.pop()
        if n in seen or n.startswith('%arg') or n not in defs:
            continue
        seen.add(n)
        out.append(defs[n])
        todo += re.findall(r'%[\w.]+', defs[n].split('=', 1)[1])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ir')
    ap.add_argument('--pe', required=True)
    ap.add_argument('--scan', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    scan = json.load(open(a.scan))
    copies = scan['functions'].get('COPY', {})
    want = set(f[2:] for f in copies)
    bodies = fn_bodies(a.ir, want)
    m = Machine(a.pe)
    rows = []
    for fva in sorted(copies):
        ins = m.disasm_fn(int(fva, 16))
        body = bodies.get(fva[2:])
        for h in copies[fva]:
            if body is None:
                rows.append(dict(fn=fva, deref_va=h['deref_va'], call_va=h['call_va'], verdict='NO_IR'))
                continue
            cva = int(h['call_va'], 16)
            tgt = h['callee']
            calls_m = [x for x in ins if x.mnemonic == 'call' and x.op_str == tgt]
            k = [i for i, x in enumerate(calls_m) if x.address == cva][0]
            argk = ARG.index(h['arg']) + 1
            argpos = ARG.index(h['deref_reg'])
            same = [mm for mm in re.finditer(r'^\s*(?:%[\w.]+ = )?call [^\n]*@function_([0-9a-f]+)\((.*)\)\s*$', body, re.M)
                    if mm.group(1) == tgt[2:]]
            j = judge(body, k, argpos, argk, same, len(calls_m))
            rows.append(dict(fn=fva, deref_va=h['deref_va'], call_va=h['call_va'], callee=tgt,
                             arg_spilled=h['arg'], deref_reg=h['deref_reg'], argpos=argpos + 1, k=k + 1,
                             base=h['base'], **j))
    json.dump(rows, open(a.out, 'w'), indent=1, ensure_ascii=False)
    print('[judge_copy_3382] 候補 %d 行: %s' % (len(rows), dict(Counter(r['verdict'] for r in rows))))


if __name__ == '__main__':
    main()
