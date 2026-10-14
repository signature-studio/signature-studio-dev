#!/usr/bin/env python3
"""対照 Gain の before 160 (gain_before_160.tsv) と x64c の lift 結果の差を内訳に分ける (#850 / KH-19d)。

usage: closure_breakdown.py <HeartCore.core_64> <gain_before_160.tsv> <x64c 出力ディレクトリ>
  x64c 出力の lift_meta.json の functions (VA の hex) を lift 済み関数とみなす。
分類 (TSV の行ごと・PE の命令で判定):
  IAT thunk  : func_rva の先頭が ff 25 (jmp qword ptr [rip+x])
  tail jmp   : call_site_rva の命令が jmp rel で func_rva を指す (親の C 本体に取り込まれる)
  取りこぼし  : 上記以外 (x64c の descend が辿らなかった call 位置)
出力: TSV 行数・lift 済み数・TSV 側の未 lift 数・lift のみの数、内訳の件数、未 lift 行の番地。
"""
import sys, json
from collections import Counter

import pefile
import capstone

corep, tsvp, outdir = sys.argv[1:4]
pe = pefile.PE(corep, fast_load=True)
IMG = pe.OPTIONAL_HEADER.ImageBase
img = pe.get_memory_mapped_image()
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True

rows = []
for line in open(tsvp).read().splitlines()[1:]:
    f = line.split('\t')
    rows.append({'rva': int(f[0], 16), 'size': int(f[1]), 'parent': f[3], 'site': int(f[4], 16) if f[4] else None})
lifted = {int(h, 16) for h in json.load(open(outdir + '/lift_meta.json'))['functions']}
tsv_va = {IMG + r['rva'] for r in rows}
missing = [r for r in rows if IMG + r['rva'] not in lifted]
extra = sorted(lifted - tsv_va)


def classify(r):
    fva = IMG + r['rva']
    if bytes(img[r['rva']:r['rva'] + 2]) == b'\xff\x25':
        return 'IAT thunk'
    if r['site'] is not None:
        ins = next(md.disasm(bytes(img[r['site']:r['site'] + 16]), IMG + r['site']), None)
        if ins and ins.mnemonic == 'jmp' and ins.operands and ins.operands[0].type == capstone.x86.X86_OP_IMM \
                and ins.operands[0].imm == fva:
            return 'tail jmp'
    return '取りこぼし'


cls = [(r, classify(r)) for r in missing]
print('TSV %d 行 / lift 済み %d / TSV 側の未 lift %d / lift のみ %d' % (len(rows), len(lifted), len(missing), len(extra)))
cnt = Counter(c for _, c in cls)
for k in ('tail jmp', 'IAT thunk', '取りこぼし'):
    print('%s %d' % (k, cnt[k]))
for r, c in cls:
    print('  %#x size=%d class=%s parent=%s site=%s' % (r['rva'], r['size'], c, r['parent'] or '-',
          '%#x' % r['site'] if r['site'] is not None else '-'))
