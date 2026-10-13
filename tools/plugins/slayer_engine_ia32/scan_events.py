#!/usr/bin/env python3
"""events[] 候補の探索 (#894 受入 1): mov r,[X+8] で base を取り、直後 6 命令内に [r+idx*4] を読む形を列挙する。

  python3 scan_events.py [PATH]   # 既定: $RUNNER_TEMP/fl-win64/extracted/block22434_PE.bin
"""
import hashlib, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from measure import EXPECT_SHA256, parse_pe  # noqa: E402
from capstone import Cs, CS_ARCH_X86, CS_MODE_32  # noqa: E402
from capstone import x86 as cx  # noqa: E402

path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.environ["RUNNER_TEMP"], "fl-win64", "extracted", "block22434_PE.bin")
data = open(path, 'rb').read()
assert hashlib.sha256(data).hexdigest() == EXPECT_SHA256
pe = parse_pe(data)
text = pe['text']
base = (pe['ibase'] or 0) + text['va']
code = data[text['rawptr']:text['rawptr'] + text['vsize']]
md = Cs(CS_ARCH_X86, CS_MODE_32)
md.detail = True
seq = []
pos = 0
while pos < len(code):
    r = list(md.disasm(bytes(code[pos:pos + 15]), base + pos, 1))
    if not r:
        pos += 1
        continue
    seq.append(r[0])
    pos += r[0].size

hits = []
for i, ins in enumerate(seq):
    # 直前 6 命令以内で mov reg,[X+8] (base 読込み) → 後続で [reg+idx*4]
    if ins.mnemonic != 'mov' or len(ins.operands) != 2:
        continue
    dst, src = ins.operands
    if dst.type != cx.X86_OP_REG or src.type != cx.X86_OP_MEM:
        continue
    m = src.mem
    if m.index != 0 or m.disp != 8:
        continue
    r = ins.reg_name(dst.reg)
    for j in range(i + 1, min(i + 7, len(seq))):
        nx = seq[j]
        for op in nx.operands:
            if op.type == cx.X86_OP_MEM and op.mem.base and nx.reg_name(op.mem.base) == r and op.mem.index and op.mem.scale == 4:
                hits.append((ins.address, '%s %s' % (ins.mnemonic, ins.op_str), nx.address, '%s %s' % (nx.mnemonic, nx.op_str)))
                break
        else:
            continue
        break

print('[events-cand] count=%d' % len(hits))
for a, t, b, t2 in hits:
    print('  0x%x  %-28s -> 0x%x  %s' % (a, t, b, t2))
