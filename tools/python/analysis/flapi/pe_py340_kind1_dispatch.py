#!/usr/bin/env python3
"""0x478420 (表 0x13b2c28 の kind 1 の関数) の分岐入力と戻り値 P の対応を PE から確定する (PY-340 / #4559)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py340_kind1_dispatch.py

検査 (1 つでも外れたら FAIL・終了 1):
- kind 1 行 (0x13b2da8) の fn = 0x478420・flags = 0x2。
- 0x478420 の分岐入力 v = [typeinfo + nameLen + 2] (1 byte)。命令列から
  v ∈ {0,1} → P0 (0x13b21e0) / v ∈ {2,3} → P1 (0x13b21e8) / v ∈ {4,5} → P2 (0x13b21f0) / v ≥ 6 → エラー経路 (0x409730, cl=4) で 0。
- P0・P1・P2 はいずれも静的 .data にあり、その先頭 qword も .data (vtable)。P2 の vtable は 0x13b21b8。
- 分岐入力の byte を持つ typeinfo は read-only な .text にあり、Integer 以外の kind 1 typeinfo
  (ShortInt・SmallInt・Byte・Word・Cardinal・HRESULT・TColor 等) の v が上の対応と一致する。

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> extracted/block00031_PE.bin
"""
import os
import struct
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
ROW_TBL = 0x13B2C28
KIND_STRIDE = 0x2E * 8
KIND1_ROW = ROW_TBL + KIND_STRIDE + 2 * 8
DISPATCH = 0x478420
ERR_CALL = 0x47845C
ERR_FN = 0x409730
INTEGER_TI_PTR = 0x4010B8
P_OBJ = {"P0": 0x13B21E0, "P1": 0x13B21E8, "P2": 0x13B21F0}
P_VT_P2 = 0x13B21B8
JUMP_TO = {"P0": 0x478441, "P1": 0x47844A, "P2": 0x478453}
# (typeinfo 名, 期待する分岐先)。TOrdType 順 (ShortInt 0・Byte 1・SmallInt 2・Word 3・Integer 4・Cardinal 5) と、
# Integer 以外の kind 1 typeinfo を含める。
SAMPLES = [
    ("ShortInt", "P0"), ("Byte", "P0"), ("SmallInt", "P1"), ("Word", "P1"),
    ("Integer", "P2"), ("Cardinal", "P2"), ("HRESULT", "P2"), ("TColor", "P2"),
    ("TCursor", "P1"), ("TOleEnum", "P2"), ("TFontCharset", "P0"), ("TModalResult", "P2"),
]


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = [(s.VirtualAddress, max(s.Misc_VirtualSize, s.SizeOfRawData), s.PointerToRawData,
             s.Name.rstrip(b"\0").decode(), s.Characteristics) for s in pe.sections]

    def locate(va):
        rva = va - base
        for vaddr, size, praw, name, ch in secs:
            if vaddr <= rva < vaddr + size:
                return name, ch, praw + (rva - vaddr)
        sys.exit(f"VA {va:#x} が section 外")

    def fo(va):
        return locate(va)[2]

    def q(va):
        return struct.unpack_from("<Q", raw, fo(va))[0]

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True

    def disasm(va, n):
        return [(i.address, i.mnemonic, i.op_str)
                for i, _ in zip(md.disasm(raw[fo(va):fo(va) + n * 16], va), range(n))]

    fails = []

    def check(ok, msg):
        print(("PASS " if ok else "FAIL ") + msg)
        if not ok:
            fails.append(msg)

    row_fn = struct.unpack_from("<Q", raw, fo(KIND1_ROW + 8))[0]
    row_flags = raw[fo(KIND1_ROW)]
    check(row_fn == DISPATCH and row_flags == 0x2,
          f"kind 1 行 {KIND1_ROW:#x}: fn = {row_fn:#x} (期待 {DISPATCH:#x})・flags = {row_flags:#x} (期待 0x2)")

    seq = [(m, s) for _, m, s in disasm(DISPATCH, 12)]
    want = [("movzx", "rax, byte ptr [rcx + 1]"), ("movzx", "rax, byte ptr [rcx + rax + 2]"),
            ("cmp", "al, 2"), ("jb", f"{JUMP_TO['P0']:#x}"), ("sub", "al, 2"), ("cmp", "al, 2"),
            ("jb", f"{JUMP_TO['P1']:#x}"), ("sub", "al, 2"), ("cmp", "al, 2"), ("jae", f"{ERR_CALL:#x}"),
            ("jmp", f"{JUMP_TO['P2']:#x}")]
    check(seq[1:12] == want, f"{DISPATCH:#x} の分岐列が v を 2 刻みで比較する (実際: {seq[1:12]})")

    for key, va in JUMP_TO.items():
        ins = next(capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64).disasm(raw[fo(va):fo(va) + 16], va))
        check(ins.mnemonic == "lea" and "rip" in ins.op_str and
              int(ins.op_str.split("+ ")[1].split("]")[0], 16) + ins.address + ins.size == P_OBJ[key],
              f"{va:#x} の lea が {key} = {P_OBJ[key]:#x} を返す ({ins.mnemonic} {ins.op_str})")

    err = disasm(ERR_CALL, 2)
    check(err[0][1:] == ("mov", "cl, 4") and err[1][1:] == ("call", f"{ERR_FN:#x}"),
          f"{ERR_CALL:#x} は cl=4 で {ERR_FN:#x} を呼ぶ (v ≥ 6 のエラー経路)")

    for key, va in P_OBJ.items():
        name, _, _ = locate(va)
        check(name == ".data", f"{key} {va:#x} は {name} (静的)")
        vt = q(va)
        check(locate(vt)[0] == ".data", f"{key} の先頭 qword {vt:#x} は .data (vtable)")
    check(q(P_OBJ["P2"]) == P_VT_P2, f"P2 の先頭 qword = {P_VT_P2:#x}")

    def find_ti(name):
        pat = b"\x01" + bytes([len(name)]) + name.encode()
        off = raw.find(pat)
        if off < 0:
            return None
        for vaddr, size, praw, sname, ch in secs:
            if praw <= off < praw + size:
                return base + vaddr + (off - praw), sname, ch
        return None

    def bucket(v):
        if v < 2:
            return "P0"
        if v < 4:
            return "P1"
        if v < 6:
            return "P2"
        return None

    int_ti = q(INTEGER_TI_PTR)
    sname, ch, _ = locate(int_ti)
    check(sname == ".text" and not (ch & 0x80000000),
          f"Integer typeinfo {int_ti:#x} は {sname} (特性 {ch:#x}・WRITE 無し)")

    for name, want_key in SAMPLES:
        found = find_ti(name)
        if found is None:
            check(False, f"typeinfo {name} が見つからない")
            continue
        ti, sname, ch = found
        v = raw[fo(ti) + len(name) + 2]
        ok = bucket(v) == want_key and sname == ".text" and not (ch & 0x80000000)
        check(ok, f"typeinfo {name} {ti:#x}: v = {v} → {bucket(v)} (期待 {want_key})・{sname} 読取専用")

    print(f"summary: {len(fails)} FAIL")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
