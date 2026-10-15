#!/usr/bin/env python3
"""ui 操作 27 関数の戻り値と引数型 (PY-141 / #3034) の PE 上の根拠を検算する解析補助 (読取りのみ)。

検算する事実 (結論は tools/python/REPORT_PY141.md):
  1. 0xd84680 の書込みは out+0 (`[rbx]`) だけ。out+8 (`[rbx+8]`) への書込みは無い。
  2. ui.selectWindow (0xd6c140) の out+8 (`[rbp+0x58]`) への書込みは無い (読むだけ)。
  3. loader (0xc39600〜0xc3a000) が GetProcAddress で読む名前と格納変数の対応。
     0x15e4280 → 0x16b8298 → PyLong_FromLong、0xc38bc0 → 0x16b82e0 → _Py_NoneStruct、
     0x15e30c8 → 0x16b8470 → PyErr_Occurred、0x15e1e58 → 0x16b82f0 → PyArg_ParseTuple。

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

    def disasm(start, end):
        return list(md.disasm(raw[v2o(start):v2o(start) + end - start], start))

    def rip_target(i):
        m = re.search(r"\[rip ([+-]) (0x[0-9a-f]+)\]", i.op_str)
        if not m:
            return None
        d = int(m.group(2), 16)
        return i.address + i.size + (d if m.group(1) == "+" else -d)

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

    if FAIL:
        print(f"FAIL {len(FAIL)} 件")
        sys.exit(1)
    print("PASS")


if __name__ == "__main__":
    main()
