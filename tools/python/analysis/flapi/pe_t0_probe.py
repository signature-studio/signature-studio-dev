#!/usr/bin/env python3
"""FLEngine PE (block00031_PE.bin) の表 T0 ([0x16bacd8]) と item tag・K の主張 (PY-182 / #3287) を PE 上で再検査する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_t0_probe.py

検査するのは次の 2 種だけ (命令列の存在検査と、大域 K の書込み 0 件の全 .text 走査):
- 構造: T0 の 36 バイト要素 (stride 0x24)・key → id (0xf8e4a0 は key を読まない)・
  添字探索 (0xf8e3f0)・update (0xf8e4e0 の vtable +0x18 を (rec,5)・(payload,1) で呼ぶ)・
  insert (0xf8ea80)・erase (0xf8eb10 → 0xf8e5f0)・contains (0xf8ecd0)・find (0xf8ec70)・
  f82a10 / f82c20 が読む K の参照。
- 大域 K (0x16bacf0): .text 全体で RIP 相対の書込み命令が 0 件、かつ絶対 disp32・即値の 4 byte 列が 0 件。
検査しない: vtable の同定 (T0 の vtable 候補は REPORT の記述のみ)・f8ca50 の解決の意味・REPORT の推論そのもの。
不一致が 1 つでもあれば終了 1。
"""
import os
import struct
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")

K, V, T0 = 0x16BACF0, 0x16BACEC, 0x16BACD8
F4A0, F3C0, F3F0, F4E0, F590, F5F0 = 0xF8E4A0, 0xF8E3C0, 0xF8E3F0, 0xF8E4E0, 0xF8E590, 0xF8E5F0
EA80, EB10, ECD0, EC70 = 0xF8EA80, 0xF8EB10, 0xF8ECD0, 0xF8EC70
SET_BB, NOTIFY = 0xF82A10, 0xF82C20
K_READS = [0xF82A43, 0xF82C48]


def load():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    return raw, pe.OPTIONAL_HEADER.ImageBase, pe.sections


def file_off(base, secs, va):
    rva = va - base
    for s in secs:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.PointerToRawData + (rva - s.VirtualAddress)
    sys.exit(f"VA {va:#x} が section 外")


def insns(raw, base, secs, va, count):
    fo = file_off(base, secs, va)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    out = []
    for i, ins in enumerate(md.disasm(raw[fo:fo + count * 16], va)):
        if i >= count:
            break
        rip = None
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                rip = ins.address + ins.size + op.mem.disp
        out.append((ins.address, ins.mnemonic, ins.op_str, rip))
    return out


def body(raw, base, secs, va, count=120):
    out = []
    for a, m, op, r in insns(raw, base, secs, va, count):
        out.append((m, op, r))
        if m == "ret":
            break
    return out


def full(m, op):
    return f"{m} {op}"


def has(b, text):
    return any(full(m, op) == text for m, op, _ in b)


def seq(b, first, second, gap=4):
    return any(full(m, op) == first and any(full(m2, op2) == second for m2, op2, _ in b[i + 1:i + 1 + gap])
               for i, (m, op, _) in enumerate(b))


def writes_memory(ins, op):
    # capstone は cmpxchg・fst*・fist* のメモリ書込みを READ と返すため、助記で補う
    text = (ins.mnemonic + " " + ins.op_str).replace("lock ", "", 1)
    return bool(op.access & capstone.CS_AC_WRITE) or text.startswith(("cmpxchg", "fst", "fist"))


def sweep_writes_to(raw, base, secs, targets):
    text = [s for s in secs if s.Name.rstrip(b"\0") == b".text"][0]
    va0 = base + text.VirtualAddress
    code = raw[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    hits = []
    i = 0
    while i < len(code):
        for ins in md.disasm(code[i:i + 16], va0 + i):
            for op in ins.operands:
                if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                    t = ins.address + ins.size + op.mem.disp
                    if t in targets and writes_memory(ins, op):
                        hits.append((ins.address, t))
            i += ins.size
            break
        else:
            i += 1
    return hits


def main():
    raw, base, secs = load()
    fails = 0

    def check(name, ok):
        nonlocal fails
        fails += 0 if ok else 1
        print(f"{'PASS' if ok else 'FAIL'} {name}")

    f4a0 = body(raw, base, secs, F4A0, 20)
    check("f8e4a0: [this+0x18] の vtable +0x20 を呼び、+1 して 31bit に切る",
          has(f4a0, "mov rax, qword ptr [rcx + 0x18]") and has(f4a0, "call qword ptr [rax + 0x20]")
          and has(f4a0, "and eax, 0x7fffffff") and has(f4a0, "add eax, 1"))
    check("f8e4a0: key (edx) を読まない", not any("edx" in op or "rdx" in op for _, op, _ in f4a0))

    f3f0 = body(raw, base, secs, F3F0, 90)
    check("f8e3f0: 要素 stride 0x24 (36 byte)", has(f3f0, "add r14, 0x24"))
    check("f8e3f0: 空き marker 0xffffffff との比較 (cmp eax, -1)", has(f3f0, "cmp eax, -1"))
    check("f8e3f0: 一致判定は [obj+0x18] の vtable +0x18 (elt.sub, key)",
          has(f3f0, "call qword ptr [rax + 0x18]") and has(f3f0, "mov r8d, ebx"))

    f4e0 = body(raw, base, secs, F4E0, 80)
    check("f8e4e0: f8e4a0 と f8e3f0 を呼ぶ", has(f4e0, f"call {F4A0:#x}") and has(f4e0, f"call {F3F0:#x}"))
    check("f8e4e0: vtable +0x18 を (old rec, 5) で呼ぶ (rsi = this の vtable)",
          seq(f4e0, "mov r8b, 5", "call qword ptr [rsi + 0x18]", 4))
    check("f8e4e0: vtable +0x18 を (payload, 1) で呼ぶ (rbx = this の vtable)",
          seq(f4e0, "mov r8b, 1", "call qword ptr [rbx + 0x18]", 4))

    f590 = body(raw, base, secs, F590, 40)
    check("f8e590: 要素の先頭 dword = id (edx)・+4 = sub (r9d)",
          has(f590, "mov dword ptr [rax], edx") and has(f590, "mov dword ptr [rax + 4], r9d"))
    check("f8e590: 件数 +0x10 を 1 増やし、vtable +0x10 (key,1) と +0x18 (rec,1) を呼ぶ",
          has(f590, "add qword ptr [rbx + 0x10], 1") and seq(f590, "mov r8b, 1", "call qword ptr [rsi + 0x10]", 4)
          and seq(f590, "mov r8b, 1", "call qword ptr [rbx + 0x18]", 4))

    ea80 = body(raw, base, secs, EA80, 60)
    check("f8ea80 (insert): 件数 >= [this+0x20] で f8e3c0 (伸長) を呼ぶ",
          has(ea80, "cmp rax, qword ptr [rbx + 0x20]") and has(ea80, f"call {F3C0:#x}"))
    check("f8ea80: 既存なら 0x448ee0 経路 (idx>=0 で分岐)、無ければ slot=~idx で f8e590",
          has(ea80, f"call {F4A0:#x}") and has(ea80, "not r8") and has(ea80, f"call {F590:#x}"))

    ecd0 = body(raw, base, secs, ECD0, 20)
    check("f8ecd0 (contains): f8e3f0 >= 0 を返す", has(ecd0, f"call {F3F0:#x}") and has(ecd0, "setge al"))

    eb10 = body(raw, base, secs, EB10, 30)
    check("f8eb10 (erase): f8e4a0 の id を使い f8e5f0 を flag 5 で呼ぶ",
          has(eb10, f"call {F4A0:#x}") and has(eb10, f"call {F5F0:#x}")
          and has(eb10, "mov byte ptr [rsp + 0x20], 5"))

    f5f0 = body(raw, base, secs, F5F0, 120)
    check("f8e5f0 (erase 本体): f8e3f0 を呼び、消した slot に marker -1 を書く",
          has(f5f0, f"call {F3F0:#x}") and has(f5f0, "mov dword ptr [rax + rdx*4], 0xffffffff"))
    check("f8e5f0: 件数 [this+0x10] を 1 減らす", has(f5f0, "sub qword ptr [rbx + 0x10], 1"))

    ec70 = body(raw, base, secs, EC70, 40)
    check("f8ec70 (find): f8e3f0 の結果が >= 0 なら 28 byte を複写する",
          has(ec70, f"call {F3F0:#x}") and has(ec70, "setge cl") and has(ec70, "movsd dword ptr [rdi], dword ptr [rsi]"))

    set_bb = insns(raw, base, secs, SET_BB, 400)
    check("f82a10 が K を読む (dl≠0 分岐の比較)",
          any(r == K and a == K_READS[0] for a, _, _, r in set_bb))
    notify = insns(raw, base, secs, NOTIFY, 150)
    check("f82c20 が K を読む (key 比較)", any(r == K and a == K_READS[1] for a, _, _, r in notify))

    writes = sweep_writes_to(raw, base, secs, {K})
    check(f"K (0x16bacf0) への RIP 相対の書込み 0 件 (.text 全走査。hits={writes})", len(writes) == 0)
    pat = struct.pack("<I", K)
    check("K の絶対 disp32・即値の 4 byte 列 0 件 (ファイル全体)", raw.count(pat) == 0)
    print(f"summary: {'OK' if fails == 0 else f'{fails} FAIL'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
