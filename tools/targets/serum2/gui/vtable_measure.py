"""SR-25 #1738 / SR-29 #1920: Xfer 固有 view / upstream view の vtable 由来の関数数を PE から実測する。

入力: Serum2_win64.vst3 (PE, x64 MSVC)。
方法: MSVC RTTI の TypeDescriptor 名 (.?AV<cls>@@) → COL (Complete Object Locator) → vtable[-1] の順に辿り、
      vtable の各スロットのうち .text 内を指すものを仮想関数とみなす。
      継承元 (COL → CHD → BaseClassArray → BaseClassDescriptor → TypeDescriptor) の vtable と同じ
      インデックスで同じ値を持つスロットは継承とみなし、残りを override / 新規の仮想関数として数える。
限界: 継承元の vtable が PE 内に無い場合は全スロットを override とみなす (上限値)。
      関数の本体サイズ (B) は本スクリプトでは測らない (Ghidra が要る)。
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


def off_to_rva(off):
    for s in pe.sections:
        if s.PointerToRawData <= off < s.PointerToRawData + s.SizeOfRawData:
            return off - s.PointerToRawData + s.VirtualAddress
    return None


def td_name(td_rva):
    o = rva_to_off(td_rva + 0x10)
    if o is None:
        return None
    e = data.find(b"\x00", o)
    return data[o:e].decode(errors="replace")


def col_rvas_of_td(td_rva):
    """TypeDescriptor の RVA を指す COL の RVA 一覧 (COL の pTypeDescriptor は rva32)。"""
    out = []
    tdv = struct.pack("<I", td_rva)
    p = data.find(tdv)
    while p != -1:
        col_off = p - 12  # COL: signature(4) offset(4) cdOffset(4) pTypeDescriptor(4) pClassDescriptor(4) pSelf(4)
        if col_off >= 0 and struct.unpack_from("<I", data, col_off)[0] == 1:
            col_rva = off_to_rva(col_off)
            if col_rva is not None:
                out.append(col_rva)
        p = data.find(tdv, p + 1)
    return out


def vtables_of_col(col_rva):
    """COL を指す vtable[-1] 位置の後ろから、.text を指すスロット列を vtable ごとに返す。"""
    res = []
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
            res.append(slots)
        q = data.find(col_abs, q + 1)
    return res


def base_td_rvas(col_rva):
    """COL → CHD → BaseClassArray の TypeDescriptor RVA 一覧 (自分自身を含む)。"""
    co = rva_to_off(col_rva)
    chd_rva = struct.unpack_from("<I", data, co + 0x10)[0]
    chd = rva_to_off(chd_rva)
    n = struct.unpack_from("<I", data, chd + 8)[0]
    bca = rva_to_off(struct.unpack_from("<I", data, chd + 0xC)[0])
    out = []
    for i in range(n):
        bcd_rva = struct.unpack_from("<I", data, bca + 4 * i)[0]
        out.append(struct.unpack_from("<I", data, rva_to_off(bcd_rva))[0])
    return out


for arg in sys.argv[2:]:
    parts = arg.split("@")
    needle = (".?AV" + "@".join(parts) + "@@").encode() + b"\x00"
    hits = []
    i = data.find(needle)
    while i != -1:
        hits.append(i)
        i = data.find(needle, i + 1)
    tds = []
    for off in hits:
        td_rva = off_to_rva(off)
        if td_rva is not None:
            tds.append(td_rva - 0x10)  # TypeDescriptor: vfptr(8) spare(8) name(...) -> 名前の前 16 B
    print(f"{arg}: TypeDescriptor hits={len(hits)}")
    all_ovr = set()
    for td_rva in tds:
        for col_rva in col_rvas_of_td(td_rva):
            vts = vtables_of_col(col_rva)
            base_vts = []
            for btd in base_td_rvas(col_rva):
                if btd == td_rva:
                    continue
                for bcol in col_rvas_of_td(btd):
                    base_vts.extend(vtables_of_col(bcol))
            print(f"  COL rva=0x{col_rva:x} base={[td_name(b) for b in base_td_rvas(col_rva)[1:]]}")
            for slots in vts:
                distinct = len(set(slots))
                ovr = [
                    i for i, v in enumerate(slots)
                    if not any(i < len(bv) and bv[i] == v for bv in base_vts)
                ]
                all_ovr.update(slots[i] for i in ovr)
                print(f"    vtable slots(.text)={len(slots)} distinct_fns={distinct} override_or_new={len(ovr)} inherited={len(slots) - len(ovr)}")
    print(f"  union override_or_new (distinct .text addr, all vtables of {arg}) = {len(all_ovr)}")
