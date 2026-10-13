#!/usr/bin/env python3
"""dir64_boundary_check.py — m6_data_gen.py / liftlib dataimage.py の生成物で DIR64 slot (末尾 8B 含む) が補正されたかを実バイトで検査 (#593)。

独立算法: pefile の DIRECTORY_ENTRY_BASERELOC で DIR64 を列挙し (生成器は .reloc を手でパース)、
slot が section (VirtualSize) に完全に収まり値が image 内のものを「補正されるべき slot」とする。
生成 C の dlld_<sec>[] を復元し、各 slot が `v - IMG + VA_BASE` になっているかを見る。
  python3 dir64_boundary_check.py PE --gen {m6,liftlib} [--va-base 0x30000000] [--expect-missed N] [--expect-final-slot-fixed 0|1]
期待と違えば exit 1。
"""
import argparse
import os
import re
import struct
import subprocess
import sys
import tempfile

import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
T = os.path.abspath(os.path.join(HERE, ".."))


def parse_c(txt):
    out = {}
    for m in re.finditer(r"static const unsigned char dlld_(\w+)\[\] = \{\n(.*?)\n\};", txt, re.S):
        out["." + m.group(1).lstrip("_")] = bytes(int(x, 16) for x in re.findall(r"0x([0-9a-f]{2})", m.group(2)))
    return out


def gen(kind, pe_path, va_base, m6_py, dataimage_dir):
    if kind == "m6":
        with tempfile.TemporaryDirectory() as td:
            outc = os.path.join(td, "m6_data.c")
            env = dict(os.environ, M6_PE=pe_path, M6_DATA_OUT=outc, M6_IMG_BASE=hex(pefile.PE(pe_path, fast_load=True).OPTIONAL_HEADER.ImageBase))
            r = subprocess.run([sys.executable, m6_py], env=env, capture_output=True, text=True)
            if r.returncode != 0:
                print("[check] FAIL: m6_data_gen 失敗\n" + r.stderr[-400:])
                sys.exit(1)
            return open(outc).read()
    sys.path.insert(0, dataimage_dir)
    from liftlib.pe import Image
    from liftlib.passes import dataimage
    return dataimage.gen_data_c(Image(pe_path), va_base=va_base)[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pe")
    ap.add_argument("--gen", choices=("m6", "liftlib"), required=True)
    ap.add_argument("--va-base", default="0x30000000")
    ap.add_argument("--m6-py", default=os.path.join(T, "m6", "m6_data_gen.py"))
    ap.add_argument("--liftlib-dir", default=HERE)
    ap.add_argument("--expect-missed", type=int, default=0)
    a = ap.parse_args()
    VA = int(a.va_base, 0)
    pe = pefile.PE(a.pe)
    IMG, SZ = pe.OPTIONAL_HEADER.ImageBase, pe.OPTIONAL_HEADER.SizeOfImage
    mm = pe.get_memory_mapped_image()
    secs = {s.Name.rstrip(b"\0").decode(): (s.VirtualAddress, s.Misc_VirtualSize) for s in pe.sections}
    relocs = [e.rva for b in pe.DIRECTORY_ENTRY_BASERELOC for e in b.entries if e.type == 10]
    gen_c = parse_c(gen(a.gen, a.pe, VA, a.m6_py, a.liftlib_dir))
    should = missed = bad = final = final_fixed = 0
    for n in (".rdata", ".data"):
        lo, vs = secs[n]
        out = gen_c[n]
        for r in relocs:
            if not (lo <= r and r + 8 <= lo + vs):
                continue
            v = struct.unpack_from("<Q", mm, r)[0]
            if not (IMG <= v < IMG + SZ):
                continue
            should += 1
            got = struct.unpack_from("<Q", out, r - lo)[0]
            want = v - IMG + VA
            is_final = r + 8 == lo + vs
            final += is_final
            if got == want:
                final_fixed += is_final
            elif got == v:
                missed += 1
                print("[check] MISS %s RVA 0x%x (%s)" % (n, r, "section 末尾 slot" if is_final else "途中"))
            else:
                bad += 1
                print("[check] BAD  %s RVA 0x%x got 0x%x want 0x%x" % (n, r, got, want))
    print("[check] gen=%s PE=%s DIR64 total=%d 補正対象=%d 補正漏れ=%d 不正値=%d 末尾slot対象=%d 末尾slot補正=%d (期待 補正漏れ=%d)"
          % (a.gen, os.path.basename(a.pe), len(relocs), should, missed, bad, final, final_fixed, a.expect_missed))
    if should == 0:
        print("[check] FAIL: 補正対象 0 件 (検査が空振り)")
        return 1
    if bad or missed != a.expect_missed:
        print("[check] FAIL")
        return 1
    print("[check] PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
