#!/usr/bin/env python3
"""表 T0 ([0x16bacd8]) の vtable を PE から確定する (PY-194 / #3402 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py194_t0_vtable.py

検査 (1 つでも外れたら FAIL・終了 1):
- 0xf8cbea が class 参照スロット 0xf80810 を読み、その値 (VMT 0xf808d8) を生成関数 0xf8e890 に渡す。
- VMT 0xf808d8 の vmtClassName が TDictionary<System.Integer,MIDIInput.TRemoteControl>。
- VMT の slot +0x10 (0xf8e830)・+0x18 (0xf8e860) が、[this+0x28]/[this+0x30]・[this+0x38]/[this+0x40] の
  TMethod (code, data) を呼ぶ転送 thunk。
- 0xf80810 を読む命令は .text 内に 1 件だけ (0xf8cbea)。

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> extracted/block00031_PE.bin
"""
import os
import struct
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
CLASS_REF_SLOT = 0xF80810
VMT = 0xF808D8
GEN_FN = 0xF8E890
CALLER_LOAD = 0xF8CBEA
CLASS_NAME = b"TDictionary<System.Integer,MIDIInput.TRemoteControl>"


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = [(s.VirtualAddress, max(s.Misc_VirtualSize, s.SizeOfRawData), s.PointerToRawData)
            for s in pe.sections]

    def fo(va):
        rva = va - base
        for vaddr, size, praw in secs:
            if vaddr <= rva < vaddr + size:
                return praw + (rva - vaddr)
        sys.exit(f"VA {va:#x} が section 外")

    def q(va):
        return struct.unpack_from("<Q", raw, fo(va))[0]

    def disasm(va, n):
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        return [(i.address, i.mnemonic, i.op_str)
                for i, _ in zip(md.disasm(raw[fo(va):fo(va) + n * 16], va), range(n))]

    fails = []

    def check(ok, msg):
        print(("PASS " if ok else "FAIL ") + msg)
        if not ok:
            fails.append(msg)

    check(q(CLASS_REF_SLOT) == VMT, f"class 参照スロット {CLASS_REF_SLOT:#x} の値 = VMT {VMT:#x}")

    check(any(m == "mov" and "rip" in s for _, m, s in disasm(CALLER_LOAD, 1)),
          f"{CALLER_LOAD:#x} が RIP 相対で class 参照スロットを読む")
    check(any(m == "call" and f"{GEN_FN:#x}" in s for _, m, s in disasm(CALLER_LOAD, 6)),
          f"{CALLER_LOAD:#x} の直後に生成関数 {GEN_FN:#x} を呼ぶ")

    vmt_name_ptr = q(VMT - 0x88)
    name_fo = fo(vmt_name_ptr)
    ln = raw[name_fo]
    check(raw[name_fo + 1:name_fo + 1 + ln] == CLASS_NAME,
          f"vmtClassName = {CLASS_NAME.decode()}")

    for slot, off, first_off in ((0xF8E830, 0x10, 0x28), (0xF8E860, 0x18, 0x38)):
        check(q(VMT + off) == slot, f"VMT+{off:#x} の値 = {slot:#x}")
        ins = disasm(slot, 20)
        ok = any(m == "call" and s == f"qword ptr [rbx + {first_off:#x}]" for _, m, s in ins)
        check(ok, f"{slot:#x} は [this+{first_off:#x}] (TMethod code) を呼ぶ転送 thunk")

    refs = []
    text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    t_va = base + text.VirtualAddress
    t_raw = raw[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
    pos = 0
    while pos < len(t_raw):
        end = pos
        for ins in md.disasm(t_raw[pos:], t_va + pos):
            end = ins.address - t_va + ins.size
            for op in ins.operands:
                if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                    if ins.address + ins.size + op.mem.disp == CLASS_REF_SLOT:
                        refs.append(ins.address)
        pos = end if end > pos else pos + 1
    check(refs == [CALLER_LOAD], f"{CLASS_REF_SLOT:#x} を読む命令は {CALLER_LOAD:#x} の 1 件 (実測 {[hex(r) for r in refs]})")

    print(f"summary: {len(fails)} FAIL")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
