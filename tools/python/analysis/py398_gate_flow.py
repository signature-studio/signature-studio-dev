#!/usr/bin/env python3
"""PY-398 (#4859): gate *(0x15e1890) の書込み分岐・-1 経路の分岐構造・0x12f9ed0 の定義を PE から検証する。

  FL_WIN64_DIR=<展開先> python3 analysis/py398_gate_flow.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
方式: objdump -d -M intel の線形走査 (py392_flag_runtime.py と同じ) と .data / .bss の直接読出し。
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


# gate ポインタ: *(0x15e1890) は .data の pointer 0x13e7628。その指す先の初期値は 0。
gate = struct.unpack("<Q", read_va(0x15E1890, 8))[0]
check(f"gate pointer = 0x13e7628 (値 {gate:#x})", gate == 0x13E7628)
check("gate の指す先の初期値 = 0 (.data)", read_va(gate, 1) == b"\x00")

# 0x1046d83: gate が 1 なら 0x104cc72 へ抜ける (-1 経路に入らない)。
check("0x1046d83: rax = [0x15e1890]", text(0x1046D83) == "mov    rax,QWORD PTR [rip+0x59ab06]")
check("0x1046d8a: cmp byte [gate],0", text(0x1046D8A) == "cmp    BYTE PTR [rax],0x0")
check("0x1046d8d: gate!=0 で 0x104cc72", text(0x1046D8D) == "jne    0x104cc72")

# gate 書込み 0x11c761c は 0x11c71b0 の内側。直前は 0x976f40 の呼出し。
check("0x11c761c: mov byte [gate],1", text(0x11C761C) == "mov    BYTE PTR [rax],0x1")
check("0x11c7610: 直前の呼出し 0x976f40", text(0x11C7610) == "call   0x976f40")

# 書込みは 0x11c7507 の分岐で飛ばされ得る: [rbp+0xdc] == 0 なら 0x11c7604 へ (store を経由しない)。
check("0x11c7500: cmp [rbp+0xdc],0", text(0x11C7500) == "cmp    DWORD PTR [rbp+0xdc],0x0")
check("0x11c7507: je 0x11c7604 (store を飛ばす分岐)", text(0x11C7507) == "je     0x11c7604")
check("0x11c7604: 飛び先 (store を経由せず 0x15e4790 の読出しへ)", text(0x11C7604) == "mov    rax,QWORD PTR [rip+0x41d185]")
check("0x11c74d3: [rbp+0xdc] = (([rbp+0xd8] | [rbp+0xd4]) & 1) - 1 の結果を格納", text(0x11C74D3) == "mov    DWORD PTR [rbp+0xdc],eax"
      and text(0x11C74D0) == "sub    eax,0x1" and text(0x11C74CD) == "and    eax,0x1")

# 0x11c71b0 の呼出しは 0x11c88d3 の 1 件。直前の cmp [0x16bcc00],0 の結果で条件付き。
check("0x11c88c2: cmp [0x16bcc00],0", text(0x11C88C2) == "cmp    QWORD PTR [rip+0x4f4336],0x0")
check("0x11c88ca: je 0x11c88d8 (0 なら呼ばない)", text(0x11C88CA) == "je     0x11c88d8")
check("0x11c88d3: call 0x11c71b0", text(0x11C88D3) == "call   0x11c71b0")

# setter 0x1262970 は gate を 1 にする (書込みは 2 箇所目)。
check("0x1262977: setter mov byte [gate],1", text(0x1262977) == "mov    BYTE PTR [rax],0x1")

# 0x12f9ed0: 0x196eb60 の配列長 (qword [ptr-8]) を返す。0 ポインタなら 0。loop の上限はこの値。
check("0x12f9ed0: rax = [0x196eb60]", text(0x12F9ED0) == "mov    rax,QWORD PTR [rip+0x674c89]")
check("0x12f9edc: rax = [rax-8] (長さ)", text(0x12F9EDC) == "mov    rax,QWORD PTR [rax-0x8]")
check("0x12f9ee0: ret", text(0x12F9EE0) == "ret")

# 0xffac50 の loop: 0x12f9ed0 の戻り値 (eax) を回し、0xffaea0 の真偽で esi=1。
check("0xffac8d: call 0x12f9ed0", text(0xFFAC8D) == "call   0x12f9ed0")
check("0xffac94: r13d = eax (長さ)", text(0xFFAC94) == "mov    r13d,eax")
check("0xffacae: call 0xffaea0 (要素判定)", text(0xFFACAE) == "call   0xffaea0")
check("0xffacb5: 負なら次の要素へ (jl 0xffacbc)", text(0xFFACB5) == "jl     0xffacbc")
check("0xffacb7: 非負なら esi=1 で抜ける", text(0xFFACB7) == "mov    sil,0x1")

# 0x1047158 以降: 0x663bf0 が負なら -1 経路 (0x1047182) で [rbp+0x55c] = -1。
check("0x104714b: call 0x663bf0", text(0x104714B) == "call   0x663bf0")
check("0x1047152: 非負なら 0x1047288 へ", text(0x1047152) == "jge    0x1047288")
check("0x1047193: [rbp+0x55c] < 0 で 0x10471fe", text(0x1047193) == "jl     0x10471fe")
check("0x10471b4: 0xffac50 が偽なら 0x10471fe", text(0x10471B4) == "je     0x10471fe")
check("0x10471c4: eventId & 0xffff != 8 なら 0x10471fe", text(0x10471C4) == "jne    0x10471fe")

# -1 経路の枝 (0x10471b6〜0x10471f9) の内容: 0x423980 → 0x8da350 → 0x9635b0 を呼んで 0x104cc72 へ。
check("0x10471c6: rcx = [0x15e2508]", text(0x10471C6) == "mov    rcx,QWORD PTR [rip+0x59b33b]")
check("0x10471cd: call 0x423980", text(0x10471CD) == "call   0x423980")
check("0x10471e0: call 0x8da350", text(0x10471E0) == "call   0x8da350")
check("0x10471f4: call 0x9635b0", text(0x10471F4) == "call   0x9635b0")
check("0x10471f9: jmp 0x104cc72", text(0x10471F9) == "jmp    0x104cc72")

# [0x15e2878] (gate 別フラグ) は 0x104711f で読まれ、0 なら 0x1047294 へ飛ぶ。
check("0x1047126: cmp byte [rax],0 (rax=[0x15e2878])", text(0x1047126) == "cmp    BYTE PTR [rax],0x0")
check("0x1047129: je 0x1047294", text(0x1047129) == "je     0x1047294")

print("summary: gate を 1 にする書込みは 2 箇所 (0x11c761c は 0x11c7507 の分岐で飛ばされ得る・0x1262970 は setter)。")
print("summary: 0x12f9ed0 は 0x196eb60 の配列長を返す。0xffac50 の loop 上限はその長さ。")
sys.exit(0)
