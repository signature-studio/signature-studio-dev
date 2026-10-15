#!/usr/bin/env python3
"""classify.py: detect.py の D23 信号 site を、IR 側の「渡された alloca の大きさ」で切り分ける (#4123 / SHX-T43)。

入力: detect.py の出力 JSON (--out で作ったもの) と新 IR (boot_final3.ll)。
判定 (site 単位・mov 渡しのみ。rcx = 親の rbp が base):
  - 親 IR の call <callee>(ptr <P>, ...) の第 1 引数 P が alloca のとき、その alloca の大きさ S を取る。
  - callee が base からアクセスする最大端 E = max(off + size) (detect.py の callee_access)。
  - E > S のとき: 親 IR が callee に渡すフレームが callee の触る範囲より小さい = IR がフレームを切っている
    → 'ir_frame_too_small' (真の D23 の機構と整合)。
  - E <= S のとき: 渡す alloca は callee の触る範囲を覆う → 'ir_frame_covers' (通常の rbp 渡しとして説明できる)。
  - 親 IR に該当 call が無い (P が alloca でない・見つからない) → 'unmatched' (未分類)。
同一 (親, callee) の site は同じ判定になる (site ごとの機械語の突合は行わない。その範囲は REPORT に書く)。
使い方:
  python3 tools/m11/frame_share/classify.py --ir work/boot_final3.ll --sites work/frame_share.json [--out work/frame_share_classify.json] [--show function_448490]
"""
import argparse
import collections
import json
import re

ALLOCA_RE = re.compile(r'^\s*%([\w.\-]+) = alloca (?:\[(\d+) x i(\d+)\]|i(\d+))', re.M)
DEF_RE = re.compile(r'^define [^@]*@(function_[0-9a-f]+)\(', re.M)
CALL_RE = re.compile(r'call [^@]*@(function_[0-9a-f]+)\(ptr[^%,]*%([\w.\-]+)')


def alloca_sizes(body):
    out = {}
    for m in ALLOCA_RE.finditer(body):
        name, n, elbits, bits = m.group(1), m.group(2), m.group(3), m.group(4)
        if n is not None:
            out[name] = int(n) * int(elbits) // 8
        else:
            out[name] = int(bits) // 8
    return out


def bodies(text):
    out = {}
    for m in re.finditer(r'^define [^@]*@(function_[0-9a-f]+)\(.*?^}', text, re.M | re.S):
        out[m.group(1)] = m.group(0)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ir', required=True)
    ap.add_argument('--sites', required=True)
    ap.add_argument('--out')
    ap.add_argument('--show', help='この親関数の (callee ごとの判定) を標準出力に表示する')
    a = ap.parse_args()
    text = open(a.ir, errors='replace').read()
    fns = bodies(text)
    data = json.load(open(a.sites))
    mov = [s for s in data['sites'] if s['how'] == 'mov' and s['cls'] == 'shared']

    cache = {}
    verdict = {}
    for s in mov:
        key = (s['parent'], s['callee'])
        if key in verdict:
            continue
        body = fns.get(s['parent'])
        if body is None:
            verdict[key] = ('unmatched', 'parent not in IR')
            continue
        if s['parent'] not in cache:
            cache[s['parent']] = alloca_sizes(body)
        sizes = cache[s['parent']]
        # 親 IR で callee を呼ぶ call の第 1 引数 (alloca 名) を集める
        args = set()
        for m in CALL_RE.finditer(body):
            if m.group(1) == s['callee']:
                args.add(m.group(2))
        need = max(x['off'] + x['size'] for x in s['callee_access'])
        allocas = {n: sizes[n] for n in args if n in sizes}
        if not allocas:
            verdict[key] = ('unmatched', 'no alloca passed as arg0: %s' % sorted(args))
            continue
        small = [n for n, sz in allocas.items() if need > sz]
        if small and len(small) == len(allocas):
            verdict[key] = ('ir_frame_too_small', 'need=%d passed=%s' % (need, sorted(allocas.items())))
        elif not small:
            verdict[key] = ('ir_frame_covers', 'need=%d passed=%s' % (need, sorted(allocas.items())))
        else:
            verdict[key] = ('mixed', 'need=%d passed=%s' % (need, sorted(allocas.items())))

    cnt_site = collections.Counter()
    cnt_pair = collections.Counter()
    for s in mov:
        v = verdict[(s['parent'], s['callee'])][0]
        cnt_site[v] += 1
    for k, v in verdict.items():
        cnt_pair[v[0]] += 1
    res = dict(sites_mov_shared=len(mov), pairs_total=len(verdict),
               sites_by_class=dict(cnt_site), pairs_by_class=dict(cnt_pair),
               pair_detail={'%s->%s' % k: dict(cls=v[0], why=v[1]) for k, v in sorted(verdict.items())})
    print(json.dumps({k: v for k, v in res.items() if k != 'pair_detail'}, ensure_ascii=False, indent=1))
    for k, v in sorted(verdict.items()):
        if a.show and k[0] == a.show:
            print('%s -> %s : %s (%s)' % (k[0], k[1], v[0], v[1]))
    if a.out:
        json.dump(res, open(a.out, 'w'), ensure_ascii=False, indent=1)
        open(a.out, 'a').write('\n')


if __name__ == '__main__':
    main()
