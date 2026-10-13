#!/usr/bin/env python3
# Blend2D.dll (FL 同梱) の Agg2D glue 棚卸し。export / RTTI クラス名 / import を実測して JSON に出す。
# 使い方: FL_WIN64_DIR=<fl-win64 展開先> python3 agg2d_inventory.py [出力 JSON]
# 依存: pefile (pip install pefile)。出力の既定は tools/shared/work/ (gitignore)。
import json
import os
import re
import sys
from collections import Counter

import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
DEFAULT_OUT = os.path.join(REPO, "tools", "shared", "work", "agg2d_inventory.json")
DLL_NAME = "Blend2D.dll"
# tools/shared/scripts/classify.py の win=("Blend2D.dll", 24339) が正。
# AggCreateInstance は dsp_ippv2 (block24356) も export するため、名前ではなくブロック番号で固定する。
DLL_BLOCK = "block24339_PE.bin"


def main():
    root = os.environ.get("FL_WIN64_DIR")
    if not root:
        sys.exit("FL_WIN64_DIR が未設定")
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    path = os.path.join(root, "extracted", DLL_BLOCK)
    if not os.path.isfile(path):
        sys.exit("%s が無い" % path)
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories(directories=[
        pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"],
        pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
    ])
    exports = []
    if hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
        exports = [s.name.decode() for s in pe.DIRECTORY_ENTRY_EXPORT.symbols if s.name]
    imports = {}
    for d in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
        imports[d.dll.decode()] = [
            (i.name.decode() if i.name else "ord%s" % i.ordinal) for i in d.imports]
    with open(path, "rb") as f:
        blob = f.read()
    strs = re.findall(rb"[\x20-\x7e]{6,}", blob)
    rtti = sorted({m.decode() for s in strs for m in re.findall(rb"\.\?AV[^@]+@[^\x00]*", s)})
    agg_rtti = [r for r in rtti if "Agg2D" in r]
    result = {
        "dll": DLL_NAME,
        "sha256_16": __import__("hashlib").sha256(blob).hexdigest()[:16],
        "size": len(blob),
        "sections": [(s.Name.rstrip(b"\0").decode(), s.Misc_VirtualSize) for s in pe.sections],
        "exports": exports,
        "imports": {k: len(v) for k, v in imports.items()},
        "rtti_class_count": len(rtti),
        "rtti_agg2d": agg_rtti,
        "rtti_prefix_counts": dict(Counter(r.split("@")[0][:6] for r in rtti).most_common(10)),
        "bl_string_count": sum(1 for s in strs if re.match(rb"^bl[A-Z]", s)),
    }
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: result[k] for k in ("sha256_16", "size", "exports", "rtti_class_count", "rtti_agg2d", "bl_string_count")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
