#!/usr/bin/env python3
"""PY-183 (#3288): 0x1051720 の 10519c6 枝 (cur と new の表示枝) の副作用を PE 上で再照合する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py183_probe.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
REPORT_PY183.md の結論 (リテラル全文・呼出し辺・分岐条件・書込み先・ac の読出し) を PE から照合する。
終了 0 = 全 PASS。1 件でも FAIL なら終了 1。
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
RAW = open(PE, "rb").read()
PEF = pefile.PE(data=RAW, fast_load=True)
BASE = PEF.OPTIONAL_HEADER.ImageBase
SECS = [(s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData)
        for s in PEF.sections]
MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

LITERALS = [
    (0x1051BF0, " is waiting for pickup: "),
    (0x1051C30, "%.2f"),
    (0x1051C48, "%"),
    (0x1051C58, " "),
    (0x1051C68, " < "),
    (0x1051C7C, " > "),
    (0x1050650, " - "),
    (0x1050664, "Omni - "),
    (0x1050680, "Time stretch"),
    (0x1050978, "Unknown event"),
    (0x10509A0, " (#"),
    (0x10509B4, ")"),
    (0x11F13C4, "cents"),
    (0x11F13DC, "cent"),
    (0x11F13F4, "%d %s"),
    (0x11F140C, "+"),
]

CALLS = [
    (0x10519E0, "0x104f580"),
    (0x10519F7, "0x414c70"),
    (0x1051A11, "0x104d2b0"),
    (0x1051A27, "0x104d2b0"),
    (0x1051A3A, "0x414e70"),
    (0x1051A7E, "0x43dd60"),
    (0x1051A95, "0x414c70"),
    (0x1051AE0, "0x414da0"),
    (0x1051B25, "0x414da0"),
    (0x1051B3E, "0x11f1a20"),
    (0x1051965, "0x11f1a20"),
    (0x11F1A33, "0x4232e0"),
    (0x11F1A42, "0x4133f0"),
    (0x11F1A55, "0x423980"),
    (0x11F1A61, "0xbd68e0"),
    (0xBD691D, "0x666780"),
    (0x104D562, "0x11f12c0"),
    (0x104F7A9, "0x414c70"),
    (0x104FA21, "0x40fe90"),
    (0x104FA41, "0x8da350"),
    (0x11F134D, "0x43dd60"),
]

FAILS = []


def v2o(va):
    rva = va - BASE
    for vaddr, vsz, praw, rsz in SECS:
        if vaddr <= rva < vaddr + max(vsz, rsz):
            return praw + (rva - vaddr)
    return None


def ins_at(va):
    o = v2o(va)
    for ins in MD.disasm(RAW[o:o + 16], va, 1):
        return ins
    return None


def rip_target(va):
    ins = ins_at(va)
    if ins is None or "rip" not in ins.op_str:
        return None
    part = ins.op_str.split("rip")[1].strip()
    sign = 1 if part[0] == "+" else -1
    disp = int(part[1:].split("]")[0].strip(), 16)
    return ins.address + ins.size + sign * disp


def u16z(va, n=64):
    o = v2o(va)
    out = []
    for i in range(0, n * 2, 2):
        c = RAW[o + i:o + i + 2]
        if c == b"\x00\x00":
            break
        out.append(c.decode("utf-16-le"))
    return "".join(out)


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + ((" " + detail) if detail else ""))
    if not ok:
        FAILS.append(name)


def main():
    for va, want in LITERALS:
        got = u16z(va)
        check(f"literal {hex(va)} = {got!r}", got == want, f"(want {want!r})")
    for va, target in CALLS:
        ins = ins_at(va)
        ok = ins is not None and ins.mnemonic == "call" and ins.op_str == target
        check(f"call {hex(va)} -> {target}", ok, f"({ins.mnemonic} {ins.op_str})" if ins else "")
    check("0x1051720 bb 初期値 0xff", ins_at(0x105180D).op_str == "byte ptr [rbp + 0xbb], 0xff")
    check("0xff 経路の入口 (0x1051849 jne 0x1051909)", ins_at(0x1051849).op_str == "0x1051909")
    stores = []
    va = 0x1051909
    while va < 0x105193C:
        ins = ins_at(va)
        if "rbp + 0xac" in ins.op_str:
            stores.append((hex(va), ins.mnemonic, ins.op_str))
        va += ins.size
    check("0xff 経路 0x1051909..0x105193c に ac (rbp+0xac) の参照が無い (読出しは 0x105193c)",
          stores == [], str(stores))
    ins = ins_at(0x105193C)
    check("0x105193c が ac を読む (movsxd rcx, dword ptr [rbp + 0xac])",
          ins.mnemonic == "movsxd" and ins.op_str == "rcx, dword ptr [rbp + 0xac]")
    ac_writes = []
    va = 0x1051720
    while va < 0x1051B44:
        ins = ins_at(va)
        if ins.mnemonic == "mov" and ins.op_str.startswith("dword ptr [rbp + 0xac], "):
            ac_writes.append(hex(va))
        va += ins.size
    check("ac への書込みは bb==0 経路の 0x1051857 と 0x10518b2 の 2 箇所のみ",
          ac_writes == ["0x1051857", "0x10518b2"], str(ac_writes))
    check("0x105194b je 0x10519c6 (sign == ac で 10519c6 枝)",
          ins_at(0x105194B).op_str == "0x10519c6")
    check("0x1051a9a/0x1051aa0 cur<new の比較は int (cmp [rbp+0xbc], ebx; jge)",
          ins_at(0x1051A9A).op_str == "dword ptr [rbp + 0xbc], ebx"
          and ins_at(0x1051AA0).op_str == "0x1051ae7")
    check("0x1051a41 jne 0x1051a9a (wstring 不一致)", ins_at(0x1051A41).op_str == "0x1051a9a")
    check("0x11f1a20 の表示先 lea rcx -> 0x16bd1a0", rip_target(0x11F1A38) == 0x16BD1A0)
    check("0x11f1a20 のフラグ mov [rip] -> 0x16bd1a8 (sil)", rip_target(0x11F1A47) == 0x16BD1A8)
    check("0xbd68e0 フラグ表 lea -> 0x16b6dcc (cmp byte [r8+id])",
          rip_target(0xBD68E7) == 0x16B6DCC and rip_target(0xBD68F5) == 0x16B6DCC)
    check("0xbd68e0 イベント先 mov rax,[rip] -> 0x16b6e00", rip_target(0xBD6901) == 0x16B6E00)
    check("0x104f580 chan 範囲 cmp eax,0x10000000 / jb 0x104f75a",
          ins_at(0x104F714).op_str == "eax, 0x10000000" and ins_at(0x104F719).op_str == "0x104f75a")
    check("0x104f580 chan==0xfff 分岐 (jne 0x1050532)", ins_at(0x104F7B6).op_str == "0x1050532")
    check("0x104f580 低位 4 → 0x104fa17 (je 0x104fa17)", ins_at(0x104F842).op_str == "0x104fa17")
    check("0x104fa17 の Time stretch 判定 cmp [rbx+0x160], 5",
          ins_at(0x104FA2A).op_str == "dword ptr [rbx + 0x160], 5")
    check("0x104d2b0 低位 4 → 0x104d55b (je 0x104d55b)", ins_at(0x104D3AE).op_str == "0x104d55b")
    check("0x11f12c0 の |v|==1 分岐 (je 0x11f1305)", ins_at(0x11F12F1).op_str == "0x11f1305")
    check("0x11f12c0 の符号 '+' 分岐 (test eax,eax; jle 0x11f1370)",
          ins_at(0x11F1357).op_str == "0x11f1370")
    check("0x11f12c0 の書式呼出し第 4 引数 r9d=1", ins_at(0x11F1347).op_str == "r9d, 1")
    check("0x1050546 の判定が 0x1050540 の store と同番地 (0x16bb13c)",
          rip_target(0x1050540) == 0x16BB13C and rip_target(0x1050546) == 0x16BB13C)
    print(f"summary: {'OK' if not FAILS else str(len(FAILS)) + ' FAIL'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
