#!/usr/bin/env python3
"""PY-336 (#4526): patterns 選択 setter 本体 (0xea6e50・0xea6a00・0xea7280・0xea7420・0xea6730・0xe4e7f0) の逆アセンブル事実を出し、期待する命令列を検査する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py336_probe.py [--negctl]

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
検査: 期待する命令の部分文字列が無ければ exit 1。--negctl は選択 flag の書込みを 1 つ壊し、exit 1 になることを確かめる。
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
N = 0x400

# (関数 VA, 名前, 期待する命令の部分文字列 (順不同で含まれること))
EXPECT = [
    (0xEA6E50, "setSelected", [
        "cmp rcx, rax", "jg 0xea7248",          # idx は 0..count-1 の外なら no-op
        "je 0xea7248",                          # 既に選択済みなら no-op
        "call 0x417fc0", "call 0x4133f0",       # 配列を 1 つ伸ばし、値を代入
        "call 0xbb1990",                        # item から値を作る
        "call qword ptr [rbx + 0x178]",         # 変更の通知 (推定)
        "cmp byte ptr [rax + 0x6c4], 0",        # モードで経路を分ける
        "call 0x12d8af0", "call 0xdce130",
        "mov byte ptr [rax + 0x6f4], 1",
        "call 0xfe8bb0", "call 0x11e8720", "call 0x11e84a0", "call 0xffe410",
    ]),
    (0xEA6A00, "clearSelection", [
        "call 0x418190",                        # 配列を空にする
        "test sil, sil", "call qword ptr [rbx + 0x178]",
    ]),
    (0xEA7280, "deselectOne", [
        "cmp byte ptr [rbx + 0x6c4], 0",
        "call 0x417fc0",                        # 配列を 1 つ縮める
        "call 0xea75a0", "call 0x12d8af0", "call 0xea66b0",
        "call 0xff8a90", "call 0xfe8bb0",
        "call qword ptr [r14 + 0x178]",
    ]),
    (0xEA7420, "isInSelection", [
        "cmp dword ptr [r9 + r11*4], edx",      # 要素の id と比較
        "lea r11, [r11 + r11*2]",               # 要素幅 12 バイト
        "mov al, 1",
    ]),
    (0xEA6730, "endPreview", [
        "cmp byte ptr [rbx + 0x6f5], 0",
        "mov byte ptr [rbx + 0x6f5], 0",
        "call qword ptr [rsi + 0x170]",
        "call 0x11ca4e0", "call 0x11ca5f0",
    ]),
    (0xE4E7F0, "beginPreview", [
        "mov byte ptr [rbx + 0x6f5], 1",
        "mov dword ptr [rbx + 0x6fc], edx",
        "call qword ptr [rsi + 0x1f0]",
        "call 0xff5120", "call 0x737640", "call 0x423980",
    ]),
]


def load():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    return raw, pe.OPTIONAL_HEADER.ImageBase, pe.sections


def to_off(va, base, secs):
    rva = va - base
    for s in secs:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.PointerToRawData + (rva - s.VirtualAddress)
    sys.exit("VA が section 外: %#x" % va)


def disasm(raw, base, secs, va, n):
    off = to_off(va, base, secs)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    out = []
    for i, ins in enumerate(md.disasm(raw[off:off + n * 16], va)):
        if i >= n:
            break
        out.append("%s %s %s" % (hex(ins.address), ins.mnemonic, ins.op_str))
    return out


def main():
    neg = "--negctl" in sys.argv
    raw, base, secs = load()
    ok = True
    for va, name, want in EXPECT:
        lines = disasm(raw, base, secs, va, N)
        text = "\n".join(lines)
        if neg and name == "setSelected":
            want = [w.replace("mov byte ptr [rax + 0x6f4], 1", "mov byte ptr [rax + 0x6f4], 0") for w in want]
        missing = [w for w in want if w not in text]
        print("# %s %#x: %s" % (name, va, "OK" if not missing else "NG missing=%s" % missing))
        ok = ok and not missing
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
