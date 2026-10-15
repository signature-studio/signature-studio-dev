#!/usr/bin/env python3
"""PY-268 (#3901): 公開表 (published method table) の 0x12acb70・0x12ac210・0x12ab710 のエントリ構造、TFXForm の VMT から公開表 (VMT-0x98)・動的メソッド表 (VMT-0x90) への参照経路、0x12ab520 の参照経路、DFM の OnClick・OnMouseWheel の結び付きを PE 上で照合する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py268_rdx.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin' (<展開先>/extracted/block00031_PE.bin に展開される)
Delphi x64 の VMT 配置: 自己ポインタ VMT-0xc8、公開表ポインタ VMT-0x98、動的メソッド表ポインタ VMT-0x90、vmtClassName VMT-0x88。
VMT は自己ポインタ [VMT-0xc8] == VMT を満たす候補のうち、vmtClassName が "TFXForm" のものとして求める (classname から逆算しない)。
終了 0 = 全 PASS。1 件でも FAIL なら終了 1。負の対照は検出できれば PASS。
発火側 (rdx の出どころ) は本スクリプトの対象外 (REPORT_PY268.md §4)。
"""
import os
import re
import struct
import sys

import capstone

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


def control(name, detected, detail=""):
    check("負の対照: " + name, detected, detail)


def is_text(va):
    return TEXT_VA <= va < TEXT_VA + TEXT_SIZE


def va_to_fo(va):
    return va - TEXT_VA + TEXT_FO if is_text(va) else None


def u16(va):
    return struct.unpack_from("<H", RAW, va_to_fo(va))[0]


def u64(va):
    return struct.unpack_from("<Q", RAW, va_to_fo(va))[0]


def shortstr(va):
    o = va_to_fo(va)
    n = RAW[o]
    return RAW[o + 1:o + 1 + n].decode("latin1")


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
        if is_text(va):
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

# VMT: 自己ポインタ [p] == p + 0xc8 (p は .text の 8 バイト整列位置) を満たす候補 V = p + 0xc8 のうち、
# [V-0x88] (vmtClassName) が ShortString "TFXForm" を指すもの。classname の位置から逆算しない。
QW = memoryview(RAW)[TEXT_FO:TEXT_FO + TEXT_SIZE].cast("Q")
self_vmts = [TEXT_VA + 8 * i + 0xC8 for i, v in enumerate(QW) if v == TEXT_VA + 8 * i + 0xC8]
named = [v for v in self_vmts if is_text(v - 0x88) and is_text(u64(v - 0x88))
         and shortstr(u64(v - 0x88)) == "TFXForm"]
check("TFXForm の VMT: 自己ポインタ [VMT-0xc8]==VMT かつ [VMT-0x88] が ShortString \"TFXForm\" を指す候補は 1 件・VMT=0x1277f38",
      named == [0x1277F38], f"self_ptr_candidates={len(self_vmts)} named={[hex(x) for x in named]}")
VMT = named[0] if len(named) == 1 else 0
control("候補 VMT 0x1277ec8 は自己ポインタ検査 ([VMT-0xc8]==VMT) で FAIL",
        u64(0x1277EC8 - 0xC8) != 0x1277EC8, f"[0x1277e00]={hex(u64(0x1277EC8 - 0xC8))}")

PMT = u64(VMT - 0x98)
cnt = u16(PMT)
check("VMT-0x98 (公開表ポインタ) = 0x12793f3・件数 120", PMT == 0x12793F3 and cnt == 120,
      f"ptr={hex(PMT)} count={cnt}")


def walk(first_shift=0):
    p = PMT + 2
    out = []
    for i in range(cnt):
        if not is_text(p):
            break
        out.append(p)
        p += u16(p) + (first_shift if i == 0 else 0)
    return out


KNOWN = (0x127956F, 0x1279614, 0x1279C33)
walked = walk()
hit_known = [e for e in KNOWN if e in walked]
check("VMT-0x98 の公開表を Size で 120 件歩くと、既知の 3 エントリ (0x127956f・0x1279614・0x1279c33) の先頭に一致する",
      len(walked) == cnt and len(hit_known) == 3,
      f"walked={len(walked)} hits={[hex(e) for e in hit_known]} last={hex(walked[-1]) if walked else None}")
shift_hits = [e for e in KNOWN if e in walk(first_shift=1)]
control("公開表の先頭エントリの Size を +1 にずらすと、既知の 3 エントリのうち一致は 3 件未満になる",
        len(shift_hits) < 3, f"hits_after_shift={[hex(e) for e in shift_hits]}")

DMT = u64(VMT - 0x90)
dmt_cnt = u16(DMT)
dmt_idx = u16(DMT + 2)
check("VMT-0x90 (動的メソッド表ポインタ) = 0x127a2b7: 件数 1・DMTIndex 0x057f・アドレス (DMT+4) = 0x12ab520",
      DMT == 0x127A2B7 and dmt_cnt == 1 and dmt_idx == 0x057F and u64(DMT + 4) == 0x12AB520,
      f"dmt={hex(DMT)} count={dmt_cnt} index={hex(dmt_idx)} addr={hex(u64(DMT + 4))}")

# 0x12ab520 の 4 バイト値 (全ブロック) は DMT の address 欄の 1 件のみ (VA 0x127a2bb・8 バイト未整列)
occ4 = []
i = -1
while True:
    i = RAW.find(struct.pack("<I", 0x12AB520), i + 1)
    if i < 0:
        break
    occ4.append(i)
check("0x12ab520 の 4 バイト値: 全ブロックで出現は 1 件 (VA 0x127a2bb・DMT の address 欄)",
      occ4 == [va_to_fo(0x127A2BB)], f"fileoffs={[hex(x) for x in occ4]}")
QW_FILE = memoryview(RAW)[:len(RAW) // 8 * 8].cast("Q")
aligned_12ab520 = [i for i, v in enumerate(QW_FILE) if v == 0x12AB520]
check("0x12ab520 の 8 バイト整列位置の出現は 0 件", aligned_12ab520 == [],
      f"aligned_hits={len(aligned_12ab520)}")
occ_dmt = [i * 8 for i, v in enumerate(QW_FILE) if v == 0x127A2B7]
check("DMT 0x127a2b7 への 8 バイト整列参照は 1 件 (VMT-0x90 のポインタ)", occ_dmt == [va_to_fo(0x1277EA8)],
      f"fileoffs={[hex(x) for x in occ_dmt]}")

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
                       ("0x12acb70 (VA 0x12acb70 と 0x1279571)", {0x12ACB70, 0x1279571}),
                       ("0x127a2ba (DMT 内の 1 バイト目・重なり読みの起点)", {0x127A2BA})]:
    refs = []
    for t, a, o in ref_targets(INS):
        if t in targets:
            refs.append((a, o))
    check(f"{label}: 線形走査の命令の即値・絶対 disp・RIP 相対・分岐先の参照は 0 件", len(refs) == 0,
          f"hits={[(hex(a), o) for a, o in refs[:5]]}")

# 0x127a2ba に fall-through する命令: 0x127a2ba の 15 バイト前から各位置で 1 命令を復号し、0x127a2ba で終わるものを数える
BOUND = 0x127A2BA
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
preds = []
for s in range(BOUND - 15, BOUND):
    ins = next(md.disasm(RAW[va_to_fo(s):va_to_fo(s) + 16], s), None)
    if ins is not None and ins.address + ins.size == BOUND:
        preds.append((hex(s), ins.mnemonic, ins.op_str))
check("0x127a2ba: 0x127a2ba で終わる命令 (fall-through 元) は 0 件 (15 バイト前からの全開始位置)", len(preds) == 0,
      f"preds={preds}")
seq = next(md.disasm(RAW[va_to_fo(BOUND):va_to_fo(BOUND) + 16], BOUND), None)
print("INFO 0x127a2ba からの逐次復号:", f"{seq.mnemonic} {seq.op_str}" if seq else None,
      "(DMT の index 上位 0x05 と address 欄 0x12ab520 の重なり読み。fall-through 元 0 件のため到達しない)")

# DFM (.rsrc の DFM 2 進形式): OnClick=MoveLeftMenuClick は TQuickMenuItem "MoveLeftMenu" のオブジェクト内
hdr = b"\x0eTQuickMenuItem\x0cMoveLeftMenu"
nxt_hdr = b"\x0eTQuickMenuItem\x0dMoveRightMenu"
p0 = RAW.find(hdr)
p1 = RAW.find(nxt_hdr, p0 + 1)
p_click = RAW.find(b"\x07OnClick\x07\x11MoveLeftMenuClick", p0 + 1)
check("DFM: TQuickMenuItem \"MoveLeftMenu\" の直後に OnClick=MoveLeftMenuClick (次のオブジェクト見出しの前)",
      p0 >= 0 and p0 < p_click < p1, f"hdr={p0:#x} onclick={p_click:#x} next={p1:#x} (ファイル位置)")
p_wheel = RAW.find(b"\x0cOnMouseWheel\x07\x16TracksPanelMMouseWheel")
p_wheel2 = RAW.find(b"\x0cOnMouseWheel\x07\x16TracksPanelMMouseWheel", p_wheel + 1)
check("DFM: OnMouseWheel=TracksPanelMMouseWheel の出現は 2 件 (.rsrc 内)", p_wheel >= 0 and p_wheel2 > p_wheel,
      f"hits={p_wheel:#x},{p_wheel2:#x} (ファイル位置)")

print()
print("PASS 件数", sum(RESULTS), "/", len(RESULTS))
sys.exit(0 if all(RESULTS) else 1)
