#!/usr/bin/env python3
"""ui 操作 27 関数の戻り値と引数型 (PY-141 / #3034) の PE 上の根拠を検算する解析補助 (読取りのみ)。

検算する事実 (結論は tools/python/REPORT_PY141.md):
  1. 0xd84680 の書込みは out+0 (`[rbx]`) だけ。out+8 (`[rbx+8]`) への書込みは無い。
  2. ui.selectWindow (0xd6c140) の out+8 (`[rbp+0x58]`) への書込みは無い (読むだけ)。
  3. loader (0xc39600〜0xc3a000) が GetProcAddress で読む名前と格納変数の対応。
     0x15e4280 → 0x16b8298 → PyLong_FromLong、0xc38bc0 → 0x16b82e0 → _Py_NoneStruct、
     0x15e30c8 → 0x16b8470 → PyErr_Occurred、0x15e1e58 → 0x16b82f0 → PyArg_ParseTuple。
  4. 0xd843d0 の成功経路 (0xd844c6) は out+8 ([rsi+8]) へ [obj+0x10] を書く。
     呼出し元は scrollWindow の handler 0xd6d300 (out = [rbp+0x88]) と wrapper 0xd84740。
  5. scrollWindow の handler 0xd6d300 は out+0 だけを読み (0xd6d3d1)、out+8 ([rbp+0x90]) に触れない。
  6. 0x415610 の型記述子: [0xd81740] → 0xd81748 (tkRecord・TPyCallSynchronizedResult・RecSize 0x18・
     managed 1 件・TypeRef は string (tkUString)・FldOffset 0x10)。
  7. 0xd82c20: status ≠ 0 は 0xd82c55 へ、status < 0 は 0xd82c6a へ。status == 0 は PyErr_Occurred
     の非 NULL で NULL (0xd82c4a)、NULL なら Py_None (0xd82c5c)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py141_probe.py

期待値と一致しなければ rc 1 で止まる。
"""
import os
import re
import struct
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
LOADER = (0xC39600, 0xC3A000)
SLOT_NAMES = {
    0x16B8298: "PyLong_FromLong",
    0x16B82E0: "_Py_NoneStruct",
    0x16B82F0: "PyArg_ParseTuple",
    0x16B8470: "PyErr_Occurred",
}
FAIL = []


def check(ok, msg):
    print(("ok   " if ok else "FAIL ") + msg)
    if not ok:
        FAIL.append(msg)


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = [(s.VirtualAddress, max(s.Misc_VirtualSize, s.SizeOfRawData), s.PointerToRawData)
            for s in pe.sections]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def v2o(va):
        rva = va - base
        for vaddr, size, praw in secs:
            if vaddr <= rva < vaddr + size:
                return praw + (rva - vaddr)
        return None

    def o2v(off):
        for vaddr, size, praw in secs:
            if praw <= off < praw + size:
                return base + vaddr + (off - praw)
        return None

    def disasm(start, end):
        return list(md.disasm(raw[v2o(start):v2o(start) + end - start], start))

    def rip_target(i):
        m = re.search(r"\[rip ([+-]) (0x[0-9a-f]+)\]", i.op_str)
        if not m:
            return None
        d = int(m.group(2), 16)
        return i.address + i.size + (d if m.group(1) == "+" else -d)

    def direct(i):
        if i.mnemonic.startswith(("j", "call")) and i.op_str.startswith("0x"):
            return int(i.op_str, 16)
        return None

    def utf16(va):
        fo = v2o(va)
        out = []
        for k in range(0, 256, 2):
            c = raw[fo + k:fo + k + 2]
            if c == b"\0\0":
                break
            out.append(c.decode("utf-16-le"))
        return "".join(out)

    def qword_at(va):
        return struct.unpack_from("<Q", raw, v2o(va))[0]

    def stores(ins):
        return [i for i in ins if i.mnemonic == "mov" and "ptr [" in i.op_str.split(", ")[0]]

    # 1. 0xd84680 (out の書込み先)
    ins = disasm(0xD84680, 0xD846DB)
    dests = [i.op_str.split(", ")[0] for i in stores(ins)]
    print("0xd84680 の store 先:", dests)
    out_dests = [d for d in dests if "rbx" in d]
    check(len(out_dests) == 3 and all(d == "qword ptr [rbx]" for d in out_dests),
          "0xd84680 の out (rbx 基底) への store は out+0 (qword ptr [rbx]) の 3 箇所だけ")

    # 2. selectWindow の out+8 ([rbp+0x58]) への書込み
    ins = disasm(0xD6C140, 0xD6C1F7)
    hits = [i for i in stores(ins) if "[rbp + 0x58]" in i.op_str.split(", ")[0]]
    check(not hits, "0xd6c140 に out+8 ([rbp+0x58]) への書込みは無い (読むのは 0xd6c1be の 1 箇所)")

    # 3. loader の名前と格納先
    loader = {}
    ins = disasm(*LOADER)
    for idx, i in enumerate(ins):
        if i.mnemonic == "mov" and i.op_str.startswith("qword ptr [rip") and i.op_str.endswith(", rax"):
            var = rip_target(i)
            for j in reversed(ins[max(0, idx - 6):idx]):
                tgt = rip_target(j) if j.mnemonic == "lea" else None
                if tgt is None:
                    continue
                name = utf16(tgt)
                if len(name) >= 3 and name.isascii() and name.replace("_", "").isalnum():
                    loader[var] = name
                    break
    for var, want in SLOT_NAMES.items():
        check(loader.get(var) == want, f"loader: var {var:#x} <- {want!r} (実測 {loader.get(var)!r})")

    # 4. 参照チェーン (スロット → 変数)
    check(qword_at(0x15E4280) == 0x16B8298, "[0x15e4280] = 0x16b8298 (PyLong_FromLong の変数へのポインタ)")
    check(qword_at(0x15E1E58) == 0x16B82F0, "[0x15e1e58] = 0x16b82f0 (PyArg_ParseTuple の変数へのポインタ)")
    check(qword_at(0x15E30C8) == 0x16B8470, "[0x15e30c8] = 0x16b8470 (PyErr_Occurred の変数へのポインタ)")
    ins = disasm(0xC38BC0, 0xC38BC8)
    check(rip_target(ins[0]) == 0x16B82E0 and ins[1].mnemonic == "ret",
          "0xc38bc0 は [0x16b82e0] (= _Py_NoneStruct のアドレス) を返す leaf (呼出し無し)")
    ins = disasm(0xD6C1C1, 0xD6C1CA)
    check(rip_target(ins[0]) == 0x15E4280, "0xd6c1c1 の mov は [0x15e4280] を読む (PyLong_FromLong)")

    # 5. 0xd843d0 の out+8 への書込み (成功経路) と、その out (rdx) の保存
    ins = disasm(0xD843D0, 0xD84510)
    check(any(i.address == 0xD843E0 and i.op_str == "rsi, rdx" for i in ins),
          "0xd843d0 は out (rdx) を rsi に保存する (0xd843e0)")
    check(any(i.address == 0xD8441A and i.op_str == "rbx, rax" for i in ins),
          "0xd843d0 の obj (rbx) は 0xd841e0 の戻り値 (0xd8441a)")
    check(any(i.address == 0xD844C2 and i.op_str == "rax, qword ptr [rbx + 0x10]" for i in ins),
          "0xd843d0 は 0xd844c2 で [obj+0x10] を読む")
    out8 = [i for i in stores(ins) if i.op_str.split(", ")[0] == "qword ptr [rsi + 8]"]
    check(len(out8) == 1 and out8[0].address == 0xD844C6 and out8[0].op_str == "qword ptr [rsi + 8], rax",
          "0xd843d0 の out+8 ([rsi+8]) への store は 0xd844c6 の 1 箇所 (値は [obj+0x10])")

    # 6. 0xd84740 (3 整数引数の wrapper) が 0xd843d0 を out (rdx) 付きで呼ぶ
    ins = disasm(0xD84740, 0xD847A6)
    check(any(i.address == 0xD84745 and i.op_str == "rbx, rdx" for i in ins)
          and any(i.address == 0xD84798 and direct(i) == 0xD843D0 for i in ins),
          "0xd84740 は rdx (out) を保存して 0xd843d0 を呼ぶ (0xd84798)")
    callers = []
    for m in re.finditer(b"\xe8", raw):
        off = m.start()
        va = o2v(off)
        if va is None or off + 5 > len(raw):
            continue
        if va + 5 + struct.unpack_from("<i", raw, off + 1)[0] == 0xD84740:
            callers.append(va)
    check(sorted(callers) == [0xD58E74, 0xD69F74, 0xD7FAC9, 0xD7FC2F],
          f"call 0xd84740 の呼出し元は 4 箇所 (実測 {[hex(c) for c in sorted(callers)]})。scrollWindow (0xd6d300) を含まない")

    # 7. scrollWindow の handler 0xd6d300: 0xd843d0 を out=[rbp+0x88] で呼び、out+0 だけを読む
    ins = disasm(0xD6D300, 0xD6D408)
    check(any(i.address == 0xD6D377 and i.mnemonic == "lea" and i.op_str == "rdx, [rbp + 0x88]" for i in ins),
          "0xd6d300 は out = [rbp+0x88] を rdx に渡す (0xd6d377)")
    check(any(i.address == 0xD6D3CC and direct(i) == 0xD843D0 for i in ins),
          "0xd6d300 は 0xd843d0 を直接呼ぶ (0xd6d3cc)")
    check(any(i.address == 0xD6D3D1 and i.op_str == "rax, qword ptr [rbp + 0x88]" for i in ins),
          "0xd6d300 は 0xd843d0 の後に out+0 ([rbp+0x88]) だけを読む (0xd6d3d1)")
    check(any(i.address == 0xD6D3DA and direct(i) == 0xD82C20 for i in ins),
          "0xd6d300 は out+0 の status を 0xd82c20 へ渡す (0xd6d3da)")
    check(not any("rbp + 0x90]" in i.op_str for i in ins),
          "0xd6d300 は out+8 ([rbp+0x90]) に触れない")

    # 8. 0x415610 の型記述子 (0xd81740 → 0xd81748)
    rtti = qword_at(0xD81740)
    check(rtti == 0xD81748, f"[0xd81740] = {rtti:#x} = 0xd81748 (型情報へのポインタを格納するスロット)")
    fo = v2o(rtti)
    name_len = raw[fo + 1]
    name = raw[fo + 2:fo + 2 + name_len].decode()
    p = fo + 2 + name_len
    recsize, managed = struct.unpack_from("<II", raw, p)
    tref, fldoff = struct.unpack_from("<QQ", raw, p + 8)
    check(raw[fo] == 14 and name == "TPyCallSynchronizedResult" and recsize == 0x18 and managed == 1
          and fldoff == 0x10,
          f"0xd81748: tkRecord (14)・{name}・RecSize {recsize:#x}・managed {managed} 件・FldOffset {fldoff:#x}")
    ti = v2o(qword_at(tref))
    check(raw[ti] == 18 and raw[ti + 2:ti + 2 + raw[ti + 1]] == b"string",
          f"managed 1 件の TypeRef {tref:#x} (PPTypeInfo) は string (tkUString)")

    # 9. 0xd82c20 の分岐 (status の値域ごと)
    ins = disasm(0xD82C20, 0xD82DDB)
    check(any(i.address == 0xD82C3A and i.mnemonic == "jne" and direct(i) == 0xD82C55 for i in ins),
          "0xd82c20: status ≠ 0 は 0xd82c55 へ (0xd82c3a jne)")
    check(any(i.address == 0xD82C48 and i.mnemonic == "je" and direct(i) == 0xD82C55 for i in ins)
          and any(i.address == 0xD82C4A and i.op_str == "eax, eax" for i in ins),
          "0xd82c20: status == 0 で PyErr_Occurred が非 NULL なら NULL (0xd82c4a)、NULL なら 0xd82c55")
    check(any(i.address == 0xD82C5A and i.mnemonic == "jl" and direct(i) == 0xD82C6A for i in ins),
          "0xd82c20: 0xd82c55 で status < 0 は 0xd82c6a へ (0xd82c5a jl)")
    check(any(i.address == 0xD82C5C and direct(i) == 0xC38BC0 for i in ins),
          "0xd82c20: status ≥ 0 の既定経路は 0xc38bc0 (Py_None) を呼ぶ (0xd82c5c)")

    if FAIL:
        print(f"FAIL {len(FAIL)} 件")
        sys.exit(1)
    print("PASS")


if __name__ == "__main__":
    main()
