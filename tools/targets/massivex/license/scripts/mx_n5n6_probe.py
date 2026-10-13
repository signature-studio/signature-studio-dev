"""MX2-3 (#830 / #1017) N5・N6 文字列の周辺実測。

使い方: python3 license/scripts/mx_n5n6_probe.py <Massive X.vst3>
文字列の出現 (ASCII / UTF-16LE) と VA (ImageBase 0x180000000) を出し、
周辺 (前後 160 B) の文脈を表示する。参照元の判定はしない (REPORT_APPENDIX §12.4)。
"""
import re
import struct
import sys

IMAGE_BASE = 0x180000000
P = sys.argv[1] if len(sys.argv) > 1 else "work/extracted/VST3/Massive X.vst3"
data = open(P, "rb").read()

pe = struct.unpack_from("<I", data, 0x3C)[0]
nsec = struct.unpack_from("<H", data, pe + 6)[0]
optsz = struct.unpack_from("<H", data, pe + 20)[0]
sec0 = pe + 24 + optsz
secs = []
for i in range(nsec):
    o = sec0 + i * 40
    name = data[o:o + 8].rstrip(b"\0").decode(errors="replace")
    vsz, va, rsz, raw = struct.unpack_from("<IIII", data, o + 8)
    secs.append((name, va, vsz, raw))


def off2va(off):
    for name, sva, vsz, raw in secs:
        if raw <= off < raw + max(vsz, 1):
            return IMAGE_BASE + sva + (off - raw), name
    return None, None


TARGETS = {
    "N6": [b"Please use Native Access to re-activate.", b"Please open Native Access to re-activate."],
    "N5": [b"MXDemoPopup", b"demoExpired", b"demoExpiredChanged", b"subscriptionExpired"],
}

for group, needles in TARGETS.items():
    for s in needles:
        for label, pat in (("ascii", s), ("utf16", s.decode().encode("utf-16-le"))):
            hits = [m.start() for m in re.finditer(re.escape(pat), data)]
            print(f"[{group}] {s.decode()} {label}: {len(hits)} hit(s)")
            for off in hits[:2]:
                va, sec = off2va(off)
                ctx = data[max(0, off - 80): off + len(pat) + 80]
                txt = re.sub(rb"[^\x20-\x7e]", b".", ctx).decode()
                print(f"  raw=0x{off:x} VA=0x{va:x} sec={sec}")
                print(f"    {txt}")
