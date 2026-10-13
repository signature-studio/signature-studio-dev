#!/usr/bin/env python3
# usage: 実行はこのディレクトリ (tools/targets/massivex) から。
#   python3 license/scripts/mx_callers_probe.py              # 実 PE の走査 (work/extracted/VST3/Massive X.vst3)
#   python3 license/scripts/mx_callers_probe.py --selftest   # 陽性対照 (素材不要)
"""N6 読み手関数 (N6-1〜6) への直接 call/jmp (E8/E9 rel32) 呼び出し元を列挙する。

検出器の陽性対照 (--selftest): 既知の E8 call / E9 jmp を埋め込んだ合成 .text を走査し、
既知件数が検出されることを確認する。検出できなければ exit 1 (0 件の出力は根拠にならない)。
"""
import sys
import numpy as np

TARGETS = [0x180f95e20, 0x181142370, 0x181144570, 0x181142640, 0x1811453f0]


def find_callers(buf, text_va, targets):
    hits = {t: [] for t in targets}
    for op in (0xE8, 0xE9):
        for i in np.nonzero(buf[:-4] == op)[0]:
            rel = int.from_bytes(bytes(buf[i + 1:i + 5]), "little", signed=True)
            dst = text_va + int(i) + 5 + rel
            if dst in hits:
                hits[dst].append((hex(text_va + int(i)), "E8" if op == 0xE8 else "E9"))
    return hits


def selftest():
    text_va = 0x180001000
    code = bytearray(b"\x90" * 256)
    known = [(0x10, 0xE8, TARGETS[0]), (0x40, 0xE9, TARGETS[1]), (0x80, 0xE8, TARGETS[1])]
    other = (0xC0, 0xE8, 0x180002000)  # 検出対象外の既知関数への call (陰性側も確認)
    for off, op, dst in known + [other]:
        rel = dst - (text_va + off + 5)
        code[off] = op
        code[off + 1:off + 5] = rel.to_bytes(4, "little", signed=True)
    hits = find_callers(np.frombuffer(bytes(code), dtype=np.uint8), text_va, TARGETS)
    want = {TARGETS[0]: 1, TARGETS[1]: 2, TARGETS[2]: 0, TARGETS[3]: 0, TARGETS[4]: 0}
    got = {t: len(hits[t]) for t in TARGETS}
    for t in TARGETS:
        print(f"selftest fn {t:#x}: 期待 {want[t]} 件 / 検出 {got[t]} 件")
    ok = got == want
    print("selftest:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    import pefile
    pe_path = "work/extracted/VST3/Massive X.vst3"
    data = open(pe_path, "rb").read()
    pe = pefile.PE(data=data, fast_load=True)
    ib = pe.OPTIONAL_HEADER.ImageBase
    text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
    t_off, t_va, t_sz = text.PointerToRawData, ib + text.VirtualAddress, text.SizeOfRawData
    buf = np.frombuffer(data[t_off:t_off + t_sz], dtype=np.uint8)
    hits = find_callers(buf, t_va, TARGETS)
    for t in TARGETS:
        print(f"fn {t:#x}: direct call/jmp {len(hits[t])} 件", hits[t][:10])


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
