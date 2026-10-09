#!/usr/bin/env python3
# M2-1: universal2 (FAT Mach-O) から指定アーキテクチャの slice を切出し、
# サイズ / arch 一覧 / slice 内 .text セクション情報を slice_inventory.json に記録する。
#
# lipo に依存しない (fat ヘッダ解析と切出しは self-contained)。python struct のみ使用。
#
# 使い方:
#   python3 extract_slice.py --input FLEngine_x64.dylib --output-dir work --arch x86_64
#
# 出力:
#   <output-dir>/FLEngine_x86_64.dylib   (arch が x86_64 甲乙あれば "FLEngine_<arch>.dylib")
#   <output-dir>/slice_inventory.json
# exit 0 / 失敗は非ゼロ。

import json
import os
import struct
import sys

# FAT Mach-O big-endian マジック (universal2/PPC 世代共通)。
FAT_MAGIC = 0xCAFEBABE
FAT_MAGIC_64 = 0xCAFEBABF
FAT_CIGAM_LE = 0xBEBAFECA  # little-endian 誤読時の検出用

# Mach-O slice 内部 (little-endian, 64bit) を読むための定数。
MH_MAGIC = 0xFEEDFACF          # 64bit
MH_CIGAM = 0xCFFAEDFE          # バイトスワップ時
MH_MAGIC_32 = 0xFEEDFACE

LC_SEGMENT_64 = 0x19
CPU_TYPE_NAMES = {
    0x00000007: "x86",
    0x01000007: "x86_64",
    0x0000000C: "arm",
    0x0100000C: "arm64",
    0x00000012: "powerpc",
    0x01000012: "ppc64",
}


def die(msg: str) -> None:
    print(f"[extract_slice] FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def parse_fat_header(data: bytes):
    """universal2 ヘッダを解析して arch エントリ一覧を返す。"""
    if len(data) < 8:
        die("ファイルが小さすぎて FAT ヘッダが読めません")
    (magic,) = struct.unpack(">I", data[0:4])
    if magic != FAT_MAGIC:
        # mac の本来のエンディアンで無い場合も報告する
        (le_magic,) = struct.unpack("<I", data[0:4])
        if le_magic == FAT_MAGIC:
            die("FAT ヘッダは big-endian です (読み方の前提違い)")
        die(f"FAT Mach-O マジックが一致しません: {hex(magic)} (universal2 以外の可能性)")

    (narch,) = struct.unpack(">I", data[4:8])
    archs = []
    if magic == FAT_MAGIC:
        entry_size = 20
    else:  # FAT_MAGIC_64 は ANSI 64bit fat (今回の対象外だが一念で対応)
        entry_size = 32
    for i in range(narch):
        off = 8 + i * entry_size
        if off + entry_size > len(data):
            die(f"arch エントリ {i} がヘッダ範囲外です (universal2 破損の可能性)")
        if entry_size == 20:
            cputype, cpusub, offset, size, align = struct.unpack(">5I", data[off:off + 20])
        else:
            cputype, cpusub = struct.unpack(">I I", data[off:off + 8])
            offset, size = struct.unpack(">Q Q", data[off + 8:off + 24])
            align = 0
        archs.append({
            "index": i,
            "cputype": cputype,
            "cpusubtype": cpusub,
            "arch": CPU_TYPE_NAMES.get(cputype, f"cpu_{hex(cputype)}"),
            "offset": offset,
            "slice_size": size,
            "align": 1 << (align if align < 32 else 0),
        })
    return archs


def parse_macho_text_section(slice_data: bytes):
    """切出した slice の Mach-O ヘッダから __text セクションの RVA/size を返す。"""
    if len(slice_data) < 8:
        die("slice が小さすぎて Mach-O ヘッダが読めません")
    (m_magic,) = struct.unpack("<I", slice_data[0:4])
    swapped = False
    if m_magic == MH_MAGIC:
        pass
    elif m_magic == MH_CIGAM:
        swapped = True
    else:
        (be_magic,) = struct.unpack(">I", slice_data[0:4])
        if be_magic == MH_MAGIC:
            swapped = True
        else:
            die(f"slice 先頭が Mach-O 64bit マジックではありません: {hex(m_magic)}")
    if swapped:
        unpacker = ">"
    else:
        unpacker = "<"

    cputype, cpusub, filetype, ncmds, sizeofcmds, flags, _reserved = struct.unpack(
        unpacker + "IiIIIII", slice_data[4:32])
    pos = 32
    loadcmds = []
    segments = []
    for _ in range(ncmds):
        if pos + 8 > len(slice_data):
            die("load command の途中でファイルが尽きました")
        (cmd, cmdsize) = struct.unpack(unpacker + "II", slice_data[pos:pos + 8])
        loadcmds.append(cmd)
        if cmd == LC_SEGMENT_64:
            segname = slice_data[pos + 8:pos + 24].split(b"\0")[0].decode("ascii", "replace")
            # LC_SEGMENT_64: cmd(0) cmdsize(4) segname(8..24) vmaddr(24) vmsize(32)
            #   fileoff(40) filesize(48) maxprot(56) initprot(60) nsects(64) flags(68)
            #   sections start at pos+72
            nsects, = struct.unpack(unpacker + "I", slice_data[pos + 64: pos + 68])
            sect_base = pos + 72
            if cmdsize < 72 + nsects * 80:
                die(f"LC_SEGMENT_64 cmdsize が不整合です (nsects={nsects})")
            for s in range(nsects):
                so = sect_base + s * 80
                if so + 80 > len(slice_data):
                    die("section header の途中でファイルが尽きました")
                sectname = slice_data[so:so + 16].split(b"\0")[0].decode("ascii", "replace")
                saddr, ssize = struct.unpack(unpacker + "QQ", slice_data[so + 32:so + 48])
                segments.append({"segment": segname, "section": sectname,
                                 "vmaddr": saddr, "size": ssize})
        pos += cmdsize

    text = next((s for s in segments if s["segment"] == "__TEXT" and s["section"] == "__text"),
                None)
    info = {
        "cputype": cputype,
        "arch": CPU_TYPE_NAMES.get(cputype, f"cpu_{hex(cputype)}"),
        "load_commands": {hex(c): loadcmds.count(c) for c in set(loadcmds)},
        "has_lc_segment_64": LC_SEGMENT_64 in loadcmds,
        "__text_section": ({"vmaddr": text["vmaddr"], "size": text["size"]}
                           if text is not None else None),
        "__TEXT_segments": [s for s in segments if s["segment"] == "__TEXT"],
    }
    if text is None:
        info["warning"] = "__TEXT,__text セクションが見つかりませんでした"
    return info


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="universal2 slice extractor (lipo 非依存)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--arch", default="x86_64",
                    help="切出すアーキテクチャ名 (x86_64 / arm64 など)")
    ap.add_argument("--output-name", default=None,
                    help="出力ファイル名 (既定: FLEngine_<arch>.dylib)")
    args = ap.parse_args()

    path = args.input
    if not os.path.isfile(path):
        die(f"入力ファイルがありません: {path}")
    with open(path, "rb") as fh:
        data = fh.read(65536)
    archs = parse_fat_header(data)

    target = next((a for a in archs if a["arch"] == args.arch), None)
    if target is None:
        die(f"アーキテクチャ {args.arch} はこの universal2 に含まれません: "
            f"{[a['arch'] for a in archs]}")

    inst_size = os.path.getsize(path)
    if inst_size < target["offset"] + target["slice_size"]:
        die(f"slice 範囲 (offset={target['offset']} size={target['slice_size']}) が"
            f"ファイル末尾 ({inst_size}) に届きません")

    # 切出し (検証込みで 2 パス: 先頭 64KB でヘッダ確認済みなので全量読み出す)
    with open(path, "rb") as fh:
        fh.seek(target["offset"])
        slice_data = fh.read(target["slice_size"])
    if len(slice_data) != target["slice_size"]:
        die("slice 読み出しサイズが一致しません")

    with open(path, "rb") as fh:
        fh.seek(target["offset"])
        head64 = fh.read(8192)
    macho_info = parse_macho_text_section(head64)
    if macho_info["arch"] != args.arch:
        die(f"slice 内 Mach-O の cputype が不一致: {macho_info['arch']} != {args.arch}")

    os.makedirs(args.output_dir, exist_ok=True)
    out_name = args.output_name or f"FLEngine_{args.arch}.dylib"
    out_path = os.path.join(args.output_dir, out_name)
    with open(out_path, "wb") as fh:
        fh.write(slice_data)

    inventory = {
        "source_universal2": {
            "path": path,
            "file_size": inst_size,
            # FAT エントリ一覧 (lipo 相当確認)
            "archs": [
                {"index": a["index"], "arch": a["arch"], "cputype": hex(a["cputype"]),
                 "cpusubtype": a["cpusubtype"], "offset": a["offset"],
                 "slice_size": a["slice_size"], "align": a["align"]}
                for a in archs
            ],
        },
        "extracted": {
            "arch": args.arch,
            "output_path": out_path,
            "output_size": target["slice_size"],
            "cputype": hex(macho_info["cputype"]),
            "load_commands": macho_info["load_commands"],
            "__text_section": macho_info["__text_section"],
        },
    }
    if "warning" in macho_info:
        inventory["extracted"]["warning"] = macho_info["warning"]
    base, _ = os.path.splitext(out_name)
    if args.output_name:
        inv_name = f"{base}_slice_inventory.json"
    else:
        # 既定 (FLEngine) 成果物は従来どおり slice_inventory.json に記録する
        inv_name = "slice_inventory.json"
    inv_path = os.path.join(args.output_dir, inv_name)
    with open(inv_path, "w") as fh:
        json.dump(inventory, fh, ensure_ascii=False, indent=2)

    t = macho_info["__text_section"]
    print("[extract_slice] universal2 archs:",
          ", ".join(f"{a['arch']}(size={a['slice_size']})" for a in archs))
    print(f"[extract_slice] extracted {args.arch}: {out_path} "
          f"({target['slice_size']} bytes)")
    if t is not None:
        print(f"[extract_slice] __TEXT,__text vmaddr=0x{t['vmaddr']:x} size={t['size']}")
    print(f"[extract_slice] inventory: {inv_path}")
    return 0


if __name__ == "__main__":
    main()
