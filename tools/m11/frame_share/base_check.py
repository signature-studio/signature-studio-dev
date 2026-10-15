#!/usr/bin/env python3
"""base_check.py: D23 信号 site (301) を、機械語の prologue から求めた親 rbp の位置と、親 IR が callee へ渡す alloca の位置で突合する (#4189 / SHX-T44)。

前提 (IR の名前の意味): RetDec の stack_var_-N は entry rsp 基準 (戻り番地の位置を 0・ `[rbp+0x70]` = +8 = 第 1 引数の home) と扱う。
機械語: 親の prologue (push・sub rsp,imm・mov rbp,rsp) から rbp の entry 基準位置 X = -(8*push 数 + sub 量) を求める。
判定 (site 単位・mov 渡しのみ):
  - 親 IR の call の第 1 引数 alloca 名が stack_var_X (= rbp と同じ位置) なら base 一致 (機械語で rbp の番地と IR の alloca が同じ)。
    - 一致 かつ callee の rbp 基準の最大端 E > alloca 幅 S → 'ir_truncated' (機械語の位置が一致し、IR が callee の触る範囲を切っている)。
    - 一致 かつ E <= S → 'ir_covers'。
  - 不一致 (alloca 名が X と違う・stack_var でない) → 'base_mismatch' (IR は別の番地を渡している。D23 かどうかは alloca 幅では決まらない)。
  - 親 IR に該当 call が無い → 'unmatched'。
  - prologue が取れない → 'no_prologue'。
使い方:
  FL_WIN64_DIR=<展開先> python3 frame_share/base_check.py --ir work/boot_final3.ll --sites work/frame_share.json [--out work/base_check.json]
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
sys.path.insert(0, HERE)
from ldmach import Machine  # noqa: E402
import classify  # noqa: E402

CALL_ARG_RE = classify.CALL_RE


def rbp_entry_offset(mach, va):
    pushes = 0
    sub = 0
    for ins in mach.disasm_fn(va):
        if ins.mnemonic == 'push':
            pushes += 1
        elif ins.mnemonic == 'sub' and ins.op_str.startswith('rsp, '):
            try:
                sub += int(ins.op_str.split(', ')[1], 0)
            except ValueError:
                return None
        elif ins.mnemonic == 'mov' and ins.op_str == 'rbp, rsp':
            return -(8 * pushes + sub)
        elif ins.op_str.startswith('rsp') or ins.mnemonic in ('call', 'ret'):
            return None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ir', required=True)
    ap.add_argument('--sites', required=True)
    ap.add_argument('--pe', default=os.path.join(os.environ.get('FL_WIN64_DIR', ''), 'extracted', 'block00031_PE.bin'))
    ap.add_argument('--out')
    a = ap.parse_args()
    text = open(a.ir, errors='replace').read()
    fns = classify.bodies(text)
    data = json.load(open(a.sites))
    mov = [s for s in data['sites'] if s['how'] == 'mov' and s['cls'] == 'shared']
    mach = Machine(a.pe)

    cache_sizes = {}
    cache_rbp = {}
    sites_out = []
    for s in mov:
        p = s['parent']
        if p not in cache_rbp:
            cache_rbp[p] = rbp_entry_offset(mach, int(p.split('_')[1], 16))
        X = cache_rbp[p]
        body = fns.get(p)
        E = max(x['off'] + x['size'] for x in s['callee_access'])
        rec = dict(call_at=s['call_at'], parent=p, callee=s['callee'], rbp_entry=X, need=E)
        if body is None:
            rec['verdict'] = 'unmatched'
            sites_out.append(rec)
            continue
        if X is None:
            rec['verdict'] = 'no_prologue'
            sites_out.append(rec)
            continue
        if p not in cache_sizes:
            cache_sizes[p] = classify.alloca_sizes(body)
        sizes = cache_sizes[p]
        args = set(m.group(2) for m in CALL_ARG_RE.finditer(body) if m.group(1) == s['callee'])
        if not args:
            rec['verdict'] = 'unmatched'
            sites_out.append(rec)
            continue
        ok = []
        for n in args:
            if n in sizes and n == 'stack_var_%d' % X:
                ok.append(n)
        if len(ok) == len(args):
            S = sizes[ok[0]]
            rec.update(passed=ok[0], alloca_size=S)
            rec['verdict'] = 'ir_truncated' if E > S else 'ir_covers'
        else:
            rec['verdict'] = 'base_mismatch'
            rec['passed'] = sorted(args)
        sites_out.append(rec)

    cnt = collections.Counter(r['verdict'] for r in sites_out)
    pairs = {}
    for r in sites_out:
        pairs.setdefault((r['parent'], r['callee']), r['verdict'])
    summary = dict(sites=len(sites_out), by_site=dict(cnt),
                   pairs=len(pairs), by_pair=dict(collections.Counter(pairs.values())))
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if a.out:
        json.dump(dict(summary=summary, sites=sites_out), open(a.out, 'w'), ensure_ascii=False, indent=1)
        open(a.out, 'a').write('\n')


if __name__ == '__main__':
    main()
