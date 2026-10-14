"""SR-25 #1738: Xfer 固有 view / upstream view の vtable 由来の関数数を PE から実測する。

入力: Serum2_win64.vst3 (PE, x64 MSVC)。
方法: MSVC RTTI の TypeDescriptor 名 (.?AV<cls>@@) → COL (Complete Object Locator) → vtable[-1] の順に辿り、
      vtable の各スロットのうち .text 内を指すものを仮想関数とみなす。
限界: 継承元の vtable は別に存在しうる。関数の本体サイズ (B) は本スクリプトでは測らない (Ghidra が要る)。
usage: vtable_measure.py <pe> <class>[@<namespace>] [...]  (例: CTextLabel@VSTGUI)
"""
import struct, sys
import pefile

pe = pefile.PE(sys.argv[1])
data = open(sys.argv[1], "rb").read()
base = pe.OPTIONAL_HEADER.ImageBase
sections = [(s.VirtualAddress, s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData), s) for s in pe.sections]


def sec_of_rva(rva):
    for lo, hi, s in sections:
        if lo <= rva < hi:
            return s
    return None


def name_of(s):
    return s.Name.rstrip(b"\0").decode(errors="replace")


text = [s for s in pe.sections if name_of(s) == ".text"][0]
t_lo = base + text.VirtualAddress
t_hi = t_lo + max(text.Misc_VirtualSize, text.SizeOfRawData)


def rva_to_off(rva):
    s = sec_of_rva(rva)
    return None if s is None else rva - s.VirtualAddress + s.PointerToRawData


for arg in sys.argv[2:]:
    parts = arg.split("@")
    needle = (".?AV" + "@".join(parts) + "@@").encode() + b"\x00"
    hits = []
    i = data.find(needle)
    while i != -1:
        hits.append(i)
        i = data.find(needle, i + 1)
    results = []
    for off in hits:
        td_rva = None
        for s in pe.sections:
            if s.PointerToRawData <= off < s.PointerToRawData + s.SizeOfRawData:
                td_rva = off - s.PointerToRawData + s.VirtualAddress
        if td_rva is None:
            continue
        td_rva -= 0x10  # TypeDescriptor: vfptr(8) spare(8) name(...) -> 名前の前 16 B
        # COL の pTypeDescriptor (rva32) は TypeDescriptor の RVA を指す
        tdv = struct.pack("<I", td_rva)
        p = data.find(tdv)
        cols = []
        while p != -1:
            col_off = p - 12  # COL: signature(4) offset(4) cdOffset(4) pTypeDescriptor(4)
            if col_off >= 0 and struct.unpack_from("<I", data, col_off)[0] == 1:
                cols.append(col_off)
            p = data.find(tdv, p + 1)
        for col_off in cols:
            col_rva = None
            for s in pe.sections:
                if s.PointerToRawData <= col_off < s.PointerToRawData + s.SizeOfRawData:
                    col_rva = col_off - s.PointerToRawData + s.VirtualAddress
            if col_rva is None:
                continue
            col_abs = struct.pack("<Q", base + col_rva)
            q = data.find(col_abs)
            while q != -1:
                vt_off = q + 8  # vtable[0] はこの直後
                slots = []
                k = 0
                while True:
                    o = vt_off + 8 * k
                    if o + 8 > len(data):
                        break
                    v = struct.unpack_from("<Q", data, o)[0]
                    if not (t_lo <= v < t_hi):
                        break
                    slots.append(v)
                    k += 1
                if slots:
                    results.append((0, len(slots), sorted(set(slots))))
                q = data.find(col_abs, q + 1)
    print(f"{arg}: TypeDescriptor hits={len(hits)} vtables={len(results)}")
    for _, n, fns in results:
        print(f"  vtable slots(.text)={n} distinct_fns={len(fns)}")
