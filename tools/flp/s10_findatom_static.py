#!/usr/bin/env python3
# #5601 (L-25): FLEngine_x64.dll の FindAtomW / GlobalFindAtomW を呼ぶ関数と、ControlOfs 名の書式文字列の参照元を静的に列挙する (実行なし)。
# 入力: $RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin (fl-win64 を tar --zstd -xf で展開した後の FLEngine_x64.dll)
# 出力: 標準出力 (IAT スロット・thunk VA・呼出し箇所・呼出し箇所を含む関数の先頭・書式文字列の参照元)。逆アセンブルは $RUNNER_TEMP/fl31.dis。
# 使い方: python3 tools/flp/s10_findatom_static.py [PE_BIN]
import bisect
import os
import re
import struct
import subprocess
import sys

IMAGE_BASE = 0x400000
TMP = os.environ.get("RUNNER_TEMP", "/tmp")
PE_BIN = sys.argv[1] if len(sys.argv) > 1 else os.path.join(TMP, "fl-win64/extracted/block00031_PE.bin")
TARGETS = ("FindAtomW", "GlobalFindAtomW")
FMT = "ControlOfs%.8X%.8X"


def load_sections(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec, = struct.unpack_from("<H", d, pe + 6)
    optsz, = struct.unpack_from("<H", d, pe + 20)
    so = pe + 24 + optsz
    return [struct.unpack_from("<8sIIII", d, so + i * 40) for i in range(nsec)]


def r2o(secs, rva):
    for _, vsz, va, rsz, rp in secs:
        if va <= rva < va + max(vsz, rsz):
            return rva - va + rp
    return None


def iat_slots(d, secs):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    imp_rva, = struct.unpack_from("<I", d, pe + 24 + 112 + 8)
    o = r2o(secs, imp_rva)
    slots = {}
    i = 0
    while True:
        oft, _, _, nrva, ft = struct.unpack_from("<IIIII", d, o + i * 20)
        if oft == 0 and nrva == 0:
            break
        lo = r2o(secs, oft or ft)
        j = 0
        while True:
            v, = struct.unpack_from("<Q", d, lo + j * 8)
            if v == 0:
                break
            if not v >> 63:
                h = r2o(secs, v & 0x7FFFFFFFFFFFFFFF)
                nm = d[h + 2:d.index(b"\0", h + 2)].decode(errors="replace")
                if nm in TARGETS:
                    slots[nm] = ft + j * 8
            j += 1
        i += 1
    return slots


def thunk_of(d, secs, iat_rva):
    # 'jmp *disp32(%rip)' (ff 25) で IAT を指す thunk の VA を求める
    out = []
    for name, vsz, va, rsz, rp in secs:
        if not name.startswith(b".text"):
            continue
        for o in range(rp, rp + rsz - 6):
            if d[o] == 0xFF and d[o + 1] == 0x25:
                r = o - rp + va
                if r + 6 + struct.unpack_from("<i", d, o + 2)[0] == iat_rva:
                    out.append(IMAGE_BASE + r)
    return out


def parse_disasm(path):
    pat = re.compile(r"^\s*([0-9a-f]+):\t(.*)$")
    ins = []
    with open(path) as f:
        for ln in f:
            m = pat.match(ln.rstrip("\n"))
            if m:
                ins.append((int(m.group(1), 16), m.group(2)))
    return ins


def func_start(ins, addrs, a):
    # 関数先頭: 直前が int3/ret/nop 等で、先頭命令が push (rbp 以外も含む) の最初の位置
    j = bisect.bisect_right(addrs, a) - 1
    while j > 0:
        if ins[j][1].startswith("push  ") and ins[j - 1][1].startswith(("int3", "ret", "nop", "(bad)")):
            return ins[j][0]
        j -= 1
    return None


def main():
    d = open(PE_BIN, "rb").read()
    secs = load_sections(d)
    slots = iat_slots(d, secs)
    print("IAT slots (VA):", {k: hex(IMAGE_BASE + v) for k, v in slots.items()})
    thunks = {nm: thunk_of(d, secs, rva) for nm, rva in slots.items()}
    for nm, ts in thunks.items():
        print(nm, "thunk VA:", [hex(x) for x in ts])

    out = os.path.join(TMP, "fl31.dis")
    if not os.path.exists(out):
        with open(out, "w") as f:
            subprocess.run(["objdump", "-d", "--no-show-raw-insn", PE_BIN], stdout=f, check=True)
    ins = parse_disasm(out)
    addrs = [a for a, _ in ins]

    for nm, ts in thunks.items():
        for t in ts:
            pat = re.compile(r"call +0x%x\b" % t)
            for a, text in ins:
                if pat.search(text):
                    f = func_start(ins, addrs, a)
                    print("%s call at %s (func %s)" % (nm, hex(a), hex(f) if f else None))

    # 書式文字列 (UTF-16LE) は .text 内に埋め込まれているので全セクションから探す
    fmt_b = FMT.encode("utf-16le")
    for name, vsz, va, rsz, rp in secs:
        i = d.find(fmt_b, rp, rp + rsz)
        if i >= 0:
            fmt_va = IMAGE_BASE + va + (i - rp)
            print("format %r at VA %s (%s)" % (FMT, hex(fmt_va), name.rstrip(b"\0").decode()))
            for a, text in ins:
                if re.search(r"# 0x%x\b" % fmt_va, text):
                    print("format ref at", hex(a), text)


if __name__ == "__main__":
    main()
