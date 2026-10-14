#!/usr/bin/env python3
"""PY-71 (#2501): 指定 VA の呼出し元と、RIP 相対・絶対値での参照を列挙する (実機不要)。

  python3 analysis/py67_callers.py <PE.bin> <target VA hex>[,<target VA hex>...] [before_insns]

1. .text を 1 回だけ線形走査し、target を直接 call/jmp する箇所を出す。各箇所に
   fn= (呼出し元の関数先頭。int3 パディングの直後の命令を近似として採る) と直前 before_insns 命令を出す。
2. target を指す RIP 相対の lea / load / store を出す (py67_indirect.py と同じ判定)。
   target を即値 (imm32/imm64) として持つ命令 (mov reg, imm 等) も [imm] として出す (表への絶対アドレス参照の検出)。
3. ファイル全体で target の 8 バイト絶対値の格納箇所を出し、その前後 4 要素 (表の広がり) を出す。
PE 上の絶対 VA は ImageBase を足さない値 (capstone の出力と同じ)。
"""
import collections
import struct
import sys

import capstone
import pefile

X = capstone.x86
path = sys.argv[1]
targets = [int(v, 0) for v in sys.argv[2].split(",")]
before = int(sys.argv[3], 0) if len(sys.argv) > 3 else 8
tset = set(targets)

pe = pefile.PE(path, fast_load=True)
data = open(path, "rb").read()
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
tdata = data[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
tbase = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
ring = collections.deque(maxlen=before)
fn = None
pad = True
off = 0
while off < len(tdata):
    ins = next(md.disasm(tdata[off:off + 15], tbase + off, 1), None)
    if ins is None:
        off += 1
        ring.clear()
        pad = True
        continue
    off += ins.size
    if ins.mnemonic == "int3":
        pad = True
        ring.clear()
        continue
    if pad:
        fn = ins.address
        pad = False
        ring.clear()
    line = f"{ins.address:#x}: {ins.mnemonic} {ins.op_str}"
    if (ins.mnemonic in ("call", "jmp") and ins.operands
            and ins.operands[0].type == X.X86_OP_IMM and ins.operands[0].imm in tset):
        t = ins.operands[0].imm
        print(f"[{t:#x}] call-site {ins.address:#x} fn={fn:#x} [direct-{ins.mnemonic}]")
        for prev in ring:
            print(f"    {prev}")
        print(f"  > {line}")
    for op in ins.operands:
        if op.type == X.X86_OP_IMM and ins.mnemonic not in ("call", "jmp") and op.imm in tset:
            print(f"[{op.imm:#x}] {ins.address:#x} fn={fn:#x}: {line}  [imm]")
        if op.type != X.X86_OP_MEM or op.mem.base != X.X86_REG_RIP:
            continue
        tgt = ins.address + ins.size + op.mem.disp
        if tgt not in tset:
            continue
        if ins.mnemonic == "lea":
            kind = "lea"
        elif op.access & capstone.CS_AC_WRITE:
            kind = "STORE"
        else:
            kind = "load"
        print(f"[{tgt:#x}] {ins.address:#x} fn={fn:#x}: {line}  [{kind}]")
    ring.append(line)


def locate(h):
    for s in pe.sections:
        if s.PointerToRawData <= h < s.PointerToRawData + s.SizeOfRawData:
            va = pe.OPTIONAL_HEADER.ImageBase + s.VirtualAddress + (h - s.PointerToRawData)
            return s.Name.rstrip(b"\0").decode(), va
    return "?", 0


for t in targets:
    needle = struct.pack("<Q", t)
    pos = data.find(needle)
    hits = []
    while pos != -1:
        hits.append(pos)
        pos = data.find(needle, pos + 1)
    print(f"# [{t:#x}] absolute 8-byte value: {len(hits)} hit(s)")
    for h in hits[:50]:
        sec, va = locate(h)
        print(f"#   file offset {h:#x} section={sec} va={va:#x}")
        vals = []
        for i in range(-4, 5):
            p = h + 8 * i
            if 0 <= p and p + 8 <= len(data):
                vals.append(struct.unpack_from("<Q", data, p)[0])
        print("#     neighbors (-4..+4): " + " ".join(f"{v:#x}" for v in vals))
