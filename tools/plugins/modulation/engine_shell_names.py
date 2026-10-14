#!/usr/bin/env python3
# 殻の名前表 (ポインタの配列) を復元し、各要素が指す文字列を出す (#527 受入 5)。
#   python3 engine_shell_names.py <PE.bin> <table_va_hex> <count>
# 文字列は ASCII (NUL 終端) と UTF-16LE (NUL 終端) の両方を試し、読めた方を出す。
# 静的のみ。表の範囲は engine_shell_vst.py の出力 (slot 近傍) で決める。
import struct
import sys

import pefile


def read_cstr(data, secs, va):
    for name, sva, vsz, rpa, rsz, ch in secs:
        if sva <= va < sva + rsz:
            raw = data[rpa + (va - sva):rpa + rsz]
            if len(raw) > 1 and raw[1] == 0:
                end = 0
                while end + 1 < len(raw) and not (raw[end] == 0 and raw[end + 1] == 0):
                    end += 2
                if 0 < end <= 512:
                    try:
                        return "utf16", raw[:end].decode("utf-16-le")
                    except UnicodeDecodeError:
                        pass
                return "?", ""
            end = raw.find(b"\0", 0, 256)
            if end > 0:
                s = raw[:end]
                if all(0x20 <= c < 0x7f for c in s):
                    return "ascii", s.decode()
            return "?", ""
    return "unmapped", ""


def main(path, table_va, count):
    pe = pefile.PE(path, fast_load=True)
    data = open(path, "rb").read()
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = []
    for s in pe.sections:
        name = s.Name.rstrip(b"\0").decode(errors="replace")
        secs.append((name, base + s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData,
                     s.SizeOfRawData, s.Characteristics))
    for i in range(count):
        va = table_va + 8 * i
        for name, sva, vsz, rpa, rsz, ch in secs:
            if sva <= va < sva + rsz:
                ptr = struct.unpack_from("<Q", data, rpa + (va - sva))[0]
                kind, text = read_cstr(data, secs, ptr)
                print(i, hex(va), hex(ptr), kind, repr(text))
                break


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3]))
