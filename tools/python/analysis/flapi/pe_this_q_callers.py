#!/usr/bin/env python3
"""FLEngine PE で、関数 VA を直接 call (E8) している箇所のうち、rcx (this) が Q 本体であると
同一基本ブロック内から確定できる呼出元を分類する (PY-169 / #3817 受入 1 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_this_q_callers.py <VA(16進)> [<VA> ...]

判定 (全件列挙はしない。直前 WINDOW バイトを線形に復号し、最後の分岐・call・ret の後ろだけを見る):
- `mov r, [rip+G]` (G = 0x15e4790) で r = PSLOT (タグ P)。
- `mov r2, [r]` で r が P なら r2 = Q 本体 (タグ Q)。`mov r2, [rip+QSLOT]` (QSLOT = 0x141d6b8) も Q。
- reg-reg の mov・lea は タグを複写する。それ以外で r を書く命令はタグを消す。
- call 直前の rcx のタグが Q なら `Q`、rcx を同ブロック内で書く命令が他にあれば `other`、無ければ `unknown` (ブロック外)。
"""
import os
import struct
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
G_VA = 0x15E4790
PSLOT_VA = 0x141D6B8
WINDOW = 160
X86 = capstone.x86


def reg_name(r, md):
    return md.reg_name(r) if r else None


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = next(s for s in pe.sections if s.Name.startswith(b".text"))
    data = raw[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
    start = base + text.VirtualAddress
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    targets = {int(a, 16) for a in sys.argv[1:]}
    for t in sorted(targets):
        callers = []
        for i in range(len(data) - 5):
            if data[i] == 0xE8 and start + i + 5 + struct.unpack_from("<i", data, i + 1)[0] == t:
                callers.append(start + i)
        counts = {"Q": 0, "other": 0, "unknown": 0}
        for c in callers:
            off = c - start
            lo = max(0, off - WINDOW)
            insns = list(md.disasm(data[lo:off + 5], start + lo))
            insns = [x for x in insns if x.address < c]
            tags = {}
            rcx_writes = 0
            rcx_tag = None
            # 直前の分岐・call・ret より後ろだけを使う
            cut = 0
            for k, ins in enumerate(insns):
                if ins.group(capstone.CS_GRP_JUMP) or ins.group(capstone.CS_GRP_CALL) or ins.group(capstone.CS_GRP_RET):
                    cut = k + 1
            block = insns[cut:]
            for ins in block:
                ops = ins.operands
                if ins.mnemonic in ("mov", "lea", "movabs") and len(ops) == 2 and ops[0].type == X86.X86_OP_REG:
                    dst = ins.reg_name(ops[0].reg)
                    src = ops[1]
                    new = None
                    if src.type == X86.X86_OP_MEM and src.mem.base == X86.X86_REG_RIP:
                        tgt = ins.address + ins.size + src.mem.disp
                        if ins.mnemonic == "mov" and tgt == G_VA:
                            new = "P"
                        elif ins.mnemonic == "mov" and tgt == PSLOT_VA:
                            new = "Q"
                    elif src.type == X86.X86_OP_MEM and src.mem.base and src.mem.index == 0 and src.mem.disp == 0:
                        base_name = ins.reg_name(src.mem.base)
                        if ins.mnemonic == "mov" and tags.get(base_name) == "P":
                            new = "Q"
                    elif src.type == X86.X86_OP_REG and ins.mnemonic in ("mov",):
                        new = tags.get(ins.reg_name(src.reg))
                    if dst == "rcx":
                        rcx_writes += 1
                        rcx_tag = new
                    if new is None:
                        tags.pop(dst, None)
                    else:
                        tags[dst] = new
                    continue
                if ins.mnemonic == "call":
                    continue
                if ops and ops[0].type == X86.X86_OP_REG:
                    dst = ins.reg_name(ops[0].reg)
                    if dst == "rcx":
                        rcx_writes += 1
                        rcx_tag = None
                    tags.pop(dst, None)
            if rcx_tag == "Q":
                counts["Q"] += 1
                verdict = "Q"
            elif rcx_writes > 0:
                counts["other"] += 1
                verdict = "other"
            else:
                counts["unknown"] += 1
                verdict = "unknown"
            print(f"  {hex(c)} rcx={verdict}")
        print(f"{hex(t)} direct E8 callers: {len(callers)} / {counts}")


if __name__ == "__main__":
    main()
