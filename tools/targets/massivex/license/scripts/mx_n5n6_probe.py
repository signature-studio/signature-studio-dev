"""MX2-3 (#830 / #1017) N5・N6 文字列の周辺実測。

使い方: python3 license/scripts/mx_n5n6_probe.py <Massive X.vst3>
N6: バイナリ中の 'Native Access' を含む文字列を ASCII / UTF-16LE で全件列挙する
    (文言の全文はリポジトリに無いため、推測せず走査で求める。REPORT_APPENDIX §12.2 の 6 件と照合する)。
N5: 既知の名前を ASCII / UTF-16LE で検索する。
文字列の VA (ImageBase 0x180000000) と前後 80 B の文脈を出す。参照元の判定はしない (REPORT_APPENDIX §12.4)。
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


def ctx(off, length):
    c = data[max(0, off - 80): off + length + 80]
    return re.sub(rb"[^\x20-\x7e]", b".", c).decode()


print("[N6] 'Native Access' を含む文字列の全件 (ASCII / UTF-16LE)")
for label, pat in (
    ("ascii", rb"[\x20-\x7e]{8,}"),
    ("utf16", rb"(?:[\x20-\x7e]\x00){8,}"),
):
    for m in re.finditer(pat, data):
        s = m.group(0)
        txt = s.decode("utf-16-le") if label == "utf16" else s.decode()
        if "Native Access" not in txt:
            continue
        va, sec = off2va(m.start())
        print(f"  {label} raw=0x{m.start():x} VA=0x{va:x} sec={sec}")
        print(f"    {txt}")
        print(f"    ctx: {ctx(m.start(), len(s))}")

TARGETS_N5 = [b"MXDemoPopup", b"demoExpired", b"demoExpiredChanged", b"subscriptionExpired"]
print("[N5] 既知名の出現")
for s in TARGETS_N5:
    for label, pat in (("ascii", s), ("utf16", s.decode().encode("utf-16-le"))):
        hits = [m.start() for m in re.finditer(re.escape(pat), data)]
        print(f"  {s.decode()} {label}: {len(hits)} hit(s)")
        for off in hits[:2]:
            va, sec = off2va(off)
            print(f"    raw=0x{off:x} VA=0x{va:x} sec={sec}")
            print(f"    {ctx(off, len(pat))}")
