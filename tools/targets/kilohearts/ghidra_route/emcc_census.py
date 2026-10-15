#!/usr/bin/env python3
"""emcc ログの clang error を排他的に分類して件数を出す。

  emcc -c -ferror-limit=0 -I ghidra_route <gr>/<name>/<name>.c -o <o> 2> <emcc.log>
  python3 tools/targets/kilohearts/ghidra_route/emcc_census.py <emcc.log>

<emcc.log> は `-ferror-limit=0` で得た stderr を使う (build_cmp.sh の emcc は既定の 20 件で打ち切るため件数が合わない)。
分類は下の RULES を上から順に先頭一致で当てる (1 error 行は必ず 1 分類に入るので、分類の合計 = error 行数)。
出力は TSV (分類 TAB 件数) と合計行。
"""
import re
import sys

ERR = re.compile(r'^[^\s:]+:\d+:\d+: error: (.*)$')
UNDECL = r"(undeclared identifier|call to undeclared function) '"
RULES = [
    ('未関数化 callee (未宣言の FUN_/func_ 呼出)', r"call to undeclared function '(FUN_|func_)|implicit declaration of function '(FUN_|func_)"),
    ('128bit レーン型 (V128・undefined1[N]・メンバ参照)', r'V128|undefined1 ?\[\d+\]|member reference base type'),
    ('引数数不一致 (引数なし呼出を含む)', r'too (few|many) arguments|no matching function'),
    ('未宣言の SIMD・AVX・swi 疑似関数', UNDECL + r"(rsqrtps|rcpps|maxps|minps|ZEXT\d+|SUB\d+|ABS|swi|v[a-z0-9]+_avx)'"),
    ('未宣言の Win API・LOCK/UNLOCK・MXCSR', UNDECL + r"(Heap\w+|Get\w+|Set\w+|IsProcessorFeaturePresent|TerminateProcess|LOCK|UNLOCK|MXCSR)'"),
    ('code 型の間接呼出し (called object type)', r'called object type'),
    ('未定義 identifier (DAT_・uRam・LAB_・PTR__)', r"undeclared identifier '(DAT_|uRam|LAB_|PTR__)"),
    ('演算・代入・ポインタの型不一致', r'invalid operands|incompatible|assigning to|initializing|non-void|cannot (assign|convert)|indirection requires|operand of type|cannot be cast to a pointer|is not assignable|passing .* to parameter of incompatible'),
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
