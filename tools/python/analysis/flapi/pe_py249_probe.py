#!/usr/bin/env python3
"""PY-249 (#3769) の解析補助: 選択ゲート 0xffac20 の *p (スロット P が指す dword) の書込み元と、
フラグ +0x32c の書込み 9 箇所の基底の由来を出す。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py249_probe.py [窓の命令数(既定 28)]

出力:
- 節 S (静的): PE ファイル上の初期値 (*p・状態バイト S の指す先・チャネル表 T1・mask 0x11e8604)。
- 節 A: *p への dword 書込み候補 (pe_slot_writers.py 0x15e3a60 0 の 6 件)。各書込みの基底レジスタを
  直前の `mov reg, [rip+X]` まで遡って解決し、そのスロット VA を出す。P 以外を読んでいれば偽陽性 (0xfffa00 は
  0x15e0bd0 を読むので除外)。
- 節 B: +0x32c への byte 書込み 9 箇所。基底を `call 0xfe8bb0(*T, idx)` (チャネル表の要素取得) か
  RIP 相対スロットか、フレーム (`[rbp+..]`) 由来かで分類し、所属関数の先頭からの命令列を出す。

線形走査で関数の先頭を推定する (直前が int3 パディング)。推定が外れると窓が途中から始まる (REPORT の限界に記載)。
"""
import os
import re
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")

P_SLOT = 0x15E3A60  # *(P_SLOT) = p。*p は選択ゲート 0xffac20 の比較対象
S_SLOT = 0x15E4B08  # *(S_SLOT) = 状態バイト S の指す先
T1 = 0x15E2218  # *(T1) = チャネル表のコンテナ。fe8bb0(*T1, idx) が channel item を返す
MASK_0X11E84A0 = 0x11E8604  # 0xea6b30 の呼出し gate の bit mask (item+0x160 ∈ {4,5})

# *p への dword 書込み候補 (pe_slot_writers.py 0x15e3a60 0 の 6 件)
P_WRITERS = [0xFFFA00, 0x103B781, 0x103B9EC, 0x103BA02, 0x103BE3A, 0x103C01C]
# +0x32c への byte 書込み (pe_scan_store.py 0x32c の 9 件。setter 0xff8abe を除く)
FLAG_WRITERS = [0x6E9F4D, 0x82BBF4, 0x82BCB5, 0x82BCE0, 0xFE96ED, 0x11F8889, 0x11F88E9, 0x11F8981, 0x11F8A43]


class Img:
    def __init__(self):
        self.raw = open(PE, "rb").read()
        self.pe = pefile.PE(data=self.raw, fast_load=True)
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.text = next(s for s in self.pe.sections if s.Name.rstrip(b"\0") == b".text")
        self.va0 = self.base + self.text.VirtualAddress
        self.n = min(self.text.Misc_VirtualSize, self.text.SizeOfRawData)
        self.data = self.raw[self.text.PointerToRawData:self.text.PointerToRawData + self.n]

    def read(self, va, size):
        for s in self.pe.sections:
            lo = self.base + s.VirtualAddress
            if lo <= va < lo + max(s.Misc_VirtualSize, s.SizeOfRawData):
                off = s.PointerToRawData + (va - lo)
                return int.from_bytes(self.raw[off:off + size], "little")
        return None

    def func_start(self, va):
        off = va - self.va0
        i = off
        while i > 0 and self.data[i - 1] != 0xCC:
            i -= 1
        while i < off and self.data[i] == 0xCC:
            i += 1
        return self.va0 + i


def disasm_from(md, img, start, end):
    off = start - img.va0
    out = []
    for ins in md.disasm(img.data[off:off + (end - start) + 16], start):
        if ins.address >= end:
            break
        out.append((ins.address, ins.size, f"{ins.mnemonic} {ins.op_str}"))
    return out


RIP_LOAD = re.compile(r"^mov (r\w+), qword ptr \[rip \+ (0x[0-9a-f]+)\]$")


def slot_of(lines, idx, reg):
    """lines[idx] より前で reg を最後に読んだ由来を返す。
    `mov reg, [rip+X]` なら X の VA。`call 0xfe8bb0` の戻り値 (チャネル表の要素) なら、その引数のコンテナ
    スロット T を `fe8bb0(*T, idx)` の形で返す。どちらでも無ければ None。"""
    for j in range(idx - 1, max(-1, idx - 40), -1):
        a, sz, s = lines[j]
        m = RIP_LOAD.match(s)
        if m and m.group(1) == reg:
            return a + sz + int(m.group(2), 16)
        if s == "call 0xfe8bb0" and reg in ("rax", "rdi"):
            for k in range(j - 1, max(-1, j - 12), -1):
                a2, sz2, s2 = lines[k]
                m2 = RIP_LOAD.match(s2)
                if m2 and m2.group(1) in ("rcx", "rax"):
                    return f"fe8bb0(*{hex(a2 + sz2 + int(m2.group(2), 16))})"
            return "fe8bb0(?)"
        m3 = re.match(r"^mov (r\w+), (r\w+)$", s)
        if m3 and m3.group(1) == reg:
            return slot_of(lines, j, m3.group(2))
        m4 = re.match(r"^mov (r\w+), qword ptr \[rbp \+ (0x[0-9a-f]+)\]$", s)
        if m4 and m4.group(1) == reg:
            return f"frame[rbp+{m4.group(2)}]"
        if s.startswith("call ") or s.startswith(f"mov {reg},"):
            return None
    return None


def show(title, md, img, targets, before, after):
    print(f"== {title}")
    for t in targets:
        fs = img.func_start(t)
        if t - fs > 0x400:
            fs = t - 0x100
        lines = disasm_from(md, img, fs, t + after)
        hit = [i for i, (a, _, _) in enumerate(lines) if a == t]
        if not hit:
            print(f"-- site {hex(t)}: 窓に無い")
            continue
        h = hit[0]
        m = re.match(r"^mov (?:dword|byte) ptr \[(r\w+)", lines[h][2])
        base = m.group(1) if m else "?"
        slot = slot_of(lines, h, base)
        cut = max(0, h - before)
        src = slot if isinstance(slot, str) or slot is None else hex(slot)
        print(f"-- site {hex(t)} (窓の先頭 {hex(fs)}) 基底 {base} の由来: {src or 'なし'}")
        for a, _, s in lines[cut:h + after // 2 + 1]:
            mark = " <== " if a == t else "     "
            print(f"{hex(a)}{mark}{s}")


def main():
    before = int(sys.argv[1]) if len(sys.argv) > 1 else 28
    img = Img()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    print("== S: 静的初期値 (PE ファイル上。実行時の値ではない)")
    print(f"*p      = dword[{hex(img.read(P_SLOT, 8))}] -> p; dword[p] = {img.read(img.read(P_SLOT, 8), 4)}")
    q = img.read(S_SLOT, 8)
    print(f"S 指す先 = qword[{hex(S_SLOT)}] = {hex(q)}; byte[S] = {img.read(q, 1)}")
    t = img.read(T1, 8)
    print(f"T1      = qword[{hex(T1)}] = {hex(t)}; qword[*T1] の +0x10 は要素数 (実行時)")
    print(f"mask    = byte[{hex(MASK_0X11E84A0)}] = {hex(img.read(MASK_0X11E84A0, 1))}")
    show("A: *p への dword 書込み候補 (スロット 0x15e3a60)", md, img, P_WRITERS, before, 6)
    show("B: +0x32c への byte 書込み (9 箇所)", md, img, FLAG_WRITERS, before, 6)


if __name__ == "__main__":
    main()
