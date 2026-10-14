#!/usr/bin/env python3
"""FLEngine PE の 0xd82c20 (戻り値 → Python 例外変換) が使う例外文言を読み出す (PY-73 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_errmsg_probe.py

0xd82c20 は負の内部 code ごとに `lea rdx,[rip+disp]` で文言の char* を渡す。各 code の分岐先 VA を
固定し、RIP 相対で文言を読む。期待値 (期待文言) と一致しなければ終了 1。
展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import os
import sys

import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")

# 分岐先 VA (lea rdx,[rip+disp] の位置の直前 4 バイトが `lea rcx,[rbp+0x38]`)
SITES = [
    (-1, 0xd82d03, "Unspecified error"),
    (-2, 0xd82d18, "Operation unsafe at current time"),
    (-3, 0xd82d2a, "Range error"),
    (-4, 0xd82d3c, "Index out of range"),
]


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase

    def fo(va):
        rva = va - base
        for s in pe.sections:
            if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
                return s.PointerToRawData + (rva - s.VirtualAddress)
        raise SystemExit(f"VA {hex(va)} が section 外")

    ok = True
    for code, site, want in SITES:
        lea = site + 4  # lea rdx,[rip+disp32] (7 バイト)
        o = fo(lea)
        if raw[o:o + 2] != b"\x48\x8d":
            raise SystemExit(f"{hex(lea)} が lea ではない")
        disp = int.from_bytes(raw[o + 3:o + 7], "little", signed=True)
        tgt = lea + 7 + disp
        t = fo(tgt)
        got = raw[t:raw.index(b"\0", t)].decode("latin1")
        mark = "OK" if got == want else "NG"
        ok &= got == want
        print(f"code {code:>2} site {hex(site)} str {hex(tgt)} {got!r} {mark}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
