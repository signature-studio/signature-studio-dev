#!/usr/bin/env python3
# AggCreateInstance が構築する vtable の所属クラスを MSVC RTTI (COL) から実測する (T-SH-02, #146)。
# 使い方: FL_WIN64_DIR=<fl-win64 展開先> python3 agg2d_rtti.py [出力 JSON]
# 依存: pefile, capstone (pip install pefile capstone)。出力の既定は tools/shared/work/ (gitignore)。
# vtable VA は agg2d_vtable.py の find_ctor_and_vtable で検出する (既定 block24339 = Blend2D.dll)。
# COL (x64 の RTTICompleteObjectLocator, signature=1) は vtable[-1] が指す。
import json
import os
import struct
import sys

import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
DEFAULT_OUT = os.path.join(REPO, "tools", "shared", "work", "agg2d_rtti.json")
DLL_BLOCK = "block24339_PE.bin"


def read_cstr(data, off):
    end = data.index(b"\0", off)
    return data[off:end].decode("ascii", errors="replace")


def main():
    import capstone
    from agg2d_vtable import find_ctor_and_vtable

    root = os.environ.get("FL_WIN64_DIR")
    if not root:
        sys.exit("FL_WIN64_DIR が未設定")
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    pe = pefile.PE(os.path.join(root, "extracted", DLL_BLOCK), fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
    base = pe.OPTIONAL_HEADER.ImageBase
    data = pe.get_memory_mapped_image()
    rdata = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".rdata"][0]
    rd_lo = base + rdata.VirtualAddress
    rd_hi = rd_lo + rdata.Misc_VirtualSize

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    _ctor, vtable_va = find_ctor_and_vtable(md, pe, data, base)

    col_va = struct.unpack_from("<Q", data, vtable_va - 8 - base)[0]
    if not (rd_lo <= col_va < rd_hi):
        sys.exit(f"vtable[-1] = {hex(col_va)} が .rdata 外。COL ではない")
    col = col_va - base
    sig, _offset, _cd_offset, td_rva, cd_rva, _self_rva = struct.unpack_from("<6I", data, col)
    if sig != 1:
        sys.exit(f"COL の signature が 1 ではない: {sig}")

    td_name = read_cstr(data, td_rva + 0x10)
    chd = cd_rva
    _sig_c, _attr, num_bases, bca_rva = struct.unpack_from("<4I", data, chd)
    bases = []
    for i in range(num_bases):
        bcd_rva = struct.unpack_from("<I", data, bca_rva + 4 * i)[0]
        bcd_td = struct.unpack_from("<I", data, bcd_rva)[0]
        bases.append(read_cstr(data, bcd_td + 0x10))
    # 基底配列の先頭は自分自身 (TypeDescriptor と同じ) なので除く
    bases = bases[1:] if bases and bases[0] == td_name else bases

    # 同じ COL を指す vtable (vtable[-1] == COL VA) を .rdata 全体から数える
    same_col = []
    for rva in range(rdata.VirtualAddress, rdata.VirtualAddress + rdata.Misc_VirtualSize - 8, 8):
        if struct.unpack_from("<Q", data, rva)[0] == col_va:
            same_col.append(hex(base + rva + 8))

    text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
    text_lo = base + text.VirtualAddress
    text_hi = text_lo + text.Misc_VirtualSize

    def vtables_of(type_name):
        name_rva = data.find(b"\0" + type_name.encode() + b"\0")
        if name_rva < 0:
            return {"typedescriptor": None, "cols": 0, "vtables": []}
        td = name_rva + 1 - 0x10
        cols = []
        for p in range(rdata.VirtualAddress, rdata.VirtualAddress + rdata.Misc_VirtualSize - 24, 4):
            if struct.unpack_from("<I", data, p)[0] == 1 and struct.unpack_from("<I", data, p + 12)[0] == td \
                    and struct.unpack_from("<I", data, p + 20)[0] == p:
                cols.append(base + p)
        found = []
        for col in cols:
            for rva in range(rdata.VirtualAddress, rdata.VirtualAddress + rdata.Misc_VirtualSize - 8, 8):
                if struct.unpack_from("<Q", data, rva)[0] == col:
                    vt = base + rva + 8
                    n = 0
                    while text_lo <= struct.unpack_from("<Q", data, vt - base + 8 * n)[0] < text_hi:
                        n += 1
                    found.append({"vtable_va": hex(vt), "slots": n})
        return {"typedescriptor": hex(base + td), "cols": len(cols), "vtables": found}

    result = {
        "dll_block": DLL_BLOCK,
        "vtable_va": hex(vtable_va),
        "col_va": hex(col_va),
        "type_name": td_name,
        "base_classes": bases,
        "vtables_with_same_col": same_col,
        "vtables_by_class": {
            name: vtables_of(name) for name in [td_name] + bases
        },
    }
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
