#!/usr/bin/env python3
"""PY-86 (#2701): py86_slot52.py が数えない参照種で、fn の参照を全数確認する (実機不要・近似)。

  python3 analysis/py86_refs.py <PE.bin> <fn hex,fn hex,...>

1. .text の全バイト位置で、(a) 32bit の絶対値が fn に一致する窓、(b) rel32 (call/jmp/jcc/lea の RIP 相対) として
   fn を指す窓 (末尾 0〜7 バイトの命令後続を許す)、(c) rel8 (短い jmp/jcc) として fn を指す窓を候補にする。
2. 候補ごとに、窓を含む命令を 0〜11 バイト前から逆引きし、命令のオペランドが fn を指すものだけを「命令参照」とする。
   残りは .text 内のデータ上の偶然の一致 (偽陽性)。
3. PE 全体の 8 バイトポインタ (fn の値) を数え、8 バイト境界か・VMT の自己ポインタ判定 (VMT-0xc8) で所属があるかを出す。
   8 バイト境界に無いものは、VMT のスロットではない (RTTI 様の表の中の参照)。
"""
import struct
import sys

import capstone
import numpy as np
import pefile

X = capstone.x86
path = sys.argv[1]
fns = [int(x, 16) for x in sys.argv[2].split(",")]

pe = pefile.PE(path, fast_load=True)
ib = pe.OPTIONAL_HEADER.ImageBase
data = open(path, "rb").read()
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
tdata = data[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
tbase = ib + text.VirtualAddress


def va_to_off(va):
    for s in pe.sections:
        lo = ib + s.VirtualAddress
        if lo <= va < lo + s.Misc_VirtualSize:
            return va - lo + s.PointerToRawData
    return None


def off_to_va(off):
    for s in pe.sections:
        if s.PointerToRawData <= off < s.PointerToRawData + s.SizeOfRawData:
            return ib + s.VirtualAddress + (off - s.PointerToRawData)
    return None


def u64(va):
    off = va_to_off(va)
    return None if off is None else int.from_bytes(data[off:off + 8], "little")


def vmt_owned(hva):
    for k in range(0, 0x400, 8):
        b = hva - k
        if u64(b - 0xC8) == b:
            return True
    return False


md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
b8 = np.frombuffer(tdata, np.uint8)
arr = b8.astype(np.uint32)
n = len(arr) - 3
v = arr[:n] | (arr[1:n + 1] << 8) | (arr[2:n + 2] << 16) | (arr[3:n + 3] << 24)
va = np.uint32(tbase & 0xFFFFFFFF) + np.arange(n, dtype=np.uint32)


def confirmed(p, fn):
    """窓の位置 p (VA) を含む命令で、オペランドが fn を指すものの (VA, 命令) を返す。"""
    out = []
    for back in range(0, 12):
        s = p - back
        ins = next(md.disasm(tdata[s - tbase:s - tbase + 15], s, 1), None)
        if ins is None or not (s <= p < s + ins.size):
            continue
        for op in ins.operands:
            if op.type == X.X86_OP_IMM and op.imm == fn:
                out.append((s, f"{ins.mnemonic} {ins.op_str}"))
            elif op.type == X.X86_OP_MEM and op.mem.base == X.X86_REG_RIP and s + ins.size + op.mem.disp == fn:
                out.append((s, f"{ins.mnemonic} {ins.op_str}"))
            elif op.type == X.X86_OP_MEM and op.mem.base == 0 and op.mem.index == 0 and op.mem.disp == fn:
                out.append((s, f"{ins.mnemonic} {ins.op_str}"))
    return out


print(f".text {len(tdata)} bytes, base {tbase:#x}")
for fn in fns:
    f32 = np.uint32(fn & 0xFFFFFFFF)
    abs4 = np.nonzero(v == f32)[0]
    rel = set()
    for k in range(0, 8):
        rel.update(np.nonzero(v == f32 - (va + np.uint32(4 + k)))[0].tolist())
    s8 = np.nonzero(((arr[:n] == 0xEB) | ((arr[:n] >= 0x70) & (arr[:n] <= 0x7F))))[0]
    s8 = s8[s8 + 2 <= len(arr)]
    rel8 = np.int64(fn) - (np.int64(tbase) + s8.astype(np.int64) + 2)
    short = s8[(rel8 >= -128) & (rel8 <= 127) & (arr[s8 + 1].astype(np.int64) == (rel8 & 0xFF))]
    refs = []
    coincidence = 0
    for p in list(abs4) + sorted(rel) + list(short):
        hit = confirmed(tbase + int(p), fn)
        if hit:
            refs.extend(hit)
        else:
            coincidence += 1
    refs = sorted(set(refs))
    print(f"fn {fn:#x}: 候補 abs32={len(abs4)} rel32={len(rel)} rel8={len(short)} / 命令参照={len(refs)} / データ上の偶然の一致={coincidence}")
    for a, txt in refs:
        print(f"    code ref {a:#x}: {txt}")
    aligned_vmt = 0
    other, mis = [], []
    pat = struct.pack("<Q", fn)
    pos = data.find(pat)
    while pos >= 0:
        hva = off_to_va(pos)
        if hva is not None:
            if hva % 8 == 0:
                if vmt_owned(hva):
                    aligned_vmt += 1
                else:
                    other.append(hex(hva))
            else:
                mis.append(hex(hva))
        pos = data.find(pat, pos + 1)
    print(f"    8-byte ptr: 8 バイト境界 VMT 所属={aligned_vmt} / 8 バイト境界で VMT 外={other} / 非整列={mis}")
