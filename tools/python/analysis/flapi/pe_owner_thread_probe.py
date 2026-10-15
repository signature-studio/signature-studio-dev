#!/usr/bin/env python3
"""FLEngine PE (block00031_PE.bin) の owner thread 同期判定 (0x525ec0) の入力を再現する (PY-178 / #3268 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_owner_thread_probe.py \
      [--expect-owner-stores N] [--expect-jne-target VA]

確認する事実 (期待値と違えば非 0 で終わる):
  (i)    0x525ec0 の比較: 0x525f42 `mov rcx,[rip+..]` (= *(0x15e4f18))、0x525f49 `mov eax,[rax+8]` (X = 0x525940())、0x525f4c `cmp eax,[rcx]`
  (ii)   0x525940 の X 生成: TLS が空なら 0x522710 を dl=1 で呼ぶ (0x52595b)。0x522710 は 0x522741 で [X+0x40]=1 を立て、
         0x522756 で dl=0・r8=0 の 0x5252d0 を呼ぶ
  (iii)  0x525400 の分岐: 0x525485 `cmp [X+0x40],0`、0x525489 `jne` の飛び先は --expect-jne-target (既定 0x525557)。
         CreateThread 経路 0x5254d0 は 0x525489 の fall-through 側 (0x525497 の je) だけ
  (iv)   0x525557 の格納: call 0x423460 (GetCurrentThread) → [X+0x10]、call 0x423470 (GetCurrentThreadId) → 0x52556d `mov [X+8],eax`
  (v)    CreateThread 経路 (fall-through 側): 0x5254b8 lea (&X+8)・0x5254c1 call 0x412b50・0x412bc6 call 0x406f80 = CreateThread。
         0x5251ca で worker の TLS+0x238 に引数 X を入れる
  (vi)   スロット 0x15e4f18 の生値 = 0x15e6080 (.data・DIR64 reloc 有り)、0x15e4f18 の RIP 参照の load/store 件数
  (vii)  0x15e6080 (dword) への store は --expect-owner-stores 件 (既定 1)。store は 0x41cee9、直前の call は 0x406f90 (GetCurrentThreadId IAT)
"""
import argparse
import os
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
    ap.add_argument("--expect-jne-target", type=lambda s: int(s, 0), default=0x525557)
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

    def at(va):
        r = dis(va, n=1)
        return (r[0][1], r[0][2]) if r and r[0][0] == va else ("", "")

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

    print("## (ii) 0x525940 の X 生成 (dl=1 → [X+0x40]=1)")
    check(at(0x52595B) == ("mov", "dl, 1") and at(0x52595D) == ("call", "0x522710"),
          "0x52595b mov dl,1 → 0x52595d call 0x522710")
    check(at(0x522741) == ("mov", "byte ptr [rax + 0x40], 1"), "0x522741 mov byte [X+0x40],1")
    check(at(0x522751) == ("xor", "edx, edx") and at(0x522753) == ("xor", "r8, r8")
          and at(0x522756) == ("call", "0x5252d0"), "0x522756 call 0x5252d0 (dl=0・r8=0)")

    print("## (iii) 0x525400 の分岐 ([X+0x40] で CreateThread 経路を避ける)")
    check(at(0x525485) == ("cmp", "byte ptr [rax + 0x40], 0"), "0x525485 cmp byte [X+0x40],0")
    check(at(0x525489)[0] == "jne" and at(0x525489)[1] == "0x%x" % args.expect_jne_target,
          "0x525489 jne → %s (期待 0x%x)" % (at(0x525489)[1], args.expect_jne_target))
    check(at(0x525497) == ("je", "0x5254d0") and 0x525489 + 6 == 0x52548F,
          "0x525497 je 0x5254d0 (CreateThread 経路は 0x525489 の fall-through 側のみ)")

    print("## (iv) 0x525557 の格納 ([X+8] = 呼出しスレッドの ID)")
    check(at(0x525557) == ("call", "0x423460") and iat_target(0x423460) == "GetCurrentThread",
          "0x525557 call 0x423460 (IAT: %s)" % iat_target(0x423460))
    check(at(0x525560) == ("mov", "qword ptr [rcx + 0x10], rax"), "0x525560 mov [X+0x10],rax")
    check(at(0x525564) == ("call", "0x423470") and iat_target(0x423470) == "GetCurrentThreadId",
          "0x525564 call 0x423470 (IAT: %s)" % iat_target(0x423470))
    check(at(0x52556D) == ("mov", "dword ptr [rcx + 8], eax"), "0x52556d mov dword [X+8],eax")

    print("## (v) CreateThread 経路 (fall-through 側): lpThreadId = &X+8")
    s_ins = dis(0x5254B4, until=0x5254C6)
    check(any(m == "lea" and o == "rax, [rax + 8]" for _, m, o in s_ins), "0x5254b8 lea rax,[rax+8] (&X+8)")
    check(at(0x5254C1) == ("call", "0x412b50"), "0x5254c1 call 0x412b50 (CreateThread wrapper)")
    check(at(0x412BC6) == ("call", "0x406f80"), "0x412bc6 call 0x406f80")
    check(iat_target(0x406F80) == "CreateThread", "0x406f80 = jmp [IAT] = CreateThread (%s)" % iat_target(0x406F80))
    check(at(0x5251CA)[0] == "mov" and "[rax + 0x238], rcx" in at(0x5251CA)[1],
          "0x5251ca mov [rax+0x238],rcx (worker が TLS に引数 X を入れる)")

    print("## (vi)/(vii) スロットと dword の参照 (.text 全走査)")
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
        check(a == 0x41CEE9 and at(0x41CEE4) == ("call", "0x406f90"),
              "store 0x41cee9 の eax は call 0x406f90")
        check(iat_target(0x406F90) == "GetCurrentThreadId", "0x406f90 = jmp [IAT] = GetCurrentThreadId")

    print("RESULT: %s" % ("PASS" if not fails else "FAIL (%d)" % len(fails)))
    raise SystemExit(1 if fails else 0)


if __name__ == "__main__":
    main()
