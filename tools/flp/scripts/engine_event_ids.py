#!/usr/bin/env python3
"""Recover the FLP event IDs that FLEngine_x64.dll (Win, FL 26.1.7) writes.

Method: the engine's FLP stream class (VA 0xa9e000..0xaa0000) exposes
  0xa9ec60  WriteEventHeader(id)   -- id<=0xFF: 1 byte; else 0xAC + u32 (extended id)
  0xa9eb60  WriteText(id, str16)   -- UTF-16 text event
  0xa9ea80  WriteData(id, ptr, n)  -- raw/data event
  0xa9ece0  Scramble(buf, n, key)  -- XOR scrambler used for the licensee string
Every `call` to these helpers is located by a rel32 scan of .text and the nearest preceding
`mov edx, imm32` (opcode BA) is taken as the event id. Result: engine_event_ids.json.
Usage: engine_event_ids.py [FLEngine_x64.dll] [out.json]
"""
import collections, json, re, struct, sys
import pefile

DLL = sys.argv[1] if len(sys.argv) > 1 else '/home/ubuntu/work/analysis/win64/extracted/block00031_PE.bin'
OUT = sys.argv[2] if len(sys.argv) > 2 else 'corpus/engine_event_ids.json'
HELPERS = {0xa9ec60: 'header', 0xa9eb60: 'text16', 0xa9ea80: 'data'}

pe = pefile.PE(DLL, fast_load=True)
data = open(DLL, 'rb').read()
base = pe.OPTIONAL_HEADER.ImageBase
text = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
code = data[text.PointerToRawData:text.PointerToRawData + text.Misc_VirtualSize]
res = collections.defaultdict(lambda: {'helper': set(), 'sites': []})
unresolved = 0
for m in re.finditer(rb'\xe8', code):
    i = m.start()
    if i + 5 > len(code):
        continue
    tgt = base + text.VirtualAddress + i + 5 + struct.unpack_from('<i', code, i + 1)[0]
    if tgt not in HELPERS:
        continue
    back = code[max(0, i - 64):i]
    j = back.rfind(b'\xba')
    if j < 0 or j + 5 > len(back):
        unresolved += 1
        continue
    eid = struct.unpack_from('<I', back, j + 1)[0]
    if eid > 0xffffffff:
        unresolved += 1
        continue
    r = res[eid]
    r['helper'].add(HELPERS[tgt])
    r['sites'].append(hex(base + text.VirtualAddress + i))
out = {
    'dll': DLL, 'imageBase': hex(base), 'unresolvedCallSites': unresolved,
    'ids': {str(k): {'hex': hex(k), 'helper': sorted(v['helper']), 'sites': v['sites']} for k, v in sorted(res.items())},
}
json.dump(out, open(OUT, 'w'), indent=1)
print(f'{len(res)} distinct event ids written by FLEngine; unresolved call sites={unresolved}')
