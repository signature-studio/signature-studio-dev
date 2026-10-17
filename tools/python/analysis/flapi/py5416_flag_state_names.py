#!/usr/bin/env python3
"""F1・F2・Z の書込み関数と、その直接呼出し元の RIP 相対参照文字列を PE から洗う (PY-5416 / #6029)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/py5416_flag_state_names.py

- 対象の関数境界は py5413_flag_writers.py と同じ .pdata から取る。
- 文字列は、関数内の RIP 相対 (lea/mov/cmp 等のメモリ参照) の先が、読める区間で
  NUL 終端の ASCII (4 文字以上) か UTF-16LE の場合に拾う。
- 呼出し元は .text 内の E8 (call rel32) の直接呼出しのみ。間接呼出しは拾えない。
- 文字列が 1 つも無い関数は「文字列なし」と出す。状態名は、この出力から読めたものだけを書く。
"""
import bisect
import struct

import capstone

import py248_gate_chain as g
from py5413_flag_writers import load_pdata

FUNCS = {
    "F1": [0xC4DBA0, 0xC4E570, 0xD18130, 0xD1AF20],
    "F2": [0xF46310, 0xF51FD0, 0xFEFBA0, 0xFFF070, 0x1042D20, 0x11D58C0],
    "Z": [0x11C71B0, 0x1262970],
}


def sec_of(va):
    rva = va - g.BASE
    for s in g.PEF.sections:
        size = max(s.Misc_VirtualSize, s.SizeOfRawData)
        if s.VirtualAddress <= rva < s.VirtualAddress + size:
            return s, rva - s.VirtualAddress
    return None, None


def read_str_at(va):
    s, off = sec_of(va)
    if s is None or off >= s.SizeOfRawData:
        return None
    raw = g.RAW[s.PointerToRawData + off:s.PointerToRawData + s.SizeOfRawData]
    end = raw.find(b"\0")
    if 4 <= end <= 200:
        body = raw[:end]
        if all(0x20 <= c < 0x7F for c in body):
            return body.decode("ascii")
    if len(raw) >= 2:
        n = 0
        while n + 1 < len(raw) and n < 400:
            ch = raw[n:n + 2]
            if ch == b"\0\0":
                break
            if not (ch[1] == 0 and 0x20 <= ch[0] < 0x7F):
                break
            n += 2
        if n >= 8:
            return raw[:n].decode("utf-16-le")
    return None


def strings_in(fs, fe):
    found = []
    f = g.fo(fs)
    if f is None:
        return found
    code = g.RAW[f:f + (fe - fs)]
    for ins in g.MD.disasm(code, fs):
        tgt = g.rip_target(ins)
        if tgt is None:
            continue
        txt = read_str_at(tgt)
        if txt is not None:
            found.append((ins.address, tgt, txt))
    return found


def main():
    rf = load_pdata()
    starts = [a for a, _ in rf]

    def bounds(va):
        i = bisect.bisect_right(starts, va) - 1
        return rf[i] if i >= 0 and rf[i][0] <= va < rf[i][1] else None

    text = [s for s in g.PEF.sections if s.Name.rstrip(b"\0") == b".text"][0]
    t0 = g.BASE + text.VirtualAddress
    buf = g.RAW[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]

    targets = {}
    for name, lst in FUNCS.items():
        for fs in lst:
            b = bounds(fs)
            if b is None or b[0] != fs:
                print(f"{name} {fs:#x} .pdata 境界と不一致")
                continue
            targets[fs] = (name, b[1])

    callers = {t: [] for t in targets}
    i = buf.find(b"\xe8")
    while i != -1:
        if i + 5 <= len(buf):
            tgt = t0 + i + 5 + struct.unpack_from("<i", buf, i + 1)[0]
            if tgt in callers:
                callers[tgt].append(t0 + i)
        i = buf.find(b"\xe8", i + 1)

    print("== 1. 書込み関数の RIP 相対文字列")
    for fs, (name, fe) in targets.items():
        hits = strings_in(fs, fe)
        print(f"  {name} fn {fs:#x} (size {fe - fs:#x}): 文字列 {len(hits)} 件")
        for at, tgt, txt in hits[:20]:
            print(f"      {at:#x} -> {tgt:#x} {txt!r}")

    print("== 2. 直接呼出し元の RIP 相対文字列 (呼出し元の関数全体)")
    for fs, (name, _) in targets.items():
        for c in callers[fs][:10]:
            cb = bounds(c)
            if cb is None:
                print(f"  {name} fn {fs:#x} <- {c:#x} 境界なし")
                continue
            hits = strings_in(cb[0], cb[1])
            print(f"  {name} fn {fs:#x} <- {c:#x} (caller fn {cb[0]:#x}): 文字列 {len(hits)} 件")
            for at, tgt, txt in hits[:12]:
                print(f"      {at:#x} -> {tgt:#x} {txt!r}")


if __name__ == "__main__":
    main()
