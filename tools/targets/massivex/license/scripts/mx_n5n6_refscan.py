"""MX2-3 (#830 / #1017) N5・N6 文字列 VA への絶対/RVA 参照を全ファイル走査する。

使い方: python3 license/scripts/mx_n5n6_refscan.py <Massive X.vst3>
8 B 絶対ポインタ (VA) と 4 B RVA を全域で数え、4 B RVA ヒットは raw オフセットを出す。
VA 一覧は REPORT_APPENDIX §12.2 の 10 件と一致させる (N6 6 件 + N5 4 件)。
RIP 相対 (lea/mov) の判定は mx_callgraph.py の rip 表側で別途行う。
"""
import struct
import sys

IMAGE_BASE = 0x180000000
P = sys.argv[1] if len(sys.argv) > 1 else "work/extracted/VST3/Massive X.vst3"
data = open(P, "rb").read()

VAS = {
    "N6 0x184ffcf87": 0x184ffcf87,
    "N6 0x184ffcfe8": 0x184ffcfe8,
    "N6 0x184ffd03f": 0x184ffd03f,
    "N6 0x184ffd092": 0x184ffd092,
    "N6 0x184ffd0d6": 0x184ffd0d6,
    "N6 0x184ffd131": 0x184ffd131,
    "N5 MXDemoPopup.qml": 0x18415f411,
    "N5 demoExpired": 0x184879407,
    "N5 demoExpiredChanged": 0x1848792b9,
    "N5 subscriptionExpired": 0x18487941a,
}

assert len(set(VAS.values())) == len(VAS), "VA 重複"

for label, va in VAS.items():
    q = struct.pack("<Q", va)
    r = struct.pack("<I", va - IMAGE_BASE)
    n8 = data.count(q)
    hits4 = []
    i = data.find(r)
    while i != -1:
        hits4.append(i)
        i = data.find(r, i + 1)
    print(f"{label} VA=0x{va:x}: abs64={n8} rva32={len(hits4)}")
    for off in hits4[:5]:
        print(f"  rva32 raw=0x{off:x}")
