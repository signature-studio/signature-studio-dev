#!/usr/bin/env python3
# #5506 (KH-167): classify_ulonglong.py の CAST 行 (p-code CAST の変数トークン) について、
# Ghidra が付けた機械語 (tokens.tsv の insn) を objdump の同アドレス命令と 1 件ずつ突き合わせる。
#   入力: tokens.tsv (MapLines.java の出力)・HeartCore.core_64 (repo 外)
#   出力: 98 行の範囲の CAST 件ごとの一致 (stdout の TSV。OK=命令・オペランドが一致 / NG=不一致 / NA=objdump 側に該当アドレス無し)
#   使い方: python3 check_cast_objdump.py <tokens.tsv> <HeartCore.core_64> <decomp_dir>
import re
import subprocess
import sys

FUNCS = ['180fc4590', '180fcce40', '180fcd690', '180fce0d0', '180fc6d70', '180fc6870', '180fcd400', '1802ed7f0']
LINE = re.compile(r'^\s*([0-9a-f]+):\s+(.*)$')
CAST_C = re.compile(r'\(ulonglong\)dVar\d+')


def objdump_map(core, va):
    out = subprocess.run(['objdump', '-d', '-M', 'intel', '--no-show-raw-insn',
                          f'--start-address=0x{va}', f'--stop-address=0x{int(va, 16) + 0x3000:x}', core],
                         capture_output=True, text=True).stdout
    m = {}
    for ln in out.splitlines():
        g = LINE.match(ln)
        if g:
            m[int(g.group(1), 16)] = re.sub(r'\s+', ' ', g.group(2)).strip()
    return m


def norm(s):
    s = s.lower()
    s = re.sub(r'\[rip\+0x[0-9a-f]+\]\s*#\s*(0x[0-9a-f]+)', r'[\1]', s)
    s = re.sub(r'\b(ptr|qword|dword|word|byte|xmmword|tbyte)\b', '', s)
    return re.sub(r'\s+', '', s)


def in_scope(decomp, fn, line):
    src = open(f'{decomp}/{fn}.c').read().splitlines()
    return 0 < line <= len(src) and CAST_C.search(src[line - 1]) is not None


def main():
    tsv, core, decomp = sys.argv[1], sys.argv[2], sys.argv[3]
    maps = {fn: objdump_map(core, fn) for fn in FUNCS}
    rows = [ln.split('\t') for ln in open(tsv).read().splitlines()[1:]]
    ok = ng = na = 0
    print('func\tline\ttoken\ttoken_va\tghidra\tobjdump\tmatch')
    for f in rows:
        if len(f) < 6 or f[3] != 'CAST' or 'dVar' not in f[2]:
            continue
        fn = f[0].replace('FUN_', '')
        if fn not in maps or not f[1].isdigit() or not in_scope(decomp, fn, int(f[1])):
            continue
        od = maps[fn].get(int(f[4], 16), '-')
        g = f[5].strip()
        if od == '-':
            na += 1
            match = 'NA'
        else:
            match = 'OK' if norm(g) == norm(od) else 'NG'
            ok += match == 'OK'
            ng += match == 'NG'
        print(f'{fn}\t{f[1]}\t{f[2]}\t{f[4]}\t{g}\t{od}\t{match}')
    print(f'# CAST (98 行の範囲): ok={ok} ng={ng} na={na}', file=sys.stderr)


if __name__ == '__main__':
    main()
