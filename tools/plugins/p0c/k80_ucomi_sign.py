#!/usr/bin/env python3
"""k80_ucomi_sign.py — ucomiss 結果を捨てて符号 (±1) が定数化された lift の修復 (P0c-7 / #310)。

  python3 k80_ucomi_sign.py <in.ll> <out.ll> --func function_5e0d80 [--report r.json]

症状 (0x5e0d80):
  機械語  ucomiss xmm0(=0.0), xmm6 ; jbe L1 ; or r14d,-1 ; jmp L2 ; L1: mov r14d,1 ; L2: ...
          = r14d = (0.0 > src) ? -1 : +1          (jbe は CF|ZF。unordered も +1)
  lift IR `call void @__asm_ucomiss(%A, %B)` の戻りが捨てられ、符号は reg2mem alloca
          (%cf.N.reg2mem) の初回 `select(arg3==0,1,-1)` と以降 `store i64 -1` の定数になる。
修復:
  ucomiss と同じ block の %cf.N.reload の use を、ucomiss 直後に置く
      %ucs.K = select (fcmp ogt float A.lane0, B.lane0), i64 -1, i64 1
  で置き換える (A = ucomiss 第 1 オペランド = 機械語の xmm0 側)。対象 function は --func で
  opt-in (jbe→±1 の機械語を確認済みのものだけ)。冪等 (`%ucs.` 定義があれば再適用しない)。
"""
import argparse
import json
import re


def fix_func(body, rep, fname):
    lines = body.split('\n')
    out = []
    n = 0
    i = 0
    # block 単位に処理
    blocks = []
    cur = []
    for ln in lines:
        if re.match(r'^[\w.$-]+:\s*(;.*)?$', ln) and cur:
            blocks.append(cur)
            cur = []
        cur.append(ln)
    blocks.append(cur)
    for blk in blocks:
        if any('%ucs.' in l for l in blk):
            out.extend(blk)
            continue
        ucs = [k for k, l in enumerate(blk) if re.search(r'call void @__asm_ucomiss\(i128 %[\w.$-]+, i128 %[\w.$-]+\)', l)]
        loads = {}
        for k, l in enumerate(blk):
            m = re.match(r'^\s*(%cf\.\d+\.reload) = load i64, ptr %cf\.\d+\.reg2mem', l)
            if m:
                loads[m.group(1)] = k
        if not ucs or not loads:
            out.extend(blk)
            continue
        k_u = ucs[0]
        m = re.search(r'@__asm_ucomiss\((i128 )(%[\w.$-]+), i128 (%[\w.$-]+)\)', blk[k_u])
        a, b = m.group(2), m.group(3)
        for name, kl in loads.items():
            if kl > k_u:
                continue
            esc = re.escape(name)
            n += 1
            tag = '%%ucs.%d' % n
            new = ['  %%ucs.a%d = trunc i128 %s to i32' % (n, a),
                   '  %%ucs.af%d = bitcast i32 %%ucs.a%d to float' % (n, n),
                   '  %%ucs.b%d = trunc i128 %s to i32' % (n, b),
                   '  %%ucs.bf%d = bitcast i32 %%ucs.b%d to float' % (n, n),
                   '  %%ucs.c%d = fcmp ogt float %%ucs.af%d, %%ucs.bf%d' % (n, n, n),
                   '  %s = select i1 %%ucs.c%d, i64 -1, i64 1' % (tag, n)]
            for k in range(k_u + 1, len(blk)):
                blk[k] = re.sub(esc + r'(?![\w.$-])', tag, blk[k])
            blk[k_u + 1:k_u + 1] = new
            k_u += len(new)
            rep['sites'] += 1
        out.extend(blk)
    return '\n'.join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--func', action='append', default=[], help='例: function_5e0d80 (複数可)')
    ap.add_argument('--report')
    a = ap.parse_args()
    text = open(a.src, errors='replace').read()
    rep = {'sites': 0, 'funcs': {}}
    starts = [m.start() for m in re.finditer(r'(?m)^define [^\n]*\{', text)]
    parts = [text[:starts[0]]] if starts else [text]
    for k, s in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else len(text)
        seg = text[s:e]
        nl = seg.index('\n') + 1
        header, rest = seg[:nl], seg[nl:]
        m = re.search(r'@([\w.$-]+)\(', header)
        fname = m.group(1) if m else ''
        if fname in a.func:
            before = rep['sites']
            rest = fix_func(rest, rep, fname)
            rep['funcs'][fname] = rep['sites'] - before
        parts.append(header + rest)
    open(a.dst, 'w').write(''.join(parts))
    if a.report:
        json.dump(rep, open(a.report, 'w'), indent=1)
    print('[k80_ucomi_sign]', json.dumps(rep))


if __name__ == '__main__':
    main()
