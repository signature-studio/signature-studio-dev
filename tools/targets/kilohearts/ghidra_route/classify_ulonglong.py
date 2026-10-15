#!/usr/bin/env python3
# #5077 (KH-138): Delay の decompile C の `(ulonglong)dVarN` 行を、機械語で「ビット再解釈」か「数値変換」かに分類する。
#   入力: MapLines.java の出力 tokens.tsv (C 行 → 変数トークン → p-code → 機械語)・decompile 出力ディレクトリ (<va>.c)
#   出力: 行ごとの Markdown 表 (stdout)
#   使い方: python3 classify_ulonglong.py <tokens.tsv> <decomp_dir>
import collections
import re
import sys

FUNCS = ['180fc4590', '180fcce40', '180fcd690', '180fce0d0', '180fc6d70', '180fc6870', '180fcd400', '1802ed7f0']
BIT = re.compile(r'^(AND|OR|XOR|CMP|TEST|SHR|SHL|SAR|PAND|POR|PXOR|PSRLQ|PSLL|ANDPD|ANDNPD|ORPD|XORPD|VAND|VOR|VXOR|VANDN|MOVDDUP|MOVQ|MOVD)')
CTRL = re.compile(r'^(J[A-Z]+|CALL)')
CAST = re.compile(r'\(ulonglong\)dVar\d+')


def kind_of(insn):
    # 制御命令 (Jcc・CALL) は判定の根拠にしない。残りの全命令がビット/論理系なら「ビット再解釈」、
    # 1 つでも数値演算 (CVT*・*SD・*PD の算術・VFMADD*・UCOMISD 等) があれば、または残りが無ければ「要確認」。
    ops = [x.split()[0] for x in insn if x and not CTRL.match(x.split()[0])]
    return 'ビット再解釈' if ops and all(BIT.match(o) for o in ops) else '要確認'


def main():
    tsv, decomp = sys.argv[1], sys.argv[2]
    tok = collections.defaultdict(list)
    for line in open(tsv).read().splitlines()[1:]:
        f = line.split('\t')
        if len(f) >= 6:
            tok[(f[0], int(f[1]))].append((f[2], f[5]))
    print('| 関数 | C 行 | C の式 (抜粋) | 対応する機械語 | 分類 |')
    print('|---|---|---|---|---|')
    n = 0
    for fn in FUNCS:
        src = open(f'{decomp}/{fn}.c').read().splitlines()
        for i, s in enumerate(src, 1):
            if not CAST.search(s):
                continue
            n += 1
            insn = sorted(set(x[1].strip() for x in tok.get(('FUN_' + fn, i), []) if 'dVar' in x[0]))
            kind = 'ビット再解釈' if any(BIT.match(x.split()[0]) for x in insn if x) else '要確認'
            code = s.strip()[:120].replace('|', '\\|')
            print(f"| {fn} | {i} | `{code}` | {', '.join(insn).replace('|', chr(92) + '|')} | {kind} |")
    print(f'<!-- rows={n} -->', file=sys.stderr)


if __name__ == '__main__':
    main()
