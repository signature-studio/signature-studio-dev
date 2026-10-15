#!/usr/bin/env python3
"""FLEngine PE (block00031_PE.bin) の owner thread 同期判定 (0x525ec0) の入力を再現する (PY-178 / #3268 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_owner_thread_probe.py [--expect-owner-stores N]

確認する事実 (期待値と違えば非 0 で終わる):
  (i)   0x525ec0 の比較: 0x525f42 `mov rcx,[rip+..]` (= *(0x15e4f18))、0x525f49 `mov eax,[rax+8]` (X = 0x525940())、0x525f4c `cmp eax,[rcx]`
  (ii)  X+8 の設定: 0x5254b8/0x5254eb で `lea rax,[rax+8]` (= &X+8) を 6 番目の引数にして 0x412b50 を call。0x412b50 は 0x406f80 → CreateThread IAT
  (iii) 0x5251b0 (スレッド関数) が自スレッドの TLS+0x238 に引数 X を入れる (0x5251ca)
  (iv)  スロット 0x15e4f18 の生値 = 0x15e6080 (.data・DIR64 reloc 有り)、0x15e4f18 の RIP 参照の load/store 件数
  (v)   0x15e6080 (dword) への store は --expect-owner-stores 件 (既定 1)。store は 0x41cee9、直前の call は 0x406f90 (GetCurrentThreadId IAT)
"""
import argparse
import os
import re
import struct

import capstone
import pefile

DIR = os.environ["FL_WIN64_DIR"]
PE = os.path.join(DIR, "extracted", "block00031_PE.bin")
SLOT = 0x15E4F18
OWNER = 0x15E6080
CHUNK = 1 << 16

fails = []


def check(ok, msg):
    print(("OK   " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect-owner-stores", type=int, default=1)
    args = ap.parse_args()

    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
                                           pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    imports = {}
    for ent in pe.DIRECTORY_ENTRY_IMPORT:
        for imp in ent.imports:
            if imp.name:
                imports[imp.address] = imp.name.decode()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True

    def dis(va, n=None, until=None):
        rva = va - base
        for s in pe.sections:
            if s.VirtualAddress <= rva < s.VirtualAddress + s.SizeOfRawData:
                fo = s.PointerToRawData + (rva - s.VirtualAddress)
                break
        out = []
        for ins in md.disasm(raw[fo:fo + 512], va):
            out.append((ins.address, ins.mnemonic, ins.op_str))
            if until is not None and ins.address >= until:
                break
            if n is not None and len(out) >= n:
                break
        return out

    def iat_target(va):
        b = raw_at(va, 6)
        if b[:2] != b"\xff\x25":
            return None
        return imports.get(va + 6 + struct.unpack("<i", b[2:6])[0])

    def raw_at(va, n):
        rva = va - base
        for s in pe.sections:
            if s.VirtualAddress <= rva < s.VirtualAddress + s.SizeOfRawData:
                fo = s.PointerToRawData + (rva - s.VirtualAddress)
                return raw[fo:fo + n]
        return b""

    print("## (i) 0x525ec0 の同期比較")
    cmp_ins = {a: (m, o) for a, m, o in dis(0x525F3D, until=0x525F5E)}
    check(cmp_ins.get(0x525F42, ("", ""))[0] == "mov" and "rip" in cmp_ins.get(0x525F42, ("", ""))[1],
          "0x525f42 mov rcx,[rip+..] (*(0x15e4f18))")
    check(cmp_ins.get(0x525F49, ("", ""))[0] == "mov" and "dword ptr [rax + 8]" in cmp_ins.get(0x525F49, ("", ""))[1],
          "0x525f49 mov eax,[rax+8] (X+8)")
    check(cmp_ins.get(0x525F4C, ("", ""))[1] == "eax, dword ptr [rcx]", "0x525f4c cmp eax,[rcx]")
    check(cmp_ins.get(0x525F58, ("", ""))[0] == "test", "0x525f58 test byte [rbp+0x98], al (r8b & r9b)")

    print("## (ii) X+8 = CreateThread の lpThreadId")
    s_ins = dis(0x5254B4, n=None, until=0x5254C6)
    check(any(m == "lea" and o == "rax, [rax + 8]" for _, m, o in s_ins), "0x5254b8 lea rax,[rax+8] (&X+8)")
    check(any(a == 0x5254C1 and m == "call" and o == "0x412b50" for a, m, o in dis(0x5254C1, n=1)),
          "0x5254c1 call 0x412b50 (CreateThread wrapper)")
    check(any(m == "call" and o == "0x406f80" for _, m, o in dis(0x412BC6, n=1)), "0x412bc6 call 0x406f80")
    check(iat_target(0x406F80) == "CreateThread", "0x406f80 = jmp [IAT] = CreateThread (%s)" % iat_target(0x406F80))
    check(any(a == 0x5251CA and m == "mov" and "[rax + 0x238], rcx" in o for a, m, o in dis(0x5251C1, n=4)),
          "0x5251ca mov [rax+0x238],rcx (worker が TLS に X を入れる)")

    print("## (iv)/(v) スロットと dword の参照 (.text 全走査)")
    targets = {SLOT, OWNER}
    hits = []
    for s in pe.sections:
        if not s.Characteristics & 0x20000000:
            continue
        start = base + s.VirtualAddress
        data = raw[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
        off = 0
        while off < len(data):
            nxt = off
            for ins in md.disasm(data[off:off + CHUNK + 16], start + off):
                if ins.address - start - off + ins.size > CHUNK:
                    break
                nxt = ins.address - start + ins.size
                for op in ins.operands:
                    if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                        tgt = ins.address + ins.size + op.mem.disp
                        if tgt in targets:
                            kind = "store" if ins.operands[0].type == capstone.x86.X86_OP_MEM else "load"
                            hits.append((ins.address, kind, tgt, ins.mnemonic, ins.op_str))
            off = nxt if nxt > off else off + 1

    slot_loads = [h for h in hits if h[2] == SLOT and h[1] == "load"]
    slot_stores = [h for h in hits if h[2] == SLOT and h[1] == "store"]
    owner_stores = [h for h in hits if h[2] == OWNER and h[1] == "store"]
    print("slot 0x%x: loads=%d stores=%d" % (SLOT, len(slot_loads), len(slot_stores)))
    check(len(slot_loads) == 23 and len(slot_stores) == 0, "スロットの RIP 参照は load 23・store 0")
    check(struct.unpack("<Q", raw_at(SLOT, 8))[0] == OWNER, "スロットの生値 = 0x%x" % OWNER)
    for a, k, t, m, o in owner_stores:
        print("owner store at 0x%x: %s %s" % (a, m, o))
    check(len(owner_stores) == args.expect_owner_stores,
          "0x%x への dword store が %d 件 (期待 %d)" % (OWNER, len(owner_stores), args.expect_owner_stores))
    if owner_stores:
        a = owner_stores[0][0]
        check(a == 0x41CEE9 and any(m == "call" and o == "0x406f90" for _, m, o in dis(0x41CEE4, n=1)),
              "store 0x41cee9 の eax は call 0x406f90")
        check(iat_target(0x406F90) == "GetCurrentThreadId", "0x406f90 = jmp [IAT] = GetCurrentThreadId")

    print("RESULT: %s" % ("PASS" if not fails else "FAIL (%d)" % len(fails)))
    raise SystemExit(1 if fails else 0)


if __name__ == "__main__":
    main()
