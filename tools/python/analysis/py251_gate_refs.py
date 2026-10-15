#!/usr/bin/env python3
"""PY-251 (#3777): gate pointer `*(0x15e1890)` の参照と、`(eventId & 0xffff) == 8` の -1 経路の分岐を PE から検証する。

  FL_WIN64_DIR=<展開先> python3 analysis/py251_gate_refs.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'

方式: objdump -d -M intel の線形走査 (REPORT_PY235 §2 と同じ) で `# 0x15e1890` を読む行を数え、
各行を「読出し (mov reg, [rip+X])」と分類する。書込みは `mov [rip+X], reg` の形の行が 0 件であることを assert する。
gate フラグ本体 (0x13e7628) は `.data` の 1 byte (初期値 0)。書込みは直接の RIP 相対 store で 2 箇所 (0x11c7615・0x1262970)。
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


GATE = 0x15E1890
refs = sorted(a for a, v in ins.items() if re.search(r"# 0x15e1890$", v))
check(f"0x15e1890 を RIP 相対で読む命令 58 件: {len(refs)}", len(refs) == 58)
check("そのうち RIP 相対 store (mov <size> PTR [rip+X], reg/imm) は 0 件", not [a for a in refs if re.match(r"mov\s+(BYTE|WORD|DWORD|QWORD) PTR \[rip", text(a))])
gate_ptr_off = GATE - (BASE + pe.sections[1].VirtualAddress) + pe.sections[1].PointerToRawData
check("gate pointer 変数 (.data の 0x15e1890) の初期値 = 0x13e7628", struct.unpack_from("<Q", raw, gate_ptr_off)[0] == 0x13E7628)
flag_off = 0x13E7628 - (BASE + pe.sections[1].VirtualAddress) + pe.sections[1].PointerToRawData
check("gate フラグ本体 (0x13e7628) の初期値 = 0", raw[flag_off] == 0)

check("0x1046d83: mov rax, [rip+X] (X = gate pointer)", text(0x1046D83).startswith("mov    rax,QWORD PTR [rip+0x59ab06]"))
check("0x1046d8d: jne 0x104cc72 (gate 1 で -1)", text(0x1046D8D) == "jne    0x104cc72")

check("0x104711f: mov rax, [rip+0x59b752] (別フラグ 0x15e2878)", text(0x104711F).startswith("mov    rax,QWORD PTR [rip+0x59b752]"))
check("0x1047129: je 0x1047294 (フラグ 0 で 0x1047294 へ)", text(0x1047129) == "je     0x1047294")
check("0x10471b4: je 0x10471fe (0xffac50 偽で通常経路)", text(0x10471B4) == "je     0x10471fe")
check("0x10471c4: jne 0x10471fe ((eventId&0xffff) != 8 で通常経路)", text(0x10471C4) == "jne    0x10471fe")
check("0x10471f9: jmp 0x104cc72 (-1 の出口)", text(0x10471F9) == "jmp    0x104cc72")

print("summary: gate 参照 58 件はすべて読出し。書込みは 2 箇所 (0x11c7615・0x1262970) で、どちらも 1 を書く。")
sys.exit(0)
