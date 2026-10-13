#!/usr/bin/env python3
"""m9_tablebind.py (M9 [F9] PoC 前段): DLL .text 先頭の低 VA 領域を基にたべ c33
  m9_tables.c を tools/m9/work/ に生成する。
対象: VA 0x180001000..0x180002000 (c38c8 family の算術合成 table base が置く
  JMP-thunk 領域)。memcpy 先 = 0x35d01000 (linear memory 空領域, MSCRATCH 0x35e00000 より下)。
"""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared'))
from paths import PLUGINS_DIR  # noqa: E402

DLL = os.path.join(PLUGINS_DIR, 'ott', 'binaries', 'OTT_vst2_win64.dll')
TABLE_LO = 0x180001000
TABLE_HI = 0x180002000
LMEM = 0x35d01000

d = open(DLL, 'rb').read()
pe = struct.unpack_from('<I', d, 0x3c)[0]
secoff = pe + 0x18 + struct.unpack_from('<H', d, pe + 0x14)[0]
nsec = struct.unpack_from('<H', d, pe + 6)[0]
imagebase = struct.unpack_from('<Q', d, pe + 0x18 + 0x18)[0]
rva = TABLE_LO - imagebase
raw = None
for k in range(nsec):
    o = secoff + k * 40
    vs, va, rs, ro = struct.unpack_from('<IIII', d, o + 8)
    if va <= rva < va + rs:
        fo = ro + (rva - va)
        raw = d[fo:fo + (TABLE_HI - TABLE_LO)]
        break
assert raw is not None, 'table RVA not in raw sections'
hexbytes = ','.join('0x%02x' % b for b in raw)
src = f'''/* m9_tables.c (M9 [F9] 自動生成 by m9_tablebind.py): DLL .text 低 VA 0x{TABLE_LO:x}..0x{TABLE_HI:x}
 * を linear memory 0x{LMEM:x} に敷設 (IR base remap 先)。m9_gbox_ctor_setup から
 * m9_tables_install() を 1 回呼ぶ (idempotent)。
 */
#include <stdint.h>
#include <string.h>
static const unsigned char m9tbl[] = {{
{hexbytes}
}};
void m9_tables_install(void) {{
  memcpy((void*){LMEM}u, m9tbl, {len(raw)}u);
}}
'''
out = sys.argv[1] if len(sys.argv) > 1 else 'work/m9_tables.c'
open(out, 'w').write(src)
print(f'[m9_tablebind] {TABLE_LO:x}..{TABLE_HI:x} -> {LMEM:x} ({len(raw)} B) -> {out}')
