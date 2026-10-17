#!/usr/bin/env python3
"""judge_arg1_5999.py — #5999 (CI-249) 受入 3: 呼出し第 1 引数を照合する判定器。

件数照合 (#5452 系) は引数の値を見ないため、第 1 引数の誤り (#5995 の f5531d) を検出できない。
本判定器は function_f552a0 の各 call について、第 1 引数の値の出所を IR の def-use でたどり、
機械語が要求する値と一致するかを見る。

機械語 (block00031_PE.bin・#5995 のコメント 6228635866): 6 件の call は全て直前の
`mov rcx, qword ptr [rbx]` (rbx = 入口の %arg1) で第 1 引数を読み直す。よって期待値は
「%arg1 が指す先の 8 バイト load (*%arg1)」だけ。

出所の分類 (reg2mem スロットは、store された値の出所の和集合として扱う):
  arg1   : %arg1 そのもの (誤り。機械語は *%arg1 を渡す)
  *arg1  : load i64, ptr (inttoptr %arg1) (期待値)
  const  : 定数
  other:<名> : 上記以外の SSA 値 (例: 境界値 %21)

判定: 各 call の第 1 引数の出所が {*arg1} だけなら OK。call が 6 件でなければ FAIL (fail-closed)。

使い方: python3 judge_arg1_5999.py IN.ll
終了コード: 0 = 全件 OK、1 = 不一致あり、2 = 入力不正
"""
import re
import sys

FN = re.compile(r'^define [^\n]*@function_f552a0\(.*?\n}\n', re.M | re.S)
DEF = re.compile(r'^\s*(%[\w.]+) = (.*)$', re.M)
STORE = re.compile(r'^\s*store i64 ([^\s,]+), ptr (%[\w.]+)\s*$', re.M)
CALL = re.compile(r'^\s*(?:%[\w.]+ = )?call i64 @function_(12df530|12df760)\((.*)\)\s*$', re.M)
ARG0 = re.compile(r'^i64 ([^\s,]+)')
EXPECT_CALLS = 6


def make_resolver(fn):
    defs = {m.group(1): m.group(2) for m in DEF.finditer(fn)}
    stores = {}
    for m in STORE.finditer(fn):
        stores.setdefault(m.group(2), []).append(m.group(1))

    def resolve(val, seen=frozenset()):
        if val == '%arg1':
            return {'arg1'}
        if re.fullmatch(r'-?\d+', val):
            return {'const'}
        if val in seen:
            return set()
        seen = seen | {val}
        d = defs.get(val)
        if d is None:
            return {'other:' + val}
        m = re.match(r'load i64, ptr (%[\w.]+)(?:, align \d+)?$', d)
        if not m:
            return {'other:' + val}
        p = m.group(1)
        if defs.get(p, '') == 'inttoptr i64 %arg1 to ptr':
            return {'*arg1'}
        if p in stores:
            out = set()
            for v in stores[p]:
                out |= resolve(v, seen)
            return out
        return {'other:' + val}

    return resolve


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    src = open(sys.argv[1], errors='replace').read()
    fns = list(FN.finditer(src))
    if len(fns) != 1:
        print('FAIL: function_f552a0 の定義が 1 件でない: %d' % len(fns))
        return 2
    fn = fns[0].group(0)
    resolve = make_resolver(fn)
    calls = list(CALL.finditer(fn))
    if len(calls) != EXPECT_CALLS:
        print('FAIL: call 件数が %d 件でなく %d 件' % (EXPECT_CALLS, len(calls)))
        return 2
    bad = 0
    for i, m in enumerate(calls, 1):
        a = ARG0.match(m.group(2))
        if not a:
            print('call %d: 第 1 引数を読めない' % i)
            bad += 1
            continue
        srcs = resolve(a.group(1))
        ok = srcs == {'*arg1'}
        bad += 0 if ok else 1
        print('call %d (12df%s): 第 1 引数 %s 出所=%s %s' % (
            i, m.group(1)[-3:], a.group(1), sorted(srcs), 'OK' if ok else 'NG'))
    print('judge: calls=%d ok=%d ng=%d' % (len(calls), len(calls) - bad, bad))
    return 0 if bad == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
