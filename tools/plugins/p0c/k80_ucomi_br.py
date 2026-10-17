#!/usr/bin/env python3
"""k80_ucomi_br.py — ucomiss/ucomisd の flags が条件分岐に届かない lift を修復する (#3281 残件 B / P0c-32)。

  python3 k80_ucomi_br.py <in.ll> <out.ll> --func function_5e12c0 --cc jbe [--report r.json]

症状 (0x5e12c0):
  機械語  ucomisd xmm0, xmm1 ; jbe L ; (store 0) ; L: ...
  lift IR `call void @__asm_ucomisd(%A, %B)` の戻りは捨てられ、分岐条件は
  reg2mem alloca (%cf.N.reg2mem) の初回 store (arg2==0) と以降の store false の reload になる。
修復:
  ucomi と同じ block の %cf.N.reload の use を、ucomi 直後に置いた flags 式で置き換える。
  jcc ごとの式 (ucomi a,b: CF = a<b または非順序, ZF = a==b または非順序):
    jb → fcmp ult (CF) / jbe → fcmp ule (CF|ZF) / ja → fcmp ogt (!CF&!ZF) / jae → fcmp oge (!CF)
  対象 function と jcc は --func / --cc で opt-in (機械語を確認済みのものだけ)。
  block 内に ucomi が無い・reload の use が分岐以外にある・jcc が未知のときは触らない (fail-closed)。
  再実行は 0 site として fail-closed で止まる (出力を再入力にしても何も書き換えない)。
  1 関数に対象 site が 2 つ以上あるときも止まる (`%ucb.` の名前が衝突するため)。
"""
import argparse
import json
import re

CC = {
    'jb': 'ult',
    'jbe': 'ule',
    'ja': 'ogt',
    'jae': 'oge',
}
RE_UCOMI = re.compile(r'call void @__asm_(ucomis[sd])\(i128 (%[\w.$-]+), i128 (%[\w.$-]+)\)')
RE_BR = re.compile(r'^\s*br i1 (%cf\.\d+\.reload),')


def fix_block(blk, cc, rep):
    if any('%ucb.' in l for l in blk):
        return blk
    ucs = [k for k, l in enumerate(blk) if RE_UCOMI.search(l)]
    if not ucs:
        return blk
    k_u = ucs[0]
    m = RE_UCOMI.search(blk[k_u])
    mn, a, b = m.group(1), m.group(2), m.group(3)
    br = [k for k in range(k_u + 1, len(blk)) if RE_BR.match(blk[k])]
    if len(br) != 1:
        return blk
    name = RE_BR.match(blk[br[0]]).group(1)
    if not name.endswith('.reload'):
        return blk
    uses = [k for k, l in enumerate(blk)
            if re.search(re.escape(name) + r'(?![\w.$-])', l) and not re.match(r'^\s*' + re.escape(name) + r' = ', l)]
    if uses != [br[0]]:
        return blk
    ity, fty = ('i32', 'float') if mn.endswith('ss') else ('i64', 'double')
    pred = CC[cc]
    tag = 'ucb'
    new = ['  %%%s.a = trunc i128 %s to %s' % (tag, a, ity),
           '  %%%s.af = bitcast %s %%%s.a to %s' % (tag, ity, tag, fty),
           '  %%%s.b = trunc i128 %s to %s' % (tag, b, ity),
           '  %%%s.bf = bitcast %s %%%s.b to %s' % (tag, ity, tag, fty),
           '  %%%s.c = fcmp %s %s %%%s.af, %%%s.bf' % (tag, pred, fty, tag, tag)]
    blk[br[0]] = RE_BR.sub('  br i1 %%%s.c,' % tag, blk[br[0]], count=1)
    blk[k_u + 1:k_u + 1] = new
    rep['sites'] += 1
    return blk


def fix_func(body, cc, rep):
    lines = body.split('\n')
    blocks, cur = [], []
    for ln in lines:
        if re.match(r'^[\w.$-]+:\s*(;.*)?$', ln) and cur:
            blocks.append(cur)
            cur = []
        cur.append(ln)
    blocks.append(cur)
    out = []
    for blk in blocks:
        out.extend(fix_block(blk, cc, rep))
    return '\n'.join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--func', action='append', default=[], help='例: function_5e12c0 (複数可)')
    ap.add_argument('--cc', required=True, choices=sorted(CC), help='機械語の jcc (ucomi の直後の分岐)')
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
            rest = fix_func(rest, a.cc, rep)
            rep['funcs'][fname] = rep['sites'] - before
            if rep['funcs'][fname] != 1:
                raise SystemExit('[k80_ucomi_br] %s: 対象 site が %d 件 (1 件のみ可・fail-closed)' % (fname, rep['funcs'][fname]))
        parts.append(header + rest)
    missing = sorted(set(a.func) - set(rep['funcs']))
    if missing:
        raise SystemExit('[k80_ucomi_br] function が無い: %s' % ' '.join(missing))
    open(a.dst, 'w').write(''.join(parts))
    if a.report:
        json.dump(rep, open(a.report, 'w'), indent=1)
    print('[k80_ucomi_br]', json.dumps(rep))


if __name__ == '__main__':
    main()
