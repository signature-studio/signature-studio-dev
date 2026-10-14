#!/usr/bin/env python3
"""emcc ログ (build_cmp.sh が書く <outdir>/emcc.log) の clang error を排他的に分類して件数を出す。

  python3 tools/targets/kilohearts/ghidra_route/emcc_census.py <emcc.log>

分類は下の RULES を上から順に当てる (先頭一致。1 error 行は必ず 1 分類に入るので、分類の合計 = error 行数)。
出力は TSV (分類 TAB 件数) と合計行。
"""
import re
import sys

ERR = re.compile(r'^[^\s:]+:\d+:\d+: error: (.*)$')
RULES = [
    ('未関数化 callee (未宣言の FUN_/func_ 呼出)', r"call to undeclared function '(FUN_|func_)|implicit declaration of function '(FUN_|func_)"),
    ('128bit レーン型 (V128 / undefined1[16])', r'V128|undefined1 \[16\]'),
    ('引数数不一致 (引数なし呼出を含む)', r'too (few|many) arguments|no matching function'),
    ('未宣言の SIMD 疑似関数', r"undeclared identifier '(rsqrtps|rcpps|maxps|minps|vpsrldq\w*|ZEXT\d+|SUB\d+|ABS)'"),
    ('未宣言の Win API・LOCK/UNLOCK・MXCSR', r"undeclared identifier '(Heap\w+|Get\w+|Set\w+|IsProcessorFeaturePresent|TerminateProcess|LOCK|UNLOCK|MXCSR)'"),
    ('演算・代入の型不一致', r'invalid operands|incompatible|assigning to|initializing|non-void|cannot (assign|convert)'),
    ('未宣言の型・識別子 (その他)', r"unknown type name|undeclared identifier"),
]


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    errs = [m.group(1) for m in (ERR.match(l) for l in open(sys.argv[1], encoding='utf-8', errors='replace')) if m]
    counts = {name: 0 for name, _ in RULES}
    counts['その他 (上記に当たらない)'] = 0
    for msg in errs:
        for name, rx in RULES:
            if re.search(rx, msg):
                counts[name] += 1
                break
        else:
            counts['その他 (上記に当たらない)'] += 1
    for name, n in counts.items():
        print('%s\t%d' % (name, n))
    print('合計\t%d' % len(errs))
    return 0


if __name__ == '__main__':
    sys.exit(main())
