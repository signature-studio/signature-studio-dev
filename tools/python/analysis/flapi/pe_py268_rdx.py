#!/usr/bin/env python3
"""PY-268 (#3901): 公開表 (published method table) の 0x12acb70・0x12ac210・0x12ab710 のエントリ構造、TFXForm の VMT から公開表 (VMT-40)・動的メソッド表 (VMT-32) への参照経路、0x12ab520 の参照経路、DFM の OnClick・OnMouseWheel の結び付きを PE 上で照合する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py268_rdx.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin' (<展開先>/extracted/block00031_PE.bin に展開される)
終了 0 = 全 PASS。1 件でも FAIL なら終了 1。
発火側 (rdx の出どころ) は本スクリプトの対象外 (REPORT_PY268.md §4)。
"""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pe_callgraph as pc  # noqa: E402

RAW = open(os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin"), "rb").read()
TEXT_VA = 0x401000
TEXT_FO = 0x400
TEXT_SIZE = 0xFA34B0
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print("PASS" if ok else "FAIL", name, detail)


def va_to_fo(va):
    if TEXT_VA <= va < TEXT_VA + TEXT_SIZE:
        return va - TEXT_VA + TEXT_FO
    return None


def u16(va):
    return struct.unpack_from("<H", RAW, va_to_fo(va))[0]


def u64(va):
    return struct.unpack_from("<Q", RAW, va_to_fo(va))[0]


def shortstr(va):
    n = RAW[va_to_fo(va)]
    return RAW[va_to_fo(va) + 1:va_to_fo(va) + 1 + n].decode("latin1")


def entry_of(code):
    """公開表エントリの位置。Code (8 バイト・上位 4 バイト 0) の出現を探し、Size (u16) は直前 2 バイト、名前 (ShortString) は +8。"""
    pat = struct.pack("<I", code) + b"\x00\x00\x00\x00"
    hits = []
    i = -1
    while True:
        i = RAW.find(pat, i + 1)
        if i < 0:
            break
        va = i - TEXT_FO + TEXT_VA
        if TEXT_VA <= va < TEXT_VA + TEXT_SIZE:
            hits.append(va)
    return hits


def entry_fields(code_va_slot):
    size = u16(code_va_slot - 2)
    name = shortstr(code_va_slot + 8)
    return size, name


INS = pc.load()
TXT_RIP = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")
HEX = re.compile(r"0x[0-9a-f]+")

ENTRY = {
    0x12ACB70: ("MoveLeftMenuClick", 0x1C),
    0x12AC210: ("TracksPanelMMouseWheel", 0x21),
    0x12AB710: ("FormMouseWheel", 0x19),
}
for code, (exp_name, exp_size) in ENTRY.items():
    hits = entry_of(code)
    check(f"{hex(code)}: 公開表エントリの出現は 1 件 (Code 8 バイト・上位 0)", len(hits) == 1,
          f"slots={[hex(h) for h in hits]}")
    if len(hits) != 1:
        continue
    slot = hits[0]
    size, name = entry_fields(slot)
    check(f"{hex(code)}: Size={hex(exp_size)} (2+8+1+len(name))、名前={exp_name}、エントリ位置 {hex(slot - 2)}",
          size == exp_size == 2 + 8 + 1 + len(name) and name == exp_name,
          f"size={hex(size)} name={name!r}")

# 0x12ab520: 4 バイト値の出現は 1 件 (VA 0x127a2bb・8 バイト未整列)。直後の Size 位置は表エントリの式と合わない。
hits_ab520 = entry_of(0x12AB520)
check("0x12ab520: 8 バイト値 (上位 0) の出現は 1 件・VA 0x127a2bb・8 バイト未整列",
      hits_ab520 == [0x127A2BB] and hits_ab520[0] % 8 != 0, f"slots={[hex(h) for h in hits_ab520]}")
size_ab520, name_ab520 = entry_fields(0x127A2BB)
check("0x12ab520: 直前 2 バイトは公開表 Size の式 (2+8+1+len) と一致しない (公開表エントリではない。次行の DMT の index)",
      size_ab520 != 2 + 8 + 1 + len(name_ab520), f"word={hex(size_ab520)} 直後の ShortString={name_ab520!r}")

# TFXForm の VMT (vmtClassName が 0x127a2c3 を指す位置 0x1277eb0 から逆算した 0x1277ec8)。VMT-40 = 公開表、VMT-32 = 動的メソッド表 (DMT)
VMT = 0x1277EB0 + 24
check("VMT(TFXForm)=0x1277ec8: vmtClassName (VMT-24) = 0x127a2c3 の ShortString は TFXForm",
      u64(VMT - 24) == 0x127A2C3 and shortstr(0x127A2C3) == "TFXForm", f"name={shortstr(0x127A2C3)!r}")
PMT = u64(VMT - 40)
cnt = u16(PMT)
p = PMT + 2
walk = []
for _ in range(cnt):
    walk.append(p)
    p += u16(p)
check("VMT-40 の公開表 (0x12793f3) を Size で順に歩くと、0x127956f (MoveLeftMenuClick) のエントリ先頭に一致する",
      0x127956F in walk, f"count={cnt} entries_walked={len(walk)} last={hex(walk[-1]) if walk else None}")
DMT = u64(VMT - 32)
dmt_cnt = u16(DMT)
dmt_idx = u16(DMT + 2)
check("VMT-32 の動的メソッド表 (0x127a2b7): 件数 1・DMTIndex 0x057f・アドレス (DMT+4) = 0x12ab520",
      DMT == 0x127A2B7 and dmt_cnt == 1 and dmt_idx == 0x057F and u64(DMT + 4) == 0x12AB520,
      f"dmt={hex(DMT)} count={dmt_cnt} index={hex(dmt_idx)} addr={hex(u64(DMT + 4))}")

# 命令側の参照 (即値・絶対 disp・RIP 相対)
def ref_targets(insns):
    for idx, (a, m, o) in enumerate(insns):
        for tok in HEX.findall(o):
            yield int(tok, 16), a, o
        mm = TXT_RIP.search(o)
        if mm and idx + 1 < len(insns):
            nxt = insns[idx + 1][0]
            disp = int(mm.group(2), 16)
            yield (nxt + disp if mm.group(1) == "+" else nxt - disp), a, o


for label, targets in [("0x12ab520 (VA 0x12ab520 と 0x127a2bb)", {0x12AB520, 0x127A2BB, 0x127A2B9}),
                       ("0x12acb70 (VA 0x12acb70 と 0x1279571)", {0x12ACB70, 0x1279571})]:
    refs = []
    for t, a, o in ref_targets(INS):
        if t in targets:
            refs.append((a, o))
    check(f"{label}: 命令の即値・絶対 disp・RIP 相対の参照は 0 件", len(refs) == 0,
          f"hits={[(hex(a), o) for a, o in refs[:5]]}")

# DFM (.rsrc の DFM 2 進形式): OnClick=MoveLeftMenuClick は TQuickMenuItem "MoveLeftMenu" のオブジェクト内
hdr = b"\x0eTQuickMenuItem\x0cMoveLeftMenu"
nxt_hdr = b"\x0eTQuickMenuItem\x0dMoveRightMenu"
p0 = RAW.find(hdr)
p1 = RAW.find(nxt_hdr, p0 + 1)
p_click = RAW.find(b"\x07OnClick\x07\x11MoveLeftMenuClick", p0 + 1)
check("DFM: TQuickMenuItem \"MoveLeftMenu\" の直後に OnClick=MoveLeftMenuClick (次のオブジェクト見出しの前)",
      p0 >= 0 and p0 < p_click < p1, f"hdr={p0:#x} onclick={p_click:#x} next={p1:#x}")
p_wheel = RAW.find(b"\x0cOnMouseWheel\x07\x16TracksPanelMMouseWheel")
p_wheel2 = RAW.find(b"\x0cOnMouseWheel\x07\x16TracksPanelMMouseWheel", p_wheel + 1)
check("DFM: OnMouseWheel=TracksPanelMMouseWheel の出現は 2 件 (.rsrc 内)", p_wheel >= 0 and p_wheel2 > p_wheel,
      f"hits={p_wheel:#x},{p_wheel2:#x}")

print()
print("PASS 件数", sum(RESULTS), "/", len(RESULTS))
sys.exit(0 if all(RESULTS) else 1)
