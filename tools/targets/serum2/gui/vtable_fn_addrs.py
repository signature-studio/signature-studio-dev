"""SR-37 #2066: vtable_measure.py と同じ方法で、override・新規の仮想関数の .text アドレス一覧を出す。

入力: Serum2_win64.vst3 (PE, x64 MSVC)。出力: 1 行 1 アドレス (RVA、16 進) と、vtable 番号・スロット番号。
usage: vtable_fn_addrs.py <pe> <class>[@<namespace>]
"""
import struct, sys
import pefile

pe = pefile.PE(sys.argv[1])
data = open(sys.argv[1], "rb").read()
base = pe.OPTIONAL_HEADER.ImageBase
sections = [(s.VirtualAddress, s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData), s) for s in pe.sections]


def name_of(s):
    return s.Name.rstrip(b"\0").decode(errors="replace")


text = [s for s in pe.sections if name_of(s) == ".text"][0]
t_lo = base + text.VirtualAddress
t_hi = t_lo + max(text.Misc_VirtualSize, text.SizeOfRawData)


def rva_to_off(rva):
    for lo, hi, s in sections:
        if lo <= rva < hi:
            return rva - s.VirtualAddress + s.PointerToRawData
    return None


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
    out = []
    tdv = struct.pack("<I", td_rva)
    p = data.find(tdv)
    while p != -1:
        col_off = p - 12
        if col_off >= 0 and struct.unpack_from("<I", data, col_off)[0] == 1:
            col_rva = off_to_rva(col_off)
            if col_rva is not None:
                out.append(col_rva)
        p = data.find(tdv, p + 1)
    return out


def vtables_of_col(col_rva):
    res = []
    col_abs = struct.pack("<Q", base + col_rva)
    q = data.find(col_abs)
    while q != -1:
        vt_off = q + 8
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


parts = sys.argv[2].split("@")
needle = (".?AV" + "@".join(parts) + "@@").encode() + b"\x00"
i = data.find(needle)
tds = []
while i != -1:
    td_rva = off_to_rva(i)
    if td_rva is not None:
        tds.append(td_rva - 0x10)
    i = data.find(needle, i + 1)

seen = {}
for td_rva in tds:
    for col_rva in col_rvas_of_td(td_rva):
        base_vts = []
        for btd in base_td_rvas(col_rva):
            if btd == td_rva:
                continue
            for bcol in col_rvas_of_td(btd):
                base_vts.extend(vtables_of_col(bcol))
        for vi, slots in enumerate(vtables_of_col(col_rva)):
            for si, v in enumerate(slots):
                if any(si < len(bv) and bv[si] == v for bv in base_vts):
                    continue
                seen.setdefault(v - base, (col_rva, vi, si))

for rva in sorted(seen):
    col_rva, vi, si = seen[rva]
    print(f"0x{rva:x}\tCOL=0x{col_rva:x}\tvt={vi}\tslot={si}")
print(f"# total distinct = {len(seen)}")
