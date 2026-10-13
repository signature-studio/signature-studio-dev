#!/usr/bin/env python3
"""PLG-X (#210) 別算法検算 (f2/xcheck_icall.py の入力パスだけ hostx 用に変更): audit_icall.py (recursive descent) とは独立に、閉包 ranges を capstone の線形 sweep で
逆アセンブルし、間接 call (オペランドが即値でない call) を数える。 rip 相対で disp 先が import でない/ある は区別せず、
IAT 判定は PE の import テーブル (pefile) で行う。
  python3 tools/plugins/hostx/xcheck_icall.py <block> ...   → block ごとの非 IAT 間接 call 数と audit_icall の値の比較
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import FL_WIN64_DIR
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

W = os.path.join(HERE, '..', 'work')
tot = [0, 0]
for b in map(int, sys.argv[1:]):
    pe = pefile.PE(os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % b), fast_load=True)
    pe.parse_data_directories()
    base = pe.OPTIONAL_HEADER.ImageBase
    iat = {i.address for d in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []) for i in d.imports if i.address}
    md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
    n = 0
    for r in open(os.path.join(W, 'closure', 'block%05d.ranges.txt' % b)).read().replace(',', '\n').split():
        lo, hi = (int(x, 16) for x in r.split('-'))
        code = pe.get_data(lo - base, hi - lo + 1)
        for i in md.disasm(code, lo):
            if i.mnemonic != 'call' or i.operands[0].type == X86_OP_IMM:
                continue
            o = i.operands[0]
            if o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP and (i.address + i.size + o.mem.disp) in iat:
                continue
            n += 1
    a = json.load(open(os.path.join(W, 'hostx', 'icall', '%d.icall.json' % b)))['call_non_iat']
    tot[0] += n; tot[1] += a
    print('%d linear-sweep=%d audit_icall=%d %s' % (b, n, a, 'EQ' if n == a else 'DIFF'))
print('合計 linear-sweep=%d audit_icall=%d' % tuple(tot))
