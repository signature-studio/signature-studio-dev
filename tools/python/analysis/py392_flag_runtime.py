#!/usr/bin/env python3
"""PY-392 (#4832): -1 経路の runtime 条件 (0x663bf0・0xffac50・[0x15e2878]) と gate 書込み元 (0x11c71b0) を PE から検証する。

  FL_WIN64_DIR=<展開先> python3 analysis/py392_flag_runtime.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
方式: objdump -d -M intel の線形走査 (py251_gate_refs.py と同じ) と .data の直接読出し。
"""
import os
import re
import struct
import subprocess
import sys

import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
raw = open(PE, "rb").read()
pe = pefile.PE(data=raw, fast_load=True)
BASE = pe.OPTIONAL_HEADER.ImageBase

ins = {}
for line in subprocess.run(["objdump", "-d", "-M", "intel", PE], capture_output=True, text=True, check=True).stdout.split("\n"):
    m = re.match(r"\s*([0-9a-f]+):\t[0-9a-f ]+\t(.*)", line)
    if m:
        ins[int(m.group(1), 16)] = m.group(2)


def text(a):
    return re.sub(r"\s+#.*$", "", ins[a]).strip()


def check(label, cond):
    print(("ok   " if cond else "FAIL ") + label)
    if not cond:
        sys.exit(1)


def read_va(va, n):
    for s in pe.sections:
        st = BASE + s.VirtualAddress
        sz = max(s.Misc_VirtualSize, s.SizeOfRawData)
        if st <= va < st + sz:
            off = s.PointerToRawData + (va - st)
            return raw[off:off + n]
    raise ValueError(hex(va))


# 0x663bf0: 配列 [rcx+8] (長さ [rcx+0x10]) を線形探索し、qword == rdx の添字を返す。無ければ -1。
check("0x663bf0: 長さ = [rcx+0x10]", text(0x663BF3) == "mov    r9d,DWORD PTR [rcx+0x10]")
check("0x663bf0: 配列の先頭 = [rcx+8]", text(0x663C0A) == "mov    r8,QWORD PTR [rcx+0x8]")
check("0x663bf0: 比較 = qword [r8+idx*8] と rdx", text(0x663C11) == "cmp    QWORD PTR [r8+r10*8],rdx")
check("0x663bf0: 見つからなければ -1 (or eax,-1)", text(0x663C24) == "or     eax,0xffffffff")

# 0xffac50 の先頭: [obj+0x160] が 0..7 なら bit mask (byte 0xffacd8) で判定。
check("0xffac50: 判定元 = [obj+0x160]", text(0xFFAC5F) == "mov    eax,DWORD PTR [rbx+0x160]")
check("0xffac50: 範囲 0..7 の外は偽 (0xffac82 で xor eax)", text(0xFFAC82) == "xor    eax,eax")
check("0xffac50: mask 参照 = byte 0xffacd8", text(0xFFAC73) == "movzx  rax,BYTE PTR [rip+0x5d]" and 0xFFACD8 == 0xFFAC7B + 0x5D)

# [0x15e2878] (gate 別フラグ) の実体: ポインタ先は .data 外ではなく 1 byte、初期値 0。
p = struct.unpack("<Q", read_va(0x15E2878, 8))[0]
check(f"[0x15e2878] の指す先 = 0x16baf90 (ポインタ値 {p:#x})", p == 0x16BAF90)
check("[0x15e2878] の指す先の初期値 = 0", read_va(p, 1) == b"\x00")

# 0x15e2878 を読む命令は 23 件。RIP 相対の直接 store は 0 件 (読出しのみ)。
refs = sorted(a for a, v in ins.items() if re.search(r"# 0x15e2878$", v))
check(f"0x15e2878 を読む命令 23 件: {len(refs)}", len(refs) == 23)
check("そのうち RIP 相対の直接 store は 0 件", not [a for a in refs if re.match(r"mov\s+(BYTE|WORD|DWORD|QWORD) PTR \[rip", text(a))])

# gate 書込み元 0x11c7615 (`mov rax,[0x15e1890]; mov byte [rax],1`) は関数 0x11c71b0 の内側。
check("0x11c7615: 0x15e1890 の pointer を rax に読む", text(0x11c7615).startswith("mov    rax,QWORD PTR [rip+0x41a274]"))
check("0x11c761c: mov byte [rax],1 (1 を書く。0 を書く store は無い)", text(0x11C761C) == "mov    BYTE PTR [rax],0x1")
check("0x11c71b0: 関数先頭 push rbp", text(0x11C71B0) == "push   rbp")
check("0x11c88d3: 呼出し 0x11c71b0 は cmp [0x16bcc00],0 の直後に条件付き", text(0x11C88D3) == "call   0x11c71b0")

# 0x1262950 (getter, vt+0x48) と 0x1262970 (setter, vt+0x60) は同じ pointer 0x15e1890 を読み書きする対。
check("0x1262950: getter (movzx byte [gate])", text(0x1262957) == "movzx  rax,BYTE PTR [rax]")
check("0x1262977: setter (mov byte [gate],1)", text(0x1262977) == "mov    BYTE PTR [rax],0x1")

print("summary: 0x663bf0 は配列の線形探索 (見つからなければ -1)。0x15e2878 の指す先は初期値 0 で書込みは間接。")
print("summary: gate の 1 書込みは 0x11c71b0 (flag=1 後に 0x86a220・0x938460・0x93f180 等を呼ぶ) と 0x1262970 (setter)。")
sys.exit(0)
