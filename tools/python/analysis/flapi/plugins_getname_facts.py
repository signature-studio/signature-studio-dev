#!/usr/bin/env python3
"""plugins.getName の引数・戻り値の骨格を PE の逆アセンブルで確かめる (PY-5350 / #5488)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/plugins_getname_facts.py

確認する事実 (いずれも block00031_PE.bin と flapi_kwargs.json・block24429_DATA.bin (midi.py)。根拠は REPORT_PY5350.md):
- 引数: fmt "i|iiii"、kwlist index・slotIndex・flag・paramIndex・useGlobalIndex (既定 -1・-1・0・-1・0)。
- slot == -1 の経路: 0x1005730 で channel を解決し、0x132f780 で有効性を見る。偽なら code -8。
- slot != -1 の経路: 件数 [0x15e2198] の -1 との比較、slot の上限 9。
- flag == 6 (midi.FPN_Preset) は 0x12b69b0 へ。それ以外は plugin の vtable (+0x20) を呼ぶ。
- flag != 6 の vtable 呼出しは flag をそのまま edx に渡す (0xd80f17)。
- 0x12b69b0 は paramIndex == -1 のとき obj[+0xc0] の値を使う (0x12b6a03〜0x12b6a19)。
- 文字列化: 0xc3cfa0 は定数 0xfde9 (= 65001 = UTF-8 の codepage 値) を 0x414200 へ渡す。
- paramIndex の既定 -1 は flag != 6 の経路で 0 に丸める (0xd80f01〜)。
実行すると PASS/FAIL を出し、1 つでも FAIL なら非 0 で終わる。
"""
import json
import os
import struct
import sys

import capstone
import pefile

FL = os.environ["FL_WIN64_DIR"]
PE = os.path.join(FL, "extracted", "block00031_PE.bin")
MIDI = os.path.join(FL, "extracted", "block24429_DATA.bin")
KW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flapi_kwargs.json")
MIX_COUNT = 0x15E2198


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = [(s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData) for s in pe.sections]

    def v2o(va):
        rva = va - base
        for v, vs, p, rs in secs:
            if v <= rva < v + max(vs, rs):
                return p + (rva - v)
        return None

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def ins(va):
        i = next(md.disasm(raw[v2o(va):v2o(va) + 16], va))
        return i, f"{i.mnemonic} {i.op_str}".strip()

    def rip_target(va):
        i, _ = ins(va)
        return i.address + i.size + int(i.op_str.split("+")[1].split("]")[0], 16)

    def ascii_at(va, n):
        return raw[v2o(va):v2o(va) + n]

    kw = json.load(open(KW))["modules"]["plugins"]["getName"]
    midi = open(MIDI, "rb").read().decode("latin-1").replace("\r", "")
    fpn_preset = [ln for ln in midi.split("\n") if ln.startswith("FPN_Preset = ")]

    checks = {
        "flapi: fmt i|iiii・kwlist index/slotIndex/flag/paramIndex/useGlobalIndex": kw["fmt"] == "i|iiii"
        and kw["kwlist"] == ["index", "slotIndex", "flag", "paramIndex", "useGlobalIndex"] and kw["fn_va"] == "0xd80d60",
        "fmt 文字列 (0xd8117c) = i|iiii": ascii_at(0xD8117C, 7) == b"i|iiii\0",
        "既定 slotIndex = -1 (0xd80dba)": ins(0xD80DBA)[1] == "mov dword ptr [rbp + 0x10c8], 0xffffffff",
        "既定 flag = 0 (0xd80dc4)": ins(0xD80DC4)[1] == "mov dword ptr [rbp + 0x10c4], 0",
        "既定 paramIndex = -1 (0xd80dce)": ins(0xD80DCE)[1] == "mov dword ptr [rbp + 0x10c0], 0xffffffff",
        "既定 useGlobalIndex = 0 (0xd80ddf)": ins(0xD80DDF)[1] == "mov dword ptr [rbp + 0x10bc], 0",
        "slot == -1 判定 (0xd80e52) → 別経路 0xd80f89": ins(0xD80E52)[1] == "cmp dword ptr [rbp + 0x10c8], -1"
        and ins(0xD80E59)[1] == "jne 0xd80f89",
        "slot == -1 経路: 0x1005730 で channel 解決 (0xd80e7d)": ins(0xD80E7D)[1] == "call 0x1005730",
        "slot == -1 経路: 0x132f780 で有効性 (0xd80e91)、偽なら code -8 (0xd80f7d)": ins(0xD80E91)[1] == "call 0x132f780"
        and ins(0xD80F7D)[1] == "mov rsi, 0xfffffffffffffff8",
        "flag == 6 の分岐 (0xd80edc)": ins(0xD80EDC)[1] == "cmp dword ptr [rbp + 0x10c4], 6",
        "flag == 6 → 0x12b69b0 (0xd80efa)": ins(0xD80EFA)[1] == "call 0x12b69b0",
        "flag != 6 の vtable 呼出しに flag を渡す (0xd80f17)": ins(0xD80F17)[1] == "mov edx, dword ptr [rbp + 0x10c4]",
        "0x12b69b0: paramIndex == -1 なら obj[+0xc0] (0x12b6a03〜0x12b6a19)": ins(0x12B6A03)[1] == "cmp eax, -1"
        and ins(0x12B6A19)[1] == "mov eax, dword ptr [rax + 0xc0]",
        "flag != 6 → plugin vtable+0x20 (0xd80f36)": ins(0xD80F36)[1] == "call qword ptr [rbx + 0x20]",
        "flag != 6 の paramIndex 丸め: 負なら 0 (0xd80f01〜0xd80f0a)": ins(0xD80F01)[1] == "cmp dword ptr [rbp + 0x10c0], 0"
        and ins(0xD80F0A)[1] == "mov dword ptr [rbp + 0x10c0], 0",
        "文字列化: 0x413a60 (0xd80f50)・0x41c650 (0xd80f63)・0xc3cfa0 (0xd80f6f)": ins(0xD80F50)[1] == "call 0x413a60"
        and ins(0xD80F63)[1] == "call 0x41c650" and ins(0xD80F6F)[1] == "call 0xc3cfa0",
        "slot != -1: 件数 [0x15e2198] の参照 (0xd80fa0)": rip_target(0xD80FA0) == MIX_COUNT,
        "slot != -1: slot の上限 9 (0xd80fc8)": ins(0xD80FC8)[1] == "cmp rax, 9",
        "slot != -1: code -4 (0xd80f89 で rsi = -4) と範囲外の分岐 (0x9a・0xb2・0xc2・0xcc → 0xd810d6、0xd810d6 で rsi を渡す)": ins(0xD80F89)[1] == "mov rsi, 0xfffffffffffffffc"
        and ins(0xD80F9A)[1] == "jl 0xd810d6" and ins(0xD80FB2)[1] == "jg 0xd810d6"
        and ins(0xD80FC2)[1] == "jl 0xd810d6" and ins(0xD80FCC)[1] == "jg 0xd810d6"
        and ins(0xD810D6)[1] == "mov ecx, esi" and ins(0xD810D8)[1] == "call 0xd82c20",
        "0xc3cfa0 の CP 指定 65001 (0xfde9 = UTF-8)": ins(0xC3CFBD)[1] == "mov r8w, 0xfde9" and 0xFDE9 == 65001,
        "0x12b69b0: 0x1331340 で sub-object を得る (0x12b6a2c)": ins(0x12B6A2C)[1] == "call 0x1331340",
        "0x12b69b0: sub.vt[+0x20] を呼ぶ (0x12b6a3c)": ins(0x12B6A3C)[1] == "call qword ptr [rax + 0x20]",
        "0x12b69b0: sub.vt[+0x20] に edx = 6 を渡す (0x12b6a56)": ins(0x12B6A56)[1] == "mov edx, 6"
        and ins(0x12B6A71)[1] == "call qword ptr [rbx + 0x20]",
        "0x12b69b0: 名前の読出し 0x413a60 (0x12b6a88)・0x41c650 (0x12b6a95)": ins(0x12B6A88)[1] == "call 0x413a60"
        and ins(0x12B6A95)[1] == "call 0x41c650",
        "midi.py: FPN_Preset = 6 (flag == 6 の意味)": bool(fpn_preset) and fpn_preset[0].strip() == "FPN_Preset = 6",
        "エラー文言 code -4 (0xd82e8c)": ascii_at(0xD82E8C, 18) == b"Index out of range",
        "エラー文言 code -8 (0xd82f3c)": ascii_at(0xD82F3C, 16) == b"Plugin not valid",
    }
    for k, ok in checks.items():
        print(("PASS " if ok else "FAIL ") + k)
    print(f"mixer 件数の参照先: {rip_target(0xD80FA0):#x} (期待 {MIX_COUNT:#x})")
    if not all(checks.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
