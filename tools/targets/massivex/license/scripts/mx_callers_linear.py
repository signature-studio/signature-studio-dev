#!/usr/bin/env python3
# usage: 実行はこのディレクトリ (tools/targets/massivex) から。
#   python3 license/scripts/mx_callers_linear.py              # 実 PE の .text を線形逆アセンブル
#   python3 license/scripts/mx_callers_linear.py --selftest   # 合成 .text で検算器を自己検査 (素材不要)
"""mx_callers_probe.py (バイト走査) とは別アルゴリズムの検算。

capstone で .text を先頭から線形逆アセンブルし、命令の call / jmp (rel32 / rel8 を含む)
のオペランドが N6 読み手 5 関数を指すものを数える。バイト走査は命令境界を見ないため、
データ中の 0xE8/0xE9 を誤検出しうる。線形逆アセンブルで両者が一致すれば検算として採る。
"""
import sys
import capstone

TARGETS = [0x180f95e20, 0x181142370, 0x181144570, 0x181142640, 0x1811453f0]


def find_callers_linear(code, text_va, targets):
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = False
    hits = {t: [] for t in targets}
    for ins in md.disasm(code, text_va):
        if ins.mnemonic not in ("call", "jmp"):
            continue
        if not ins.op_str.startswith("0x"):
            continue
        dst = int(ins.op_str, 16)
        if dst in hits:
            hits[dst].append((hex(ins.address), ins.mnemonic))
    return hits


def selftest():
    text_va = 0x180001000
    code = bytearray()
    # 命令境界を揃えた合成 .text: nop で埋めた先頭、既知 call/jmp を配置
    code += b"\x90" * 0x10
    code += b"\xe8" + (TARGETS[0] - (text_va + len(code) + 5)).to_bytes(4, "little", signed=True)
    code += b"\x90" * 0x10
    code += b"\xe9" + (TARGETS[1] - (text_va + len(code) + 5)).to_bytes(4, "little", signed=True)
    code += b"\xe8" + (TARGETS[1] - (text_va + len(code) + 5)).to_bytes(4, "little", signed=True)
    code += b"\xe8" + (0x180002000 - (text_va + len(code) + 5)).to_bytes(4, "little", signed=True)
    code += b"\xc3"
    want = {TARGETS[0]: 1, TARGETS[1]: 2, TARGETS[2]: 0, TARGETS[3]: 0, TARGETS[4]: 0}
    hits = find_callers_linear(bytes(code), text_va, TARGETS)
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
    hits = find_callers_linear(data[t_off:t_off + t_sz], t_va, TARGETS)
    for t in TARGETS:
        print(f"linear fn {t:#x}: call/jmp {len(hits[t])} 件", hits[t][:10])


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
