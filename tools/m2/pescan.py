#!/usr/bin/env python3
# M2: PE32+ (win64 FLEEngine_x64.dll) の静的解析基盤スキャン。
#
# 出すもの (json):
#   sections      : セクション一覧 (name, vaddr, vsize, raw)
#   imports       : DLL 名 → シンボル一覧 (llvm-objdump -p 解析)
#   exports       : エクスポート名 → RVA (EDATA を生で解析)
#   pdata         : RUNTIME_FUNCTION 一覧 (begin/end/unwind RVA) — Delphi x64
#                   table-based SEH の静的関数境界 (strategy §5.7 #1 の正)
#   unwind_flags  : 各 unwind 情報の flags (EHANDLER/UHANDLER/CHAININFO)
#
# 依存: llvm-objdump が PATH にあること。入力は PE32+ x64 のみ。
#
#   python3 pescan.py --input FLEngine_x64.dll --out work/pe_scan_dll.json

import argparse
import json
import re
import struct
import subprocess
import sys


def die(msg: str):
    print(f"[pescan] FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def parse_pe_sections(data):
    pe_off, = struct.unpack("<I", data[0x3C:0x40])
    if data[pe_off:pe_off + 4] != b"PE\0\0":
        die("PE シグネチャ不一致")
    opt_off = pe_off + 24
    if struct.unpack("<H", data[opt_off:opt_off + 2])[0] != 0x20B:
        die("PE32+ (0x20b) 以外は非対応")
    nsec, = struct.unpack("<H", data[pe_off + 6:pe_off + 8])
    optsz, = struct.unpack("<H", data[pe_off + 20:pe_off + 22])
    sec_off = opt_off + optsz
    sections = []
    for i in range(nsec):
        e = sec_off + i * 40
        name = data[e:e + 8].split(b"\0")[0].decode("latin1")
        vsize, vaddr, raw_size, raw_ptr = struct.unpack("<IIII", data[e + 8:e + 24])
        sections.append({"name": name, "vsize": vsize, "vaddr": vaddr,
                         "raw_size": raw_size, "raw_ptr": raw_ptr})
    return sections


def file_off(data, sections, rva):
    """RVA (データディレクトリ値) → ファイルオフセット"""
    for s in sections:
        if s["raw_size"] and s["vaddr"] <= rva < s["vaddr"] + s["vsize"]:
            off = rva - s["vaddr"]
            if off < s["raw_size"]:
                return s["raw_ptr"] + off
    return None


def data_dir(data, sections, index):
    """data directory [index] の (rva, size)。PE32+ optional header + 112 から。"""
    pe_off, = struct.unpack("<I", data[0x3C:0x40])
    opt_off = pe_off + 24
    dd = opt_off + 112
    rva, size = struct.unpack("<II", data[dd + 8 * index: dd + 8 * index + 8])
    return rva, size


def read_cstr(data, off, limit=256):
    if off is None or off <= 0 or off >= len(data):
        return ""
    end = data.find(b"\0", off, off + limit)
    return data[off:end].decode("latin1", "replace")


def parse_imports(text):
    """llvm-objdump -p の Import Tables 部から (dll, symbol) 一覧を獲る。"""
    imports = []
    in_import = False
    cur_dll = None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("The Import Tables"):
            in_import = True
            continue
        if not in_import:
            continue
        if s.startswith("The Delay Import Tables") or s.startswith("Start Address") \
                or s.startswith("Sections:") or s.startswith("The Export Tables"):
            in_import = False
            cur_dll = None
            continue
        if s.startswith("DLL Name:"):
            cur_dll = s.split(":", 1)[1].strip()
            continue
        if cur_dll and s and s[0].isdigit():
            parts = s.split()
            if len(parts) == 2:
                imports.append({"dll": cur_dll, "name": parts[1]})
    return imports


def parse_edata(data, sections):
    exp_rva, exp_size = data_dir(data, sections, 0)
    if not exp_rva:
        return {}
    base = file_off(data, sections, exp_rva)
    if base is None:
        die(f"Export Directory RVA {hex(exp_rva)} がファイル内にありません")
    (_fl, _ts, _mj, _mi, _name_rva, _ordbase,
     naddr, nnames, af_rva, an_rva, ao_rva) = struct.unpack(
        "<IIHHIIIIIII", data[base:base + 40])

    af = file_off(data, sections, af_rva)
    an = file_off(data, sections, an_rva)
    ao = file_off(data, sections, ao_rva)
    if af is None or an is None or ao is None:
        die("Export tables (AddressTable/NameTable/OrdinalTable) がファイル内にありません")

    def r4(o):
        return struct.unpack("<I", data[o:o + 4])[0]

    funcs = [r4(af + i * 4) for i in range(naddr)]
    names = []
    for i in range(nnames):
        no = file_off(data, sections, r4(an + i * 4))
        if no is not None:
            names.append(read_cstr(data, no))
    out = {}
    for i, nm in enumerate(names):
        oi = struct.unpack("<H", data[ao + i * 2: ao + i * 2 + 2])[0]
        rva = funcs[oi] if 0 <= oi < len(funcs) else None
        out[nm] = rva
    return out


UNW_FLAG_EHANDLER = 0x1
UNW_FLAG_UHANDLER = 0x2
UNW_FLAG_CHAININFO = 0x4


def parse_iat_slots(data, sections):
    """Import Directory (entry 1) 遅延含まず — IAT slot RVA → (dll, name)。"""
    imp_rva, imp_size = data_dir(data, sections, 1)
    out = {}
    if not imp_rva:
        return out
    off = file_off(data, sections, imp_rva)
    if off is None:
        return out
    dllnames = {}

    while True:
        oft, _ts, _fc, name_rva, ft = struct.unpack("<IIIII", data[off:off + 20])
        if oft == 0 and name_rva == 0 and ft == 0:
            break
        dll = read_cstr(data, file_off(data, sections, name_rva) or 0)
        # どちらか: OriginalFirstThunk (.name address table) または FirstThunk の立たない場合
        walk = oft if oft else ft
        i = 0
        while True:
            entry = struct.unpack("<Q", data[file_off(data, sections, walk + i * 8):
                                             file_off(data, sections, walk + i * 8) + 8])[0]
            if entry == 0:
                break
            if not (entry & (1 << 63)):
                hno = file_off(data, sections, entry & 0xFFFFFFFF)
                nm = read_cstr(data, (hno if hno is not None else 0) + 2)
                out[ft + i * 8] = (dll, nm)
            i += 1
        off += 20
        if len(out) > 100000:
            break
    return out


def parse_delay_iat_slots(data, sections):
    """Delay Import Directory (entry 13) — IAT slot RVA → (dll, name)。"""
    d_rva, d_size = data_dir(data, sections, 13)
    out = {}
    if not d_rva:
        return out
    off = file_off(data, sections, d_rva)
    if off is None:
        return out
    while True:
        attrs, dll_rva, hmod, iat_rva, int_rva, _b, _u, _ts = struct.unpack(
            "<IIIIIIII", data[off:off + 32])
        if dll_rva == 0 and iat_rva == 0:
            break
        dll = read_cstr(data, file_off(data, sections, dll_rva) or 0)
        has_bound = (attrs & 0x1) == 0  # 従来構造 (rva) のとき
        if iat_rva:
            i = 0
            while True:
                fo = file_off(data, sections, iat_rva + i * 8)
                if fo is None:
                    break
                entry = struct.unpack("<Q", data[fo:fo + 8])[0]
                if entry == 0:
                    break
                if int_rva:
                    no = file_off(data, sections, int_rva + i * 8)
                    if no is not None:
                        e2 = struct.unpack("<Q", data[no:no + 8])[0]
                        if e2 and not (e2 & (1 << 63)):
                            nm = read_cstr(data, (file_off(data, sections, e2 & 0xFFFFFFFF)
                                             or 0) + 2)
                            out[iat_rva + i * 8] = (dll, nm)
                i += 1
        off += 32
        if len(out) > 100000:
            break
    return out


def parse_pdata(data, sections):
    """Exception Directory (.pdata) → RUNTIME_FUNCTION 一覧 + unwind flags。"""
    exc_rva, exc_size = data_dir(data, sections, 3)
    if not exc_rva or not exc_size:
        return [], {}
    base = file_off(data, sections, exc_rva)
    if base is None:
        die(".pdata がファイル内にありません")
    entries = []
    while base + len(entries) * 12 + 12 <= len(data):
        b, e, u = struct.unpack("<III", data[base + len(entries) * 12:
                                           base + len(entries) * 12 + 12])
        if b == 0:
            break
        tag = "none"
        if u:
            ua = file_off(data, sections, u)
            if ua is None:
                tag = "unreadable"
            else:
                f = (data[ua] >> 3) & 0xF
                parts = []
                if f & UNW_FLAG_EHANDLER:
                    parts.append("EHANDLER")
                if f & UNW_FLAG_UHANDLER:
                    parts.append("UHANDLER")
                if f & UNW_FLAG_CHAININFO:
                    parts.append("CHAININFO")
                tag = ",".join(parts) if parts else "PLAIN"
        entries.append({"begin": b, "end": e, "unwind": u, "flag": tag})
    summary = {}
    for en in entries:
        summary[en["flag"]] = summary.get(en["flag"], 0) + 1
    return entries, summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    data = open(args.input, "rb").read()
    sections = parse_pe_sections(data)
    text = subprocess.check_output(
        ["llvm-objdump", "-p", args.input], text=True, errors="replace")
    imports = parse_imports(text)
    exports = parse_edata(data, sections)
    pdata, unwind_summary = parse_pdata(data, sections)
    iat = parse_iat_slots(data, sections)
    diat = parse_delay_iat_slots(data, sections)
    print(f"[pescan] iat slots={len(iat)} delay-iat slots={len(diat)}")

    imp_by_dll = {}
    for it in imports:
        imp_by_dll.setdefault(it["dll"], []).append(it["name"])

    out = {
        "file": args.input,
        "file_size": len(data),
        "sections": sections,
        "imports": imp_by_dll,
        "import_count": len(imports),
        "imports_dll_count": len(imp_by_dll),
        "iat_slots": {hex(k): v for k, v in sorted(iat.items())},
        "iat_delay_slots": {hex(k): v for k, v in sorted(diat.items())},
        "exports": exports,
        "pdata": pdata,
        "pdata_count": len(pdata),
        "unwind_flag_summary": unwind_summary,
    }
    total = sum((e["end"] - e["begin"]) for e in pdata if e["end"] >= e["begin"])
    out["pdata_text_covered_bytes"] = total

    with open(args.out, "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print(f"[pescan] sections={len(sections)} import_names={len(imports)}"
          f"({len(imp_by_dll)} DLLs) exports={len(exports)} "
          f"pdata={len(pdata)} text_covered={total}")
    print(f"[pescan] unwind flags: {unwind_summary}")
    print(f"[pescan] wrote {args.out}")


if __name__ == "__main__":
    main()
