#!/usr/bin/env python3
"""hs_vtable_verify.py — CAB-195 検収: TFruityHost vtable / slot0=Dispatcher の独立照合。

hostshim.c の g_fle_impl[0] = 0x13173a0 (slot0 = Dispatcher) と
CAB-12 A検収確定値 (tools/plugins/REPORT.md / ABI.md) の一致を、A検収素材
block00031_PE.bin (FLEngine) の VMT から独立に読み直して確認する。

数え方の定義:
  * VMT 0x1314108, vtable = VMT+0x70 (ABI.md §2.3)。plugin から見た slot k の
    FLE 実装 VA = *(u64*)(vtable + 8k)  (k = 0..45, 46 slot)。
  * hs_vtable_gen.py が未実行 (FLE PE が本回は別経路) なので、ここでは「表の読み出し」
    だけでなく hostshim.c の静的配列と 1 件ずつ diff する。

使い方: python3 hs_vtable_verify.py [PEパス]
"""
import re
import struct
import sys
import pefile

PE = sys.argv[1] if len(sys.argv) > 1 else '/home/ubuntu/work/analysis/win64/extracted/block00031_PE.bin'
VMT = 0x1314108
VTB = VMT + 0x70
NSLOT = 46
SRC = '/home/ubuntu/work/webstudio/tools/plugins/framework/hostshim/hostshim.c'

d = open(PE, 'rb').read()
pe = pefile.PE(data=d)
base = pe.OPTIONAL_HEADER.ImageBase


def u64(va):
    o = pe.get_offset_from_rva(va - base)
    return struct.unpack_from('<Q', d, o)[0]


native = [u64(VTB + 8 * k) for k in range(NSLOT)]

# hostshim.c の g_fle_impl[] を読む
src = open(SRC, encoding='utf-8').read()
m = re.search(r'g_fle_impl\[HS_SLOTS\]\s*=\s*\{(.*?)\};', src, re.S)
body = m.group(1)
shim = [int(x, 16) for x in re.findall(r'0x[0-9a-fA-F]+', body)]
print('[vtab] FLE PE=%s ImageBase=0x%x VMT=0x%x vtable=0x%x slots=%d'
      % (PE, base, VMT, VTB, NSLOT))
print('[vtab] hostshim.c g_fle_impl 要素数 = %d' % len(shim))
ok = bad = 0
for k in range(NSLOT):
    if k < len(shim) and shim[k] == native[k]:
        ok += 1
    else:
        bad += 1
        print('  NG  slot%-2d native=0x%x shim=%s' % (k, native[k],
              ('0x%x' % shim[k]) if k < len(shim) else 'なし'))
print('[vtab] slot0 = Dispatcher: native 0x%x / hostshim.c 0x%x → %s'
      % (native[0], shim[0] if shim else 0,
         '一致 (CAB-12 A検収 0x13173a0)' if native[0] == 0x13173a0 and shim and shim[0] == 0x13173a0
         else '不一致'))
print('[vtab] 46 slot の一致 = %d / 不一致 = %d' % (ok, bad))

# 参考: slot0 (=0x13173a0) が本当に Dispatcher (ID 分岐) であることを capstone で spot check
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
md = Cs(CS_ARCH_X86, CS_MODE_64)
o = pe.get_offset_from_rva(native[0] - base)
ins = list(md.disasm(d[o:o + 0x400], native[0]))
cands = [i for i in ins if i.mnemonic in ('cmp', 'sub') and '0x47' in i.op_str]
print('[vtab] slot0 先頭 0x400B 内で ID 即値 0x47 に触れる命令: %d 件 (%s)'
      % (len(cands), ['%s %s' % (i.mnemonic, i.op_str) for i in cands[:3]]))
sys.exit(1 if bad else 0)
