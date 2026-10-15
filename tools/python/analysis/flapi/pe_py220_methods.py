#!/usr/bin/env python3
"""PY-220 (#3616): 間接呼出し 4 関数 (0x12ab520・0x12acb70・0x1021670・0x12ac210) の所属データ構造を PE 上で確定する。
(0x12ab710 は 0x12ac210 と同じ公開表の別ハンドラとして併せて照合する。)

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py220_methods.py

構造 (公開メソッド表 TMethodEntry の推定形): [Len: word][Code: qword][Name: ShortString]、Len = 2 + 8 + (1 + len(Name))。
表の先頭は Count: word (先頭エントリの 2 バイト前)。VMT の判定は `[VMT-0xc8] == VMT` (自己ポインタ) と
`[VMT-0x88]` の ShortString (pe_vmt_probe.py と同じ)。表ポインタの位置は VMT-0x98 (陽性対照で確認)。
終了 0 = 全 PASS。1 件でも FAIL なら終了 1。
"""
import os
import struct
import sys

import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
RAW = open(PE, "rb").read()
PEF = pefile.PE(data=RAW, fast_load=True)
BASE = PEF.OPTIONAL_HEADER.ImageBase
TEXT = next(s for s in PEF.sections if s.Name.rstrip(b"\0") == b".text")
T0 = BASE + TEXT.VirtualAddress
T1 = T0 + min(TEXT.Misc_VirtualSize, TEXT.SizeOfRawData)
FOFF = TEXT.PointerToRawData - T0
RESULTS = []
TARGETS = (0x12AB520, 0x12ACB70, 0x1021670, 0x12AC210, 0x12AB710)


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print("PASS" if ok else "FAIL", name, detail)


def u16(va):
    return struct.unpack_from("<H", RAW, va + FOFF)[0]


def u64(va):
    return struct.unpack_from("<Q", RAW, va + FOFF)[0]


def shortstr(va):
    n = RAW[va + FOFF]
    return RAW[va + FOFF + 1:va + FOFF + 1 + n].decode("latin1")


def is_name(va):
    n = RAW[va + FOFF]
    body = RAW[va + FOFF + 1:va + FOFF + 1 + n]
    return 1 <= n <= 200 and all(0x20 <= c < 0x7F for c in body)


def entry(p, shift=0):
    if not (T0 <= p and p + 18 <= T1):
        return None
    ln = u16(p)
    if ln < 11 or ln > 300:
        return None
    code = u64(p + 2)
    if not (T0 <= code < T1) or RAW[p + FOFF + 6:p + FOFF + 10] != b"\0\0\0\0":
        return None
    if ln != 11 + shift + RAW[p + FOFF + 10] or not is_name(p + 10):
        return None
    return ln, code, shortstr(p + 10)


def scan(shift=0):
    ents = {}
    for f in range(T0 + FOFF, T1 + FOFF - 18):
        if RAW[f + 6:f + 10] != b"\0\0\0\0":
            continue
        p = f - FOFF
        e = entry(p, shift)
        if e:
            ents[p] = e
    return ents


def chains(ents):
    nxt = {p + e[0] for p, e in ents.items()}
    out = []
    for h in [p for p in ents if p not in nxt]:
        seq, p = [], h
        while p in ents:
            seq.append(p)
            p += ents[p][0]
        out.append(seq)
    return out


def is_vmt(v):
    return T0 <= v - 0xC8 and v < T1 and u64(v - 0xC8) == v and T0 <= u64(v - 0x88) < T1 and is_name(u64(v - 0x88))


def vmt_nearest(slot, span=0x400):
    for i in range(span):
        v = slot - 8 * i
        if T0 + 0xC8 <= v < T1 and is_vmt(v):
            return v, i
    return None


def main():
    ents = scan()
    neg = scan(shift=1)
    print(f"method-entry candidates in .text: {len(ents)} (control: Len 1 byte off -> {len(neg)})")
    check("負の対照: Len を 1 バイトずらすと候補が 0 件", len(neg) == 0, f"{len(neg)}")
    ch = [c for c in chains(ents) if len(c) >= 2]
    ok = sum(1 for c in ch if u16(c[0] - 2) == len(c))
    print(f"chains (length >= 2): {len(ch)}, longest {max(len(c) for c in ch)}")
    check("表の Count (先頭エントリの 2 バイト前) が鎖の長さと一致", ok == len(ch) and len(ch) > 0, f"{ok}/{len(ch)}")

    for t in TARGETS:
        where = [p for p in ents if ents[p][1] == t]
        if where:
            p = where[0]
            head = next(c[0] for c in ch if p in c) if any(p in c for c in ch) else p
            print(f"{t:#x}: 公開表 entry {p:#x} name {ents[p][2]!r} Len={ents[p][0]:#x} (2+8+1+{RAW[p + FOFF + 10]})"
                  f" 表先頭 {head:#x} Count={u16(head - 2)}")
    check("0x12acb70・0x12ac210・0x12ab710 は公開表のエントリ (Len = 2+8+1+名前長)",
          all(any(ents[p][1] == t for p in ents) for t in (0x12ACB70, 0x12AC210, 0x12AB710)))
    names = {ents[p][2] for p in ents if ents[p][1] in (0x12ACB70, 0x12AC210, 0x12AB710)}
    check("公開表の名前: MoveLeftMenuClick・TracksPanelMMouseWheel・FormMouseWheel",
          names == {"MoveLeftMenuClick", "TracksPanelMMouseWheel", "FormMouseWheel"}, str(sorted(names)))
    check("0x12ab520 は公開表のエントリではない", not any(ents[p][1] == 0x12AB520 for p in ents))

    head = next(c[0] for c in ch if any(ents[p][1] == 0x12ACB70 for p in c))
    hdr_refs = [L for L in range(T0, T1 - 8) if u64(L) == head - 2]
    owner = []
    for L in hdr_refs:
        for k in range(0x08, 0x100, 8):
            v = L + k
            if T0 <= v - 0xC8 and v < T1 and is_vmt(v):
                owner.append((v, k, shortstr(u64(v - 0x88))))
    print(f"表ポインタの所在 (値 = 表先頭 - 2): {[hex(x) for x in hdr_refs]}, 所属 VMT: {[(hex(v), hex(k), n) for v, k, n in owner]}")
    check("公開表 (count 120) は TFXForm の VMT の表ポインタ (VMT-0x98) から参照される",
          any(n == "TFXForm" and k == 0x98 for _, k, n in owner))

    vmts = [v for v in range(T0 + 0xC8, T1) if is_vmt(v)]
    print(f"VMT (自己ポインタ判定) 全件: {len(vmts)}、うち 8 バイト整列 {sum(1 for v in vmts if v % 8 == 0)}")
    check("全 VMT は 8 バイト整列 (スロットの整列の前提)", vmts and all(v % 8 == 0 for v in vmts), f"{len(vmts)}")
    check("陽性対照: 既知の VMT TPublicChannel (0xfe2cf8) のスロット 35 (0xfe2e10) を同じ判定で VMT と認める",
          vmt_nearest(0xFE2E10) == (0xFE2CF8, 35))
    a = [L for L in range(T0, T1 - 8) if u64(L) == 0x12AB520]
    align = [L % 8 for L in a]
    print(f"0x12ab520 の qword 参照 (VA): {[hex(x) for x in a]} (mod 8 = {align})")
    check("0x12ab520 の参照位置は 8 バイト未整列 (VMT スロットの整列に合わない)", a and all(x % 8 for x in align))
    check("0x12ab520 から VMT への後方候補は 0 件 (VMT 推定は否定)",
          all(vmt_nearest(L) is None for L in a))

    b = [L for L in range(T0, T1 - 8) if u64(L) == 0x1021670]
    print(f"0x1021670 の qword 参照 (VA): {[hex(x) for x in b]}")
    near = [vmt_nearest(L) for L in b]
    print(f"  最近の VMT: {[(hex(v), i, shortstr(u64(v - 0x88))) for v, i in near if v]}")
    check("0x1021670 は VMT 0x1012f40 (TUndoEvent_MovedFXTracks) のスロット 1 (VMT+8)",
          any(v == 0x1012F40 and i == 1 for v, i in near if v))
    print(f"{sum(RESULTS)}/{len(RESULTS)} PASS")
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
