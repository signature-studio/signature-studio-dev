#!/usr/bin/env python3
# slot_table_reach.py — ディスパッチャ 0x18105de80 の 2 表 (T1/T2) の参照形を集め、既知 12 slot が
#   どちらの表の index 域に入るかを判定する (ICALL-62 / #2197)。
#   入力: work/core64_dis.txt (objdump -d -M intel の出力。tools/icall/work/ 配下に作る)。
#   T1 = [r14+rsi*8+0x1307100]・T2 = [r14+r15*8+0x13071a0]、r14 = 0x180000000。
#   index は 32bit 無符号 (mov esi,[rbp] / mov r15d,ecx) なので、表から読める最小 VA は各起点。
#   表の終点はこの判定では決まらない (index の上限は呼び出し側が決める)。
import re
import sys
from pathlib import Path

T1 = 0x181307100
T2 = 0x1813071A0
KNOWN = [0x1813068D0, 0x1813068F8, 0x181306900, 0x181306908, 0x181306910, 0x1813072B0,
         0x1813073F0, 0x1813073F8, 0x181307400, 0x181307408, 0x181307410, 0x181307418]

DIS = Path(sys.argv[1] if len(sys.argv) > 1 else "tools/icall/work/core64_dis.txt")
pat = re.compile(r"r14\+(r15|rsi)\*8\+0x(13[0-9a-f]{5})\]")
refs = {}
for line in DIS.read_text(errors="replace").splitlines():
    m = pat.search(line)
    if m:
        refs.setdefault(m.group(1), set()).add(int(m.group(2), 16))
print("r14-indexed refs:", {k: [hex(x) for x in sorted(v)] for k, v in refs.items()})

for va in KNOWN:
    in_t1 = va >= T1 and (va - T1) % 8 == 0
    in_t2 = va >= T2 and (va - T2) % 8 == 0
    print(hex(va),
          "T1 index %d" % ((va - T1) // 8) if in_t1 else "T1 不可 (起点 %s 未満 or 整列外)" % hex(T1),
          "/ T2 index %d" % ((va - T2) // 8) if in_t2 else "/ T2 不可 (起点 %s 未満 or 整列外)" % hex(T2))
