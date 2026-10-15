#!/usr/bin/env python3
"""ildsp (block24360_PE.bin) を native_ref_wc.c が読む RVA 配置イメージと IAT 一覧に変換する。

usage: native_image.py [PE] [--out-dir DIR]
  既定 PE: $FL_WIN64_DIR/extracted/block24360_PE.bin (tools/shared/paths.py)
  既定 DIR: tools/shared/work/raw/ildsp_native (gitignore)
出力:
  DIR/image.bin : pefile の get_memory_mapped_image() (SizeOfImage 長・RVA 配置。ImageBase は 0x180000000)
  DIR/iat.txt   : 1 行 1 件 `<IAT の RVA (hex)> <DLL>!<名前>`。native_ref_wc.c は行番号順に stub 番号を振る
"""
import sys, os, argparse
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
from paths import FL_WIN64_DIR
import pefile

ROOT = os.path.dirname(os.path.dirname(HERE))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pe", nargs="?", default=os.path.join(FL_WIN64_DIR, "extracted", "block24360_PE.bin"))
    ap.add_argument("--out-dir", default=os.path.join(ROOT, "work", "raw", "ildsp_native"))
    a = ap.parse_args()

    pe = pefile.PE(a.pe, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    base = pe.OPTIONAL_HEADER.ImageBase
    if base != 0x180000000:
        sys.exit(f"ImageBase {base:#x} != 0x180000000 (native_ref_wc.c は固定配置を前提)")

    os.makedirs(a.out_dir, exist_ok=True)
    img = pe.get_memory_mapped_image()
    if len(img) != pe.OPTIONAL_HEADER.SizeOfImage:
        sys.exit("mapped image size != SizeOfImage")
    with open(os.path.join(a.out_dir, "image.bin"), "wb") as f:
        f.write(img)

    rows = []
    for d in pe.DIRECTORY_ENTRY_IMPORT:
        dll = d.dll.decode("ascii", "replace")
        for imp in d.imports:
            name = imp.name.decode("ascii") if imp.name else f"#{imp.ordinal}"
            rows.append(f"{imp.address - base:x} {dll}!{name}")
    with open(os.path.join(a.out_dir, "iat.txt"), "w") as f:
        f.write("\n".join(rows) + "\n")
    print(f"image.bin {len(img)} bytes, iat.txt {len(rows)} imports -> {a.out_dir}")


if __name__ == "__main__":
    main()
