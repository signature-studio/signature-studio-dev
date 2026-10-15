#!/usr/bin/env python3
"""SlateCore.core_64 の Gain ramp を KH 形 `cur = a + (b-a)*t` の命令列に置き換えた複製を作る (#2736)。
   usage: ks_ramp_kh_patch.py <src SC PE> <dst>
 元の SC 形は `cur = (1-t)*a + t*b` (t = pos*coef)。置換後は KH の演算順 (t = pos*inc → (b-a)*t → +a)。
 書き換え範囲 (VA):
   0x180afe152〜0x180afe1a0: 旧 nop 14 B + ramp 65 B = 79 B → 新 nop 13 B + ramp 66 B = 79 B (ループ頭 0x180afe15f)
   0x180afe21d〜0x180afe220: back-edge `jl` の rel32 を新しいループ頭へ向け直す
 書き込み前に元バイトを assert する (fail-closed: 一致しなければ dst を作らず exit 1)。元ファイルは変えない。
"""
import json, os, struct, sys

NOP_OLD = "0f1f4000" + "66660f1f840000000000"
RAMP_OLD = [
    ("f30f108b9c000000", "movss xmm1,[rbx+0x9c]"),
    ("0f28c4", "movaps xmm0,xmm4"),
    ("f30f58cc", "addss xmm1,xmm4"),
    ("ffc1", "inc ecx"),
    ("f30f118b9c000000", "movss [rbx+0x9c],xmm1"),
    ("f30f598ba0000000", "mulss xmm1,[rbx+0xa0]"),
    ("f30f5cc1", "subss xmm0,xmm1"),
    ("f30f598ba8000000", "mulss xmm1,[rbx+0xa8]"),
    ("f30f5983a4000000", "mulss xmm0,[rbx+0xa4]"),
    ("f30f58c1", "addss xmm0,xmm1"),
    ("f30f1183ac000000", "movss [rbx+0xac],xmm0"),
]
NOP_NEW = "0f1f40000f1f4400000f1f4000"
RAMP_NEW = [
    ("f30f108b9c000000", "movss xmm1,[rbx+0x9c]"),
    ("f30f58cc", "addss xmm1,xmm4"),
    ("ffc1", "inc ecx"),
    ("f30f118b9c000000", "movss [rbx+0x9c],xmm1"),
    ("f30f598ba0000000", "mulss xmm1,[rbx+0xa0]"),
    ("f30f1083a8000000", "movss xmm0,[rbx+0xa8]"),
    ("f30f5c83a4000000", "subss xmm0,[rbx+0xa4]"),
    ("f30f59c1", "mulss xmm0,xmm1"),
    ("f30f5883a4000000", "addss xmm0,[rbx+0xa4]"),
    ("f30f1183ac000000", "movss [rbx+0xac],xmm0"),
]
REGION_VA = 0x180afe152
LOOP_HEAD_OLD = 0x180afe160
LOOP_HEAD_NEW = 0x180afe15f
JL_VA = 0x180afe21b


def sections(f):
    pe = struct.unpack_from("<I", f, 0x3C)[0]
    assert f[pe:pe + 4] == b"PE\0\0", "not a PE"
    magic, = struct.unpack_from("<H", f, pe + 24)
    assert magic == 0x20B, "not PE32+"
    ns, = struct.unpack_from("<H", f, pe + 6)
    osz, = struct.unpack_from("<H", f, pe + 20)
    base, = struct.unpack_from("<Q", f, pe + 24 + 24)
    secs = []
    for i in range(ns):
        s = pe + 24 + osz + i * 40
        vs, va, rs, rp = struct.unpack_from("<IIII", f, s + 8)
        secs.append((va, vs, rp, rs))
    return base, secs


def file_off(secs, base, va, n):
    rva = va - base
    for va0, vs, rp, rs in secs:
        if va0 <= rva and rva + n <= va0 + max(vs, rs):
            return rp + (rva - va0)
    raise SystemExit(f"no section covers {va:#x}+{n}")


def hexs(items):
    return "".join(h for h, _ in items)


def main():
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    src, dst = sys.argv[1], sys.argv[2]
    orig = open(src, "rb").read()
    data = bytearray(orig)
    base, secs = sections(orig)

    old_region = bytes.fromhex(NOP_OLD + hexs(RAMP_OLD))
    new_region = bytes.fromhex(NOP_NEW + hexs(RAMP_NEW))
    assert len(old_region) == len(new_region) == 79, (len(old_region), len(new_region))

    off = file_off(secs, base, REGION_VA, len(old_region))
    assert bytes(data[off:off + len(old_region)]) == old_region, "region 0x180afe152 の元バイトが一致しない"
    data[off:off + len(new_region)] = new_region

    def jl(target):
        return struct.pack("<i", target - (JL_VA + 6))

    old_jl = bytes.fromhex("0f8c") + jl(LOOP_HEAD_OLD)
    new_jl = bytes.fromhex("0f8c") + jl(LOOP_HEAD_NEW)
    assert old_jl == bytes.fromhex("0f8c3fffffff"), old_jl.hex()
    offj = file_off(secs, base, JL_VA, 6)
    assert bytes(data[offj:offj + 6]) == old_jl, "jl 0x180afe21b の元バイトが一致しない"
    data[offj:offj + 6] = new_jl

    changed = sum(a != b for a, b in zip(orig, data))
    with open(dst, "wb") as g:
        g.write(data)
    print(json.dumps({
        "src": os.path.basename(src),
        "dst": os.path.basename(dst),
        "base": hex(base),
        "region_va": hex(REGION_VA),
        "region_len": len(new_region),
        "region_file_off": hex(off),
        "jl_va": hex(JL_VA),
        "jl_new_rel32": new_jl[2:].hex(),
        "bytes_changed": changed,
    }))


if __name__ == "__main__":
    main()
