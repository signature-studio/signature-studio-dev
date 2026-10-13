"""MX2-3 (#830 / #1017) N5・N6 文字列 VA への絶対/RVA 参照を全ファイル走査する。

使い方: python3 license/scripts/mx_n5n6_refscan.py <Massive X.vst3>
8 B 絶対ポインタ (VA) と 4 B RVA を .text/.rdata/.data/.pdata/.xdata/.reloc 全域で数える。
RIP 相対 (lea/mov) の判定は mx_callgraph.py の rip 表側で別途行う。
"""
import struct
import sys

IMAGE_BASE = 0x180000000
P = sys.argv[1] if len(sys.argv) > 1 else "work/extracted/VST3/Massive X.vst3"
data = open(P, "rb").read()

VAS = {
    "N6 'Please open ... re-activate.'": 0x184ffcf87,
    "N6 'Please use ... re-activate.' (1)": 0x184ffcfe8,
    "N6 'Please use ... re-activate.' (2)": 0x184ffd03f,
    "N5 'MXDemoPopup.qml'": 0x18415f411,
    "N5 'demoExpired'": 0x1848792b9,
    "N5 'demoExpiredChanged'": 0x1848792b9,
    "N5 'subscriptionExpired'": 0x18487941a,
}

for label, va in VAS.items():
    q = struct.pack("<Q", va)
    r = struct.pack("<I", va - IMAGE_BASE)
    n8 = data.count(q)
    n4 = data.count(r)
    print(f"{label} VA=0x{va:x}: abs64={n8} rva32={n4}")
