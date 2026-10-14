#!/usr/bin/env python3
"""SHX-T30 (#2579): function_8c5eb0 の直接 call 元の窓統計 (REPORT_SHX-T30.md §4) を再計算する。

使い方: python3 tools/m11/m11_t30_callsites.py <block00031_PE.bin>
  入力は fl-win64 の extracted/block00031_PE.bin (sha256 b2c64da4...)。objdump が必要。

窓: 各 call 命令の直前 14 命令。ただし同じ関数 (.pdata の境界) の内側だけを見る。
判定: 窓の中で dl (rdx) と r8 を明示的に書く最後の命令で値を分類する。
  dl: mov dl,imm (imm≠0 → nz) / xor edx,edx (zero) / その他の書込み (nonconst)
  r8: xor r8,r8・mov r8,0 (zero) / その他の書込み (nonconst)
"""
import bisect
import re
import struct
import subprocess
import sys

TARGET = 0x8C5EB0
WINDOW = 14
DL_NAMES = {"dl", "edx", "rdx", "dx"}
R8_NAMES = {"r8", "r8d", "r8w", "r8b"}


def pdata_functions(path):
    b = open(path, "rb").read()
    e_lfanew = struct.unpack_from("<I", b, 0x3C)[0]
    assert b[e_lfanew:e_lfanew + 4] == b"PE\0\0", "not a PE file"
    coff = e_lfanew + 4
    nsec = struct.unpack_from("<H", b, coff + 2)[0]
    optsz = struct.unpack_from("<H", b, coff + 16)[0]
    opt = coff + 20
    assert struct.unpack_from("<H", b, opt)[0] == 0x20B, "PE32+ expected"
    imagebase = struct.unpack_from("<Q", b, opt + 24)[0]
    exc_rva, exc_size = struct.unpack_from("<II", b, opt + 112 + 3 * 8)
    secs = []
    for i in range(nsec):
        off = opt + optsz + 40 * i
        vsize, va, rawsz, rawptr = struct.unpack_from("<IIII", b, off + 8)
        secs.append((va, max(vsize, rawsz), rawptr))
    for va, sz, raw in secs:
        if va <= exc_rva < va + sz:
            off = exc_rva - va + raw
            break
    else:
        raise ValueError("exception directory not in any section")
    funcs = []
    for i in range(exc_size // 12):
        begin, end, _ = struct.unpack_from("<III", b, off + 12 * i)
        funcs.append((imagebase + begin, imagebase + end))
    return sorted(funcs), imagebase


def linear_insns(path):
    out = subprocess.run(
        ["objdump", "-d", "-M", "intel", "--no-show-raw-insn", path],
        check=True, capture_output=True, text=True,
    ).stdout
    insns = []
    for line in out.splitlines():
        m = re.match(r"^\s*([0-9a-f]+):\t(\S.*)$", line)
        if m:
            insns.append((int(m.group(1), 16), m.group(2).strip()))
    return insns


def dest_and_src(text):
    parts = text.split(None, 1)
    mnem = parts[0]
    ops = parts[1] if len(parts) > 1 else ""
    if "," in ops:
        dst, src = [x.strip() for x in ops.split(",", 1)]
    else:
        dst, src = ops.strip(), None
    return mnem, dst, src


def classify(window, names, kind):
    for text in reversed(window):
        mnem, dst, src = dest_and_src(text)
        if dst not in names or mnem in ("cmp", "test", "push"):
            continue
        if mnem in ("xor",) and src == dst:
            return "zero"
        if mnem in ("mov", "movabs") and src is not None:
            if re.fullmatch(r"0x[0-9a-f]+|\d+", src):
                v = int(src, 0)
                if kind == "dl":
                    return "zero" if v == 0 else "nz"
                return "zero" if v == 0 else "nonconst"
        return "nonconst"
    return "none"


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    path = sys.argv[1]
    funcs, _ = pdata_functions(path)
    starts = [f[0] for f in funcs]
    insns = linear_insns(path)
    addr_index = {a: i for i, (a, _) in enumerate(insns)}
    calls = [
        i for i, (_, t) in enumerate(insns)
        if re.match(r"call\s+(?:0x)?%x\b" % TARGET, t)
    ]
    dl_cnt = {}
    r8_cnt = {}
    for i in calls:
        addr = insns[i][0]
        k = bisect.bisect_right(starts, addr) - 1
        fbegin = funcs[k][0] if k >= 0 and addr < funcs[k][1] else addr
        lo = max(i - WINDOW, 0)
        while lo < i and insns[lo][0] < fbegin:
            lo += 1
        window = [t for _, t in insns[lo:i]]
        dl = classify(window, DL_NAMES, "dl")
        dl_cnt[dl] = dl_cnt.get(dl, 0) + 1
        if dl == "nz":
            r8 = classify(window, R8_NAMES, "r8")
            r8_cnt[r8] = r8_cnt.get(r8, 0) + 1
    print(f"direct calls to {TARGET:#x}: {len(calls)}")
    print(f"dl: nz={dl_cnt.get('nz', 0)} zero={dl_cnt.get('zero', 0)} none={dl_cnt.get('none', 0)} nonconst={dl_cnt.get('nonconst', 0)}")
    print(f"dl nz の r8: zero={r8_cnt.get('zero', 0)} nonconst={r8_cnt.get('nonconst', 0)} none={r8_cnt.get('none', 0)}")


if __name__ == "__main__":
    main()
