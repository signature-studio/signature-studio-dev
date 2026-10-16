#!/usr/bin/env python3
"""plugins.getPadInfo (0xd811c0) の引数・解決・戻り値の経路を PE の逆アセンブルで確かめる (PY-5351 / #5489)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/plugins_padinfo_facts.py

確認する事実 (いずれも block00031_PE.bin。根拠は REPORT_PY5351.md):
- 引数 (kwlist index, slotIndex, paramOption, paramIndex, useGlobalIndex) の既定値と格納先 ([rbp+0xac]・[rbp+0xa8]・[rbp+0xa0]・[rbp+0xa4]・[rbp+0x9c])
- slotIndex == -1 の経路: 0x1005730 で channel を解決し、0x132f780 で有効性を見る
- slotIndex != -1 の経路 (0xd81374〜): 件数検査・slot 0..9 の検査・mixer 配列 (stride 0x28f*8、オフセット 0x134c) から plugin を取る
- 値の取得: 0x1331340 → [obj]->vtbl[+0x20] → 得た obj の vtbl[+8](0x35, paramIndex, paramOption)
- paramOption == 2 のときだけ eax を 16 bit 語ごとに組み替える (0xff00ff・0xff00ff00)
- 戻り値: 整数を [0x15e4280] (実行時設定の関数ポインタ。import ではない) に渡す
- 範囲外・空 slot の code: -4 (0xfffffffffffffffc)・-8 (0xfffffffffffffff8)。PyArg 失敗は ebx そのまま (0 以下) を 0xd82c20 へ

実行すると PASS/FAIL を出し、1 つでも FAIL なら非 0 で終わる。
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
FN = 0xD811C0
END = 0xD814C3  # 関数末尾 (ret の次)

# (VA, 期待する逆アセンブル文字列の部分一致)
EXPECT = [
    (0xD811C0, "push rbp"),
    (0xD811E6, "mov dword ptr [rbp + 0xa8], 0xffffffff"),  # slotIndex 既定 -1
    (0xD811F0, "mov dword ptr [rbp + 0xa4], 0"),           # paramIndex 既定 0
    (0xD811FA, "mov dword ptr [rbp + 0xa0], 0"),           # paramOption 既定 0
    (0xD81204, "mov dword ptr [rbp + 0x9c], 0"),           # useGlobalIndex 既定 0
    (0xD81224, "lea rax, [rbp + 0xac]"),                   # index の格納先
    (0xD81277, "cmp dword ptr [rbp + 0xa8], -1"),
    (0xD81284, "mov rbx, 0xfffffffffffffffc"),             # code -4
    (0xD8128B, "mov ecx, dword ptr [rbp + 0xac]"),
    (0xD81291, "cmp dword ptr [rbp + 0x9c], 0"),
    (0xD812A2, "call 0x1005730"),
    (0xD812B6, "call 0x132f780"),
    (0xD812CE, "call 0x1331340"),
    (0xD812DE, "call qword ptr [rax + 0x20]"),
    (0xD812F8, "cmp dword ptr [rbp + 0xa0], 2"),
    (0xD81304, "mov edx, 0x35"),
    (0xD8131A, "call qword ptr [rax + 8]"),
    (0xD8131F, "and ecx, 0xff00ff"),
    (0xD81325, "and eax, 0xff00ff00"),
    (0xD81368, "mov rbx, 0xfffffffffffffff8"),            # code -8 (空 slot)
    (0xD81374, "mov rbx, 0xfffffffffffffffc"),
    (0xD8138B, "mov rcx, qword ptr [rip + 0x860e06]"),
    (0xD81394, "sub ecx, 1"),
    (0xD813B3, "cmp rax, 9"),
    (0xD813CB, "imul rcx, rcx, 0x28f"),
    (0xD813DD, "mov rsi, qword ptr [rax + rcx*8 + 0x134c]"),
    (0xD8135D, "call qword ptr [rax]"),                   # 戻り値の変換 (0x15e4280)
    (0xD81492, "mov ecx, ebx"),
    (0xD81494, "call 0xd82c20"),
    (0xD814B4, "mov rax, qword ptr [rbp + 0x68]"),
]


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = False
    code = pe.get_data(FN - base, END - FN)
    ins = {i.address: f"{i.mnemonic} {i.op_str}".strip() for i in md.disasm(code, FN)}
    fails = 0
    for va, want in EXPECT:
        got = ins.get(va)
        ok = got is not None and want in got
        if not ok:
            fails += 1
        print(("PASS" if ok else "FAIL"), hex(va), want, "|", got)
    print("FAIL 件数:", fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
