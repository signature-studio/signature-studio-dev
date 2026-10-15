#!/usr/bin/env python3
# #2546: oracle 用ローカルコピー (FLEngine_x64.dll 等) の命令 1 つを書き換える検証用パッチ。期待バイトと一致したときだけ書く。
# 使い方: s2_imm_patch.py <file> <VA hex> <期待バイト hex> <新バイト hex>
# 呼出し元: tools/flp/s2_render_probe.sh (S2_PATCH)。素材の blob・repo 内には書かない。
import sys

import pefile

path, va_s, expect_s, new_s = sys.argv[1:5]
pe = pefile.PE(path, fast_load=True)
off = pe.get_offset_from_rva(int(va_s, 16) - pe.OPTIONAL_HEADER.ImageBase)
expect, new = bytes.fromhex(expect_s), bytes.fromhex(new_s)
if len(expect) != len(new):
    sys.exit("expect/new の長さが違う")
data = bytearray(open(path, "rb").read())
if bytes(data[off:off + len(expect)]) != expect:
    sys.exit(f"期待バイト不一致 at file {hex(off)}: {data[off:off + len(expect)].hex()}")
data[off:off + len(new)] = new
open(path, "wb").write(bytes(data))
print(f"imm patch {va_s} {expect_s} -> {new_s} (file {hex(off)})")
