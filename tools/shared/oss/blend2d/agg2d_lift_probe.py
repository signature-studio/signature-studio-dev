#!/usr/bin/env python3
# Agg2D vtable の 79 root を flelift の lifter (x64c) に通したときの lift 可否を実測する (T-SH-02, #146)。
# 使い方: FL_WIN64_DIR=<fl-win64 展開先> python3 agg2d_lift_probe.py [出力 JSON]
# 依存: pefile, capstone。出力の既定は tools/shared/work/ (gitignore)。
# 閉包の深さ (--closure) を 0 / 1 / 3 / 50 で変え、直接 call の先を lift に含めたときの件数を見る。
# 50 は直接 call の閉包を使い切る深さ (unlifted callee が 0 になる)。
# x64c の CFG 間接 call の扱いも検証する: 生成 C の間接 dispatch の宛先値が dispatch 表に載っているかを見る。
import json
import os
import re
import struct
import subprocess
import sys
from collections import Counter

import pefile

from agg2d_vtable import DLL_BLOCK, VTABLE_VA

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
X64C = os.path.join(REPO, "tools", "flelift", "x64c.py")
WORK = os.path.join(REPO, "tools", "shared", "work")
DEFAULT_OUT = os.path.join(WORK, "agg2d_lift_probe.json")
DEPTHS = (0, 1, 3, 50)


def vtable_roots(data, base, text_lo, text_hi):
    roots = []
    off = VTABLE_VA - base
    while True:
        v = struct.unpack_from("<Q", data, off + 8 * len(roots))[0]
        if not (text_lo <= v < text_hi):
            break
        roots.append(v)
    return sorted(set(roots))


def indirect_dispatch(src, pe, base):
    sites = Counter(re.findall(r"uint64_t t_ = LD64\((0x[0-9a-f]+)ULL\)", src))
    out = {}
    for addr_s in sorted(sites):
        slot = int(addr_s, 16)
        value = int.from_bytes(pe.get_data(slot - base, 8), "little")
        head = pe.get_data(value - base, 2).hex()
        out[addr_s] = {
            "slot_value": hex(value),
            "target_bytes": head,
            "value_in_dispatch_table": ("case %s" % hex(value) + "ULL") in src,
            "sites": sites[addr_s],
        }
    return out


def main():
    root = os.environ.get("FL_WIN64_DIR")
    if not root:
        sys.exit("FL_WIN64_DIR が未設定")
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    path = os.path.join(root, "extracted", DLL_BLOCK)
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    size = pe.OPTIONAL_HEADER.SizeOfImage
    data = pe.get_memory_mapped_image()
    text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
    text_lo = base + text.VirtualAddress
    roots = vtable_roots(data, base, text_lo, text_lo + text.Misc_VirtualSize)
    os.makedirs(WORK, exist_ok=True)
    roots_path = os.path.join(WORK, "agg2d_roots.json")
    with open(roots_path, "w") as fh:
        json.dump({"roots": roots, "calltgt": []}, fh)

    result = {"dll_block": DLL_BLOCK, "image_base": hex(base), "size_of_image": hex(size), "roots": len(roots), "depths": {}}
    for depth in DEPTHS:
        outdir = os.path.join(WORK, "agg2d_lift_c%d" % depth)
        subprocess.run(
            [sys.executable, X64C, "--pe", path, "--entries", roots_path, "--out", outdir,
             "--closure", str(depth), "--img", hex(base), "--shift", "0", "--img-size", hex(size),
             "--impbase", "0x1D80000"],
            check=True, capture_output=True, text=True,
        )
        with open(os.path.join(outdir, "lift_meta.json")) as fh:
            meta = json.load(fh)
        with open(os.path.join(outdir, "fle_lifted.c")) as fh:
            src = fh.read()
        unsup = meta["unsup"]
        result["depths"][str(depth)] = {
            "functions": len(meta["functions"]),
            "insns": meta["ninsn"],
            "unsup_sites": sum(unsup.values()),
            "unsup_mnemonics": len(unsup),
            "unsup_top": sorted(unsup.items(), key=lambda kv: -kv[1])[:6],
            "unlifted_callees": sum(meta["unlifted_callees"].values()),
            "imports_used": len(meta["imports_used"]),
            "indirect_dispatch": indirect_dispatch(src, pe, base),
        }

    with open(out, "w") as fh:
        json.dump(result, fh, indent=1)
    for depth in DEPTHS:
        d = result["depths"][str(depth)]
        print("closure=%d funcs=%d insns=%d unsup_sites=%d unsup_mnem=%d unlifted=%d imports=%d" % (
            depth, d["functions"], d["insns"], d["unsup_sites"], d["unsup_mnemonics"], d["unlifted_callees"], d["imports_used"]))
    last = result["depths"][str(DEPTHS[-1])]["indirect_dispatch"]
    for addr, v in last.items():
        print("indirect dispatch slot %s: value %s bytes %s in_table=%s sites=%d" % (
            addr, v["slot_value"], v["target_bytes"], v["value_in_dispatch_table"], v["sites"]))
    print("wrote", out)


if __name__ == "__main__":
    main()
