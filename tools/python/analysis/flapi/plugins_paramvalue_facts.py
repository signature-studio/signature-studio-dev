#!/usr/bin/env python3
"""plugins.getParamValueString の index・slotIndex・useGlobalIndex を PE の逆アセンブルで確かめる (PY-228 / #3656)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/plugins_paramvalue_facts.py

確認する事実 (いずれも block00031_PE.bin。根拠は REPORT_PY228.md §2):
- getParamValueString 0xd7f940: slotIndex == -1 なら 0x1005730 で channel を解決、slotIndex != -1 (0xd7fb34〜) なら
  mixer 配列 (件数 [0x15e2198]・stride 0x28f*8・slot 0..9) から slot の plugin を取り、0x132f780 で有効性を見る。
- 値の参照先は 0xd84740 (param id を引数に取る)。id は slot -1 が [obj+0x9c]+paramIndex+0x8000、
  slot >= 0 が 0x70008000 + (index*64+slot)<<16 + paramIndex (0x12be250 が (index*64+slot)<<16 を返す)。
- 範囲外の code: 0x1005730 の失敗・index/slot の範囲外は -4 (文言 "Index out of range")、空 slot (0x132f780 が偽) は -8 ("Plugin not valid")。
- paramIndex は [0, [obj+0x68]) で検査する (0xd7fa0f〜 と 0xd7fbb5〜)。
実行すると PASS/FAIL を出し、1 つでも FAIL なら非 0 で終わる。
"""
import os
import struct
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
PSTR = 0xD7F940
MIX_COUNT = 0x15E2198  # mixer track の件数 (dword)。PY-115 の setter と同じ変数
PARAM_INFO_GETTER = 0xD7FDA0
PARAM_SET = 0xD80160


def load():
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

    return raw, v2o


def disasm(raw, v2o, va, n):
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    fo = v2o(va)
    return [f"{i.mnemonic} {i.op_str}".strip() for _, i in zip(range(n), md.disasm(raw[fo:fo + n * 16], va))]


def main():
    raw, v2o = load()
    body = disasm(raw, v2o, PSTR, 400)
    getter = disasm(raw, v2o, PARAM_INFO_GETTER, 200)
    setter = disasm(raw, v2o, PARAM_SET, 140)
    core = disasm(raw, v2o, 0x12BE250, 8)
    obj_valid = disasm(raw, v2o, 0x132F780, 3)
    chan = disasm(raw, v2o, 0x1005730, 40)
    # mov rcx,[rip+x] (0xd7fb4b) の参照先 = mixer の件数
    fo = v2o(0xD7FB4B)
    ins = next(capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64).disasm(raw[fo:fo + 16], 0xD7FB4B))
    ref = ins.address + ins.size + int(ins.op_str.split("+")[1].split("]")[0], 16)
    checks = {
        "getParamValueString: slot == -1 の判定 (cmp [rbp+0xa8], -1)": any(s == "cmp dword ptr [rbp + 0xa8], -1" for s in body),
        "slot == -1 経路: 0x1005730 で channel 解決": any(s == "call 0x1005730" for s in body),
        "slot == -1 経路: 0x132f780 で有効性": any(s == "call 0x132f780" for s in body),
        "slot >= 0 経路: 件数 [0x15e2198] の参照先": ref == MIX_COUNT,
        "slot >= 0 経路: slot の上限 9 (cmp rax, 9)": any(s == "cmp rax, 9" for s in body),
        "slot >= 0 経路: 要素 = base + index*0x28f*8 (imul rcx,rcx,0x28f)": any(s == "imul rcx, rcx, 0x28f" for s in body),
        "slot >= 0 経路: 0x12be250(index, slot) を id の基底に使う": any(s == "call 0x12be250" for s in body),
        "id (slot >= 0): add r8d, 0x70008000": any(s == "add r8d, 0x70008000" for s in body),
        "id (slot -1): add r8d, 0x8000 (+ [obj+0x9c])": any(s == "add r8d, 0x8000" for s in body) and any(s == "add r8d, dword ptr [rbp + 0xa4]" for s in body),
        "値の参照: call 0xd84740 (2 回)": sum(1 for s in body if s == "call 0xd84740") == 2,
        "文字列化: call 0x104d2b0 → 0xc3cfa0": any(s == "call 0x104d2b0" for s in body) and any(s == "call 0xc3cfa0" for s in body),
        "paramIndex の範囲: count-1 との比較 (sub eax, 1)": sum(1 for s in body if s == "sub eax, 1") >= 2,
        "0x12be250 = ((index<<6)+slot)<<16": core[:4] == ["mov eax, ecx", "shl eax, 6", "add eax, edx", "shl eax, 0x10"],
        "0x132f780 = ([obj+0x64] >= 0)": obj_valid[:1] == ["cmp dword ptr [rcx + 0x64], 0"],
        "0x1005730: dl (useGlobalIndex>0) で 2 表を切替 (test dl, dl)": any(s == "test dl, dl" for s in chan),
        "getParamValue 0xd7fda0 も同じ channel 解決 (call 0x1005730)": any(s == "call 0x1005730" for s in getter),
        "getParamValue 0xd7fda0 も mixer 件数 [0x15e2198] 相当の cmp 9": any(s == "cmp rax, 9" for s in getter),
        "setParamValue 0xd80160 も channel/slot を解決 (call 0x1005730・0x132f780)": any(s == "call 0x1005730" for s in setter) and any(s == "call 0x132f780" for s in setter),
    }
    checks["code -4 の文言 (Index out of range): 0xd82e8c (ASCII)"] = raw[v2o(0xD82E8C):v2o(0xD82E8C) + 18] == b"Index out of range"
    checks["code -8 の文言 (Plugin not valid): 0xd82f3c (ASCII)"] = raw[v2o(0xD82F3C):v2o(0xD82F3C) + 16] == b"Plugin not valid"
    for k, ok in checks.items():
        print(("PASS " if ok else "FAIL ") + k)
    print(f"mixer 件数の参照先: {ref:#x} (期待 {MIX_COUNT:#x})")
    if not all(checks.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
