#!/usr/bin/env python3
# #2190 / T-SH-34: relay trace の GetProcAddress 呼出しのうち、戻り番地 (ret=) が
# 指定イメージの [base, base+SizeOfImage) に入るものを抜く。
# 件数の定義: Call 行のみ (Ret 行は含めない)。範囲判定は整数比較 (桁数に依存しない)。
# usage: filter_gpa.py TRACE IMAGE BASE_HEX [NAME_REGEX]  (該当行を stdout、件数を stderr)
import re
import struct
import sys


def size_of_image(path):
    with open(path, "rb") as f:
        d = f.read(0x1000)
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    if d[pe:pe + 4] != b"PE\0\0":
        raise SystemExit(f"not a PE: {path}")
    opt = pe + 24
    if struct.unpack_from("<H", d, opt)[0] not in (0x10B, 0x20B):
        raise SystemExit(f"unknown optional header: {path}")
    return struct.unpack_from("<I", d, opt + 56)[0]


def main():
    trace, image, base_s = sys.argv[1:4]
    name_re = re.compile(sys.argv[4]) if len(sys.argv) > 4 else None
    base = int(base_s, 16)
    end = base + size_of_image(image)
    call_re = re.compile(
        r"Call (?:KERNEL32|KERNELBASE)\.GetProcAddress\((.*)\) ret=([0-9a-f]+)\s*$"
    )
    total = hit = 0
    with open(trace, errors="replace") as f:
        for line in f:
            m = call_re.search(line)
            if not m:
                continue
            total += 1
            if not base <= int(m.group(2), 16) < end:
                continue
            if name_re is not None and not name_re.search(m.group(1)):
                continue
            hit += 1
            sys.stdout.write(line)
    print(
        f"GetProcAddress Call 行 {total} 件 / ret in [{base:#x}, {end:#x}) = {hit} 件"
        f" (image={image}, name={sys.argv[4] if len(sys.argv) > 4 else '*'})",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
