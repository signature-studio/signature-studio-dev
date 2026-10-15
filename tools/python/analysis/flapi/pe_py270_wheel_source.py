#!/usr/bin/env python3
"""PY-270 (#3903): 0x12ac210 (TFXForm の公開メソッド TracksPanelMMouseWheel) の第 4 引数 r9 の発火側を PE 上で探す。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py270_wheel_source.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
終了 0 = 全 PASS。1 件でも FAIL なら終了 1。
確認する事実 (REPORT_PY270.md §1): 0x12ac210 の参照は公開表のスロット 1 件だけ (生バイト走査)、直接 call・RIP 相対参照は 0 件、
6 引数のメソッドポインタ呼出しの形 (r9 符号付き読込み + スタック 5・6 番目) の候補は 2 件で、どちらも WM_MOUSEWHEEL の分岐を含まない、
WheelDelta (= 符号付き word [msg+0xa]) の読込みは 11 箇所。発火側の確定は未達 (REPORT_PY270.md §4)。
"""
import bisect
import os
import re
import struct
import sys

import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pe_callgraph as pc  # noqa: E402

INS = pc.load()
STARTS = pc.function_starts(INS)
RAW = open(pc.PE, "rb").read()
PE = pefile.PE(data=RAW, fast_load=True)
BASE = PE.OPTIONAL_HEADER.ImageBase
TEXT = next(s for s in PE.sections if s.Name.rstrip(b"\0") == b".text")
RESULTS = []
WRAP = 0x12AC210
PRIMARY = 0x12AB710


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print("PASS" if ok else "FAIL", name, detail)


def fn_of(va):
    i = bisect.bisect_right(STARTS, va) - 1
    return STARTS[i] if i >= 0 else None


def fo(va):
    for s in PE.sections:
        lo = BASE + s.VirtualAddress
        if lo <= va < lo + s.SizeOfRawData:
            return va - lo + s.PointerToRawData
    raise ValueError(hex(va))


def qword_slots(value):
    pat = struct.pack("<Q", value)
    out = []
    pos = RAW.find(pat)
    while pos != -1:
        for s in PE.sections:
            if s.PointerToRawData <= pos < s.PointerToRawData + s.SizeOfRawData:
                out.append(BASE + s.VirtualAddress + pos - s.PointerToRawData)
                break
        pos = RAW.find(pat, pos + 1)
    return out


def next_addr(i):
    return INS[i + 1][0] if i + 1 < len(INS) else None


def rip_refs_to(target):
    hits = []
    for i, (a, m, o) in enumerate(INS):
        if "[rip" not in o or next_addr(i) is None:
            continue
        mm = re.search(r"\[rip ([+-]) (0x[0-9a-f]+)\]", o)
        if mm is None:
            continue
        d = int(mm.group(2), 16) * (1 if mm.group(1) == "+" else -1)
        if next_addr(i) + d == target:
            hits.append((a, m, o))
    return hits


def body_of(f):
    i = bisect.bisect_right(STARTS, f) - 1
    s = STARTS[i]
    e = STARTS[i + 1] if i + 1 < len(STARTS) else s + 0x10000
    return [(a, m, o) for a, m, o in INS if s <= a < e]


# 1. 公開表のスロット (生バイト走査。逆アセンブルに依存しない)
slots = qword_slots(WRAP)
check("0x12ac210 を 8 バイト値として持つ箇所は公開表の 1 件", slots == [0x1279C35], [hex(x) for x in slots])
s = fo(slots[0])
name_len = RAW[s + 8]
name = RAW[s + 9:s + 9 + name_len]
check("スロットの直後の ShortString が TracksPanelMMouseWheel", name == b"TracksPanelMMouseWheel", repr(name))
check("PY-220 の公開表の隣接エントリ (FXViewModeSelectBeforePopup) が同じ表にある",
      b"FXViewModeSelectBeforePopup" in RAW[s:s + 0x80] or b"FXViewModeSelectBeforePopup" in RAW[s:s + 0x200])

# 2. 直接 call・RIP 相対参照 (逆アセンブル)
direct = [a for a, m, o in INS if m == "call" and o == hex(WRAP)]
check("0x12ac210 への直接 call は 0 件", len(direct) == 0, str(len(direct)))
rip = rip_refs_to(WRAP)
check("0x12ac210 への RIP 相対参照は 0 件", len(rip) == 0, str(len(rip)))
p_direct = [a for a, m, o in INS if m == "call" and o == hex(PRIMARY)]
check("0x12ab710 への直接 call は 1 件 (0x12ac257 in 0x12ac210)",
      p_direct == [0x12AC257] and fn_of(0x12AC257) == WRAP, [hex(x) for x in p_direct])

# 3. 6 引数のメソッドポインタ呼出しの形 (r9 符号付き読込み + スタック 5・6 番目の書込み + lea)
def shape_hits(need_signed_r9=True):
    out = []
    for i, (a, m, o) in enumerate(INS):
        if m != "call" or o.startswith("0x"):
            continue
        f = fn_of(a)
        back = []
        j = i - 1
        while j >= 0 and fn_of(INS[j][0]) == f and len(back) < 22:
            back.append(INS[j])
            j -= 1
        txt = [f"{x[1]} {x[2]}" for x in reversed(back)]
        st5 = any(re.match(r"^mov qword ptr \[rsp \+ 0x20\],", t) for t in txt)
        st6 = any(re.match(r"^mov qword ptr \[rsp \+ 0x28\],", t) for t in txt)
        r9s = [t for t in txt if re.match(r"^movsx(d)?\s+r9", t)]
        lea = any(" lea " in " " + t for t in txt)
        if st5 and st6 and lea and (r9s or not need_signed_r9):
            out.append((a, o, f))
    return out


strict = shape_hits()
check("6 引数のメソッドポインタ呼出しの候補 (r9 符号付き読込み) は 2 件", len(strict) == 2,
      " ".join(f"{hex(a)}(in {hex(f)})" for a, _, f in strict))
wm_in_cands = [f for _, _, f in strict if any(re.search(r"\b0x20a\b", o) for _, _, o in body_of(f))]
check("その候補のうち WM_MOUSEWHEEL (0x20a) を含む関数は 0 件", len(wm_in_cands) == 0, str(len(wm_in_cands)))
# 負の対照: r9 の符号付き条件を外すと候補が増える (条件が効いていることの確認)
loose = shape_hits(need_signed_r9=False)
check("負の対照: r9 条件を外すと候補が 2 件より増える", len(loose) > len(strict), f"{len(strict)} -> {len(loose)}")

# 4. WheelDelta (符号付き word [msg+0xa]) の読込み
wd = [(a, m, o) for a, m, o in INS if re.match(r"^movsx\s+\w+,\s+word ptr \[\w+ \+ 0xa\]$", f"{m} {o}")]
check("movsx word [reg+0xa] の読込みは 11 箇所 (9 関数)", len(wd) == 11 and len({fn_of(a) for a, _, _ in wd}) == 9,
      f"{len(wd)} / {len({fn_of(a) for a, _, _ in wd})}")
check("0x60dc34 は WheelDelta (movsx rax, word ptr [rsi+0xa]) を読む (Keys 0x40 の分岐と換算は未検査)",
      any(a == 0x60DC34 and "movsx rax, word ptr [rsi + 0xa]" in f"{m} {o}" for a, m, o in INS))

# 5. WM_MOUSEWHEEL の受取の連鎖 (0x612aa0 → 0x60c220 → 仮想 [rbx+0x80])
check("0x612c48 は cmp eax, 0x20a で分岐し、0x60c220 を呼ぶ",
      any(a == 0x612C48 and o == "eax, 0x20a" for a, m, o in INS) and any(a == 0x612C59 and o == hex(0x60C220) for a, m, o in INS))
check("0x60c220 は [rbx+0x80] の仮想 call で TMessage 相当 (rdx) を渡す",
      any(m == "call" and o == "qword ptr [rbx + 0x80]" for a, m, o in body_of(0x60C220)))

print(f"{sum(RESULTS)}/{len(RESULTS)} PASS")
sys.exit(0 if all(RESULTS) else 1)
