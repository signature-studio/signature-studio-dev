#!/usr/bin/env python3
"""SR-82 #4930 受入 1 (補助): SerumController の関数内で、`lea reg,[rip+X]` の vtable 先頭 X を `mov [rcx+off], reg` で this の off に書く箇所を列挙する (静的・ヒューリスティック)。

目的: recv_sc_sites.py で受け手が this+off と分類された間接 call について、this+off に書かれる vtable 先頭が候補の表 h と一致するかを見る。
方法: SC の関数ごとに、rcx の定義を同じ関数内で追う簡易版 (rcx を書き換える命令より前の store のみ採用)。
限界: 同じ off に複数の vtable が書かれる場合 (分岐・再代入) は両方を出す。型の確定ではなく、候補の表との整合の確認。
usage: sc_slot_stores.py <pe>
"""
import contextlib
import io
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
pe_path = sys.argv[1]
sys.argv = [sys.argv[0], pe_path]
with contextlib.redirect_stdout(io.StringIO()):
    import receiver_this_trace as R

lea_re = re.compile(r"^(r\w+), \[rip ([+-]) (0x[0-9a-f]+)\]$")
st_re = re.compile(r"^qword ptr \[rcx(?: \+ (0x[0-9a-f]+|\d+))?\], (r\w+)$")

stores = defaultdict(set)
for f in R.SC:
    if f not in R.by_func:
        continue
    lea = {}
    for ins in R.by_func[f]:
        if ins.mnemonic == "lea":
            m = lea_re.match(ins.op_str)
            if m:
                d = int(m.group(3), 16) * (1 if m.group(2) == "+" else -1)
                t = ins.address + ins.size + d
                if R.rva_to_off(t) is not None and R.func_of(t) is None:
                    lea[m.group(1)] = t
                    continue
            lea.pop(ins.op_str.split(",")[0], None)
            continue
        m = st_re.match(ins.op_str)
        if ins.mnemonic == "mov" and m and m.group(2) in lea:
            off = int(m.group(1) or "0", 16 if (m.group(1) or "").startswith("0x") else 10)
            stores[off].add((f, lea[m.group(2)]))
        if ins.mnemonic in ("mov", "lea", "xor", "add", "sub", "pop") and ins.op_str.split(",")[0] == "rcx":
            break

for off in sorted(stores):
    for f, t in sorted(stores[off]):
        print(f"this+{off:#x}\tfunc={f:#x}\tvtable_write={t:#x}")
