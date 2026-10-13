#!/usr/bin/env python3
# usage: 実行はこのディレクトリ (tools/targets/massivex) から: python3 license/scripts/mx_callers_probe.py
"""N6 読み手関数 (N6-1〜6) への直接 call/jmp (E8/E9 rel32) 呼び出し元を列挙する。"""
import bisect
import numpy as np
import pefile

PE = "work/extracted/VST3/Massive X.vst3"
data = open(PE, "rb").read()
pe = pefile.PE(data=data, fast_load=True)
IB = pe.OPTIONAL_HEADER.ImageBase
text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
T_OFF, T_VA, T_SZ = text.PointerToRawData, IB + text.VirtualAddress, text.SizeOfRawData
buf = np.frombuffer(data[T_OFF:T_OFF + T_SZ], dtype=np.uint8)

targets = [0x180f95e20, 0x181142370, 0x181144570, 0x181142640, 0x1811453f0]
hits = {t: [] for t in targets}
for op in (0xE8, 0xE9):
    idx = np.nonzero(buf[:-4] == op)[0]
    for i in idx:
        rel = int.from_bytes(data[T_OFF + i + 1: T_OFF + i + 5], "little", signed=True)
        dst = T_VA + i + 5 + rel
        if dst in hits:
            hits[dst].append((hex(T_VA + i), "E8" if op == 0xE8 else "E9"))

for t in targets:
    print(f"fn {t:#x}: direct call/jmp {len(hits[t])} 件", hits[t][:10])
