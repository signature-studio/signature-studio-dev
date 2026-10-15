#!/usr/bin/env python3
"""PY-235 (#3701): general.processRECEvent の本体 0x1046a30 の eventId 族 (family) 分岐と、戻り値 [rbp+0x5b8] の書込み census を PE から検証する。

  FL_WIN64_DIR=<展開先> python3 analysis/py235_process_rec_families.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
各 assert は REPORT_PY235.md の VA 1 件に対応する (失敗すると非 0 で終わる)。CFG は関数内の直接 jmp/jcc のみ (間接 jmp は 0 件を確認)。
"""
import os
import sys
from collections import deque

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
raw = open(PE, "rb").read()
pe = pefile.PE(data=raw, fast_load=True)
BASE = pe.OPTIONAL_HEADER.ImageBase
FN_LO, FN_HI = 0x1046A30, 0x104CCCA


def fo_of(va):
    rva = va - BASE
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.PointerToRawData + (rva - s.VirtualAddress)
    sys.exit(f"VA {va:#x} が section 外")


def check(label, cond):
    print(("ok   " if cond else "FAIL ") + label)
    if not cond:
        sys.exit(1)


# 本体を線形に逆アセンブル (ret 0x104ccca まで。以降はデータ)
body = {}
for i in md.disasm(raw[fo_of(FN_LO):fo_of(FN_HI) + 16], FN_LO):
    if i.address > FN_HI:
        break
    body[i.address] = i
order = sorted(body)
pos = {a: k for k, a in enumerate(order)}


def text(a):
    return f"{body[a].mnemonic} {body[a].op_str}"


def succ(a):
    i = body[a]
    if i.mnemonic == "ret":
        return []
    if i.mnemonic == "jmp":
        return [int(i.op_str, 16)] if i.op_str.startswith("0x") else ["IND"]
    fall = order[pos[a] + 1] if pos[a] + 1 < len(order) else None
    if i.mnemonic.startswith("j"):
        return [int(i.op_str, 16), fall]
    return [fall]


def reach(entry, avoid=frozenset()):
    seen, q = set(), deque([entry])
    while q:
        a = q.popleft()
        if a is None or a in seen or a in avoid or a not in body:
            continue
        seen.add(a)
        q.extend(s for s in succ(a) if s != "IND")
    return seen


# 1. 族の分岐 (eventId = [rbp+0x5b0] を eax に読んでから)。各 VA は REPORT_PY235 §1 の表
check("0x1047424: eax = [rbp+0x5b0] (eventId)", text(0x1047424) == "mov eax, dword ptr [rbp + 0x5b0]")
check("0x104742a: cmp eax, 0x40000001 / 0x104742f: jg 0x104746a", text(0x104742A) == "cmp eax, 0x40000001" and text(0x104742F) == "jg 0x104746a")
check("0x1047436: je 0x104c4af (eventId == 0x40000001。直前 0x1047431 は cmp eax, 0x40000001)", text(0x1047431) == "cmp eax, 0x40000001" and text(0x1047436) == "je 0x104c4af")
check("0x1047441: cmp eax, 0x70000000 / 0x1047446: jb 0x104aa87", text(0x1047441) == "cmp eax, 0x70000000" and text(0x1047446) == "jb 0x104aa87")
check("0x1047451: cmp eax, 0x10000000 / 0x1047456: jb 0x1047497 (index 族)", text(0x1047451) == "cmp eax, 0x10000000" and text(0x1047456) == "jb 0x1047497")
check("0x104745d: test eax / 0x104745f: jne 0x104caae / 0x1047465: jmp 0x104c2a6 (eventId == 0x40000000)", text(0x104745F) == "jne 0x104caae" and text(0x1047465) == "jmp 0x104c2a6")
check("0x104746a: sub eax, 0x40000002 / 0x1047471: je 0x104c64f", text(0x104746A) == "sub eax, 0x40000002" and text(0x1047471) == "je 0x104c64f")
check("0x104747c: je 0x104c919 (eventId == 0x40000005)", text(0x104747C) == "je 0x104c919")
check("0x1047487: cmp eax, 0x10000000 / 0x104748c: jae 0x104caae / 0x1047492: jmp 0x104aa87", text(0x1047487) == "cmp eax, 0x10000000" and text(0x104748C) == "jae 0x104caae" and text(0x1047492) == "jmp 0x104aa87")
check("0x1047497: shr eax, 0x10 (index = eventId >> 16)", text(0x10474A0) == "mov dword ptr [rbp + 0x580], eax" and "shr eax, 0x10" in text(0x104749D))
check("0x10474b9: index 範囲外 jge 0x104cc72 (-1)", text(0x10474B9) == "jge 0x104cc72")

# 2. 早期 exit: 共通 prefix の gate (*(0x15e1890) != 0 で -1) と (eventId & 0xffff) == 8 の -1 経路
check("0x1046d83: rax = [0x15e1890] (gate の pointer)", text(0x1046D83) == "mov rax, qword ptr [rip + 0x59ab06]" and 0x1046D8A + 0x59AB06 == 0x15E1890)
check("0x1046d8d: gate の jne 0x104cc72 (-1)", text(0x1046D8D) == "jne 0x104cc72")
check("0x10471c4: (eventId & 0xffff) == 8 でなければ 0x10471fe へ", text(0x10471C4) == "jne 0x10471fe")
check("0x10471f9: jmp 0x104cc72 (-1 の出口。runtime 条件つき)", text(0x10471F9) == "jmp 0x104cc72")

# 3. 戻り値 [rbp+0x5b8] の書込み census
stores = [a for a in order if body[a].mnemonic == "mov" and body[a].op_str.startswith("dword ptr [rbp + 0x5b8], ")]
check(f"[rbp+0x5b8] の mov 書込み 74 件 (入口の 0x1046d6b を含む。cmp 9 件は除く): {len(stores)}", len(stores) == 74)
leas = [a for a in order if body[a].mnemonic == "lea" and "[rbp + 0x5b8]" in body[a].op_str]
check("lea [rbp+0x5b8] (アドレス渡し) は 0x104a924 の 1 件", leas == [0x104A924])
check("読出し 0x104cc65 の mov eax, [rbp+0x5b8] → 0x104cc6b で [rbp+0x584] へ", text(0x104CC65) == "mov eax, dword ptr [rbp + 0x5b8]" and text(0x104CC6B) == "mov dword ptr [rbp + 0x584], eax")
indirect = [a for a in order if body[a].mnemonic == "jmp" and not body[a].op_str.startswith("0x")]
check("間接 jmp は 0 件 (CFG が完全)", indirect == [])

# 4. 族ごとの到達性 (CFG)。R-other (0x104caae) は store 0 件・アドレス渡しに到達せず、-1 出口も 0x104cc65 を通らない
r_other = reach(0x104CAAE)
check("R-other (0x104caae) から到達する 5b8 store は 0 件", not [a for a in stores if a in r_other])
check("R-other から lea 0x104a924 に到達しない", 0x104A924 not in r_other)
check("R-other から 0x104cc65 を通らず ret に到達しない / 0x104cc72 への辺も無い",
      0x104CCCA not in reach(0x104CAAE, {0x104CC65}) and not any(0x104CC72 in succ(a) for a in reach(0x104CAAE, {0x104CC65})))
prefix = reach(0x1046A30, {0x1047424})
exits = sorted(hex(a) for a in prefix if 0x104CC72 in succ(a))
check(f"共通 prefix の -1 出口は 2 箇所 (gate と 0x10471f9): {exits}", exits == ["0x1046d8d", "0x10471f9"])
check("共通 prefix から到達する 5b8 store は入口の 1 件のみ", [a for a in stores if a in prefix] == [0x1046D6B])

# 5. 固定 eventId の 3 族 (0x104c4af・0x104c64f・0x104c919・0x104c2a6) の store (未確定。REPORT §3)
fixed = {"0x40000001": (0x104C4AF, [0x104C51A, 0x104C56D]), "0x40000000": (0x104C2A6, [0x104C311, 0x104C3F0]),
         "0x40000002": (0x104C64F, [0x104C6BA, 0x104C769]), "0x40000005": (0x104C919, [0x104C984, 0x104C9E6])}
for name, (entry, want) in fixed.items():
    got = sorted(a for a in stores if a in reach(entry))
    check(f"eventId {name} (entry {entry:#x}) の 5b8 store = {[hex(a) for a in want]}", got == want)
# PY-252 (#3778): 固定 4 族の store は flags ([rbp+0x5c0]) の 0x20/0x2 ガードの内側。アドレス渡しに届かない
fixed_all = set().union(*(reach(e) for e, _ in fixed.values()))
check("固定 4 族から lea 0x104a924 (アドレス渡し) に到達しない (flags & 0x22 == 0 で戻り値 = value)", 0x104A924 not in fixed_all)

# 6. 未確定の族: 0x104aa87 (0x70000000 族) と index 族 (0x1047497) は lea 0x104a924 (アドレス渡し) に到達する
check("0x70000000 族 (0x104aa87) は lea 0x104a924 に到達する (未確定の理由)", 0x104A924 in reach(0x104AA87))
check("index 族 (0x1047497) は lea 0x104a924 に到達する (未確定の理由)", 0x104A924 in reach(0x1047497))
print("summary: R-other (eventId の 0x10000000〜0x3fffffff・0x40000003〜4・0x40000006〜0x6fffffff・0xf0000000〜0xffffffff) で (eventId & 0xffff) != 8 かつ gate 0 の成功経路は戻り値 = value")
