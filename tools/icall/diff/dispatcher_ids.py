#!/usr/bin/env python3
"""UCRT 遅延解決ディスパッチャ (try_get_function 相当) の呼び出し側から、T1/T2 の index 域を静的に集める (#2225)。

用法: python3 tools/icall/diff/dispatcher_ids.py <PE> [dispatcher T1 T2 module_names]   (16 進 VA。既定 = SlateCore.core_64)
  SlateCore.core_64: 既定値 (0x18105de80 0x181307100 0x1813071a0 0x181134720)
  OTT_vst2_win64.dll: 0x1801c38c8 0x18026c950 0x18026c9f0 0x21e500 を VA 化した 0x18021e500
出力:
  T2 (encoded 関数ポインタ表 0x1813071a0): call site ごとの ecx 即値 (function_id) と、その最大値。
  T1 (module handle 表 0x181307100): module_names 配列 0x181134720 の連続する有効ポインタの数と、
    各 call site が渡す module id 列 (r8..r9 の 4 B 配列) の最大値。
  表の隣接関係: T1 起点と T2 起点の差。
  T1/T2 の起点を `lea` で参照する関数 (CRT の winapi_thunks 初期化・終了関数) の逆アセンブル全体。
  初期化関数の `rep stos` 個数 (`and ecx, N`) が T2 の entry 数、終了関数のループ終点が T1 の終点。
call site は .pdata の関数境界内を capstone で線形に逆アセンブルして `call 0x18105de80` を拾う。
ecx は同じ関数内で直前に書かれた `mov ecx, imm` / `xor ecx, ecx` だけを即値として扱う (それ以外は「非即値」)。
"""
import struct
import sys

import capstone
import pefile

DISPATCH, T1, T2, MODULE_NAMES = 0x18105DE80, 0x181307100, 0x1813071A0, 0x181134720


def imm(s):
    try:
        return int(s, 0)
    except ValueError:
        return None


def main(path):
    pe = pefile.PE(path)
    base = pe.OPTIONAL_HEADER.ImageBase
    img = pe.get_memory_mapped_image()

    def rd(va, n):
        return img[va - base:va - base + n]

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    text = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
    t_lo, t_hi = base + text.VirtualAddress, base + text.VirtualAddress + text.Misc_VirtualSize
    funcs = sorted((base + e.struct.BeginAddress, base + e.struct.EndAddress)
                   for e in pe.DIRECTORY_ENTRY_EXCEPTION if t_lo <= base + e.struct.BeginAddress < t_hi)

    sites = []
    table_funcs = {}
    for lo, hi in funcs:
        ecx, r8, r9 = "非即値", None, None
        body = list(md.disasm(rd(lo, hi - lo), lo))
        for i in body:
            if i.mnemonic == "lea" and "[rip" in i.op_str and (i.address + i.size + i.disp) in (T1, T2):
                table_funcs[lo] = body
        for i in body:
            ops = i.op_str.replace(" ", "")
            if i.mnemonic == "call" and ops == hex(DISPATCH):
                sites.append((i.address, lo, ecx, r8, r9))
                ecx, r8, r9 = "非即値", None, None
            elif i.mnemonic == "mov" and ops.startswith("ecx,") and imm(ops[4:]) is not None:
                ecx = imm(ops[4:])
            elif i.mnemonic == "xor" and ops == "ecx,ecx":
                ecx = 0
            elif i.mnemonic in ("mov", "lea", "xor", "add", "sub", "movzx", "movsx") and ops.startswith(("ecx,", "rcx,")):
                ecx = "非即値"
            elif i.mnemonic == "lea" and ops.startswith("r8,[rip"):
                r8 = i.address + i.size + i.disp
            elif i.mnemonic == "lea" and ops.startswith("r9,[rip"):
                r9 = i.address + i.size + i.disp
    print("call site 数:", len(sites))
    ids = []
    mids = []
    for a, lo, ecx, r8, r9 in sites:
        mod = ""
        if r8 and r9 and 0 < r9 - r8 <= 64:
            lst = list(struct.unpack("<%dI" % ((r9 - r8) // 4), rd(r8, r9 - r8)))
            mids += lst
            mod = "module_id=%s" % lst
        print("  call %#x (func %#x) ecx=%s %s" % (a, lo, hex(ecx) if isinstance(ecx, int) else ecx, mod))
        if isinstance(ecx, int):
            ids.append(ecx)
    print("T2 function_id: 即値 %d 件・distinct %d・最大 %d → T2 は少なくとも %d entry" % (
        len(ids), len(set(ids)), max(ids), max(ids) + 1))
    print("T1 module_id (call site が渡す列): distinct %s・最大 %d → T1 は少なくとも %d entry" % (
        sorted(set(mids)), max(mids), max(mids) + 1))

    for lo, body in sorted(table_funcs.items()):
        print("T1/T2 起点を lea で参照する関数 %#x:" % lo)
        for i in body:
            tgt = ("  # %#x" % (i.address + i.size + i.disp)) if "[rip" in i.op_str else ""
            print("  %#x: %s %s%s" % (i.address, i.mnemonic, i.op_str, tgt))
            if i.mnemonic == "ret":
                break

    n = 0
    while True:
        p = struct.unpack("<Q", rd(MODULE_NAMES + 8 * n, 8))[0]
        if not (base <= p < base + pe.OPTIONAL_HEADER.SizeOfImage):
            break
        w = rd(p, 120)
        s = w.decode("utf-16le", errors="replace").split("\0")[0]
        print("  module_names[%d] = %#x %r" % (n, p, s))
        n += 1
    print("module_names (0x%x) の連続する有効ポインタ: %d 件 (終端 = %#x)" % (MODULE_NAMES, n, MODULE_NAMES + 8 * n))
    print("T1 起点 %#x と T2 起点 %#x の差: %#x B = %d entry (8 B)" % (T1, T2, T2 - T1, (T2 - T1) // 8))


if __name__ == "__main__":
    if len(sys.argv) == 6:
        DISPATCH, T1, T2, MODULE_NAMES = (int(a, 16) for a in sys.argv[2:6])
    main(sys.argv[1])
