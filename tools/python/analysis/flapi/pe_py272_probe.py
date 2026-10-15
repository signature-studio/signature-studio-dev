#!/usr/bin/env python3
"""PY-272 (#3926): 0x45c290 (Variant* → int32 変換) の戻り値 eax の意味の照合 (解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py272_probe.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
  (<展開先>/extracted/block00031_PE.bin が存在すること)
終了 0 = 全 PASS。1 件でも FAIL なら終了 1。ネガティブコントロールは「期待が偽」を PASS とする。
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    imports = {}
    for entry in pe.DIRECTORY_ENTRY_IMPORT:
        for imp in entry.imports:
            if imp.address is not None:
                imports[imp.address] = f"{entry.dll.decode()}!{imp.name.decode() if imp.name else 'ord' + str(imp.ordinal)}"

    def fo_of(va):
        rva = va - base
        for s in pe.sections:
            if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
                return s.PointerToRawData + (rva - s.VirtualAddress)
        raise SystemExit(f"VA {va:#x} が section 外")

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def decode(start, end):
        fo = fo_of(start)
        out = {}
        for ins in md.disasm(raw[fo:fo + (end - start)], start):
            out[ins.address] = f"{ins.mnemonic} {ins.op_str}".strip()
        return out

    F = decode(0x45C290, 0x45C8D1)     # 0x45c290 の本体 (線形に連続)
    G = decode(0x40F540, 0x40F568)     # 例外送出の薄いラッパ (cl=4 / cl=5)
    W = decode(0x45C170, 0x45C1BF)     # Variant → VT_I4 の強制変換 (VariantChangeTypeEx 形)
    T = decode(0x457270, 0x457276)     # VariantInit の thunk

    def at(d, va):
        return d.get(va, "")

    # --- 0x45c290 の枠: 引数 rcx = Variant*, 戻り値 = [rbp+0x3c] (eax) ---
    check("0x45c290: 第 1 引数 rcx を [rbp+0x50] に保存", at(F, 0x45C29C) == "mov qword ptr [rbp + 0x50], rcx")
    check("0x45c290: 型ワード = movzx rax, word [arg+0]", at(F, 0x45C2A5) == "movzx rax, word ptr [rax]")
    check("0x45c8c8: 戻り値 = mov eax, [rbp+0x3c]", at(F, 0x45C8C8) == "mov eax, dword ptr [rbp + 0x3c]")
    check("0x45c8d0: ret (戻り値は eax の 1 語)", at(F, 0x45C8D0) == "ret")

    # --- 型ごとの写像 (case → 0x45c290 内の書込み先) ---
    check("型 0 (VT_EMPTY): 0 を返す (0x45c3d8)", at(F, 0x45C3D8) == "mov dword ptr [rbp + 0x3c], 0")
    check("型 2 (VT_I2): movsx word [arg+8] (0x45c406)", at(F, 0x45C406 + 4) == "movsx rax, word ptr [rax + 8]")
    check("型 3 (VT_I4): mov eax, [arg+8] (0x45c417)", at(F, 0x45C417 + 4) == "mov eax, dword ptr [rax + 8]")
    check("型 0xb (VT_BOOL): movsx word [arg+8] (0x45c4ef)", at(F, 0x45C4EF + 4) == "movsx rax, word ptr [rax + 8]")
    check("型 0x11 (VT_UI1): movzx byte [arg+8] (0x45c511)", at(F, 0x45C511 + 4) == "movzx rax, byte ptr [rax + 8]")
    check("型 0x12 (VT_UI2): movzx word [arg+8] (0x45c522)", at(F, 0x45C522 + 4) == "movzx eax, word ptr [rax + 8]")
    check("型 0xc (VT_VARIANT): 内側の Variant* へ再帰 (0x45c58f → call 0x45c290)",
          at(F, 0x45C597) == "call 0x45c290")
    check("型 8 (VT_BSTR): 文字列系 0x45c040 へ (0x45c4e2)", at(F, 0x45C4E2) == "call 0x45c040")
    check("型 9 / 0xd: VT_I4 強制変換 0x45c170 へ (0x45c5a8)", at(F, 0x45C5A8) == "call 0x45c170")

    # --- 範囲チェック → 例外 0x40f540 ---
    check("型 4/5/7: 結果を 32bit 符号つき範囲に入れる (rcx = 0x80000000 + x; cmp rcx, 0xffffffff)",
          at(F, 0x45C443) == "cmp rcx, rdx" and at(F, 0x45C43E) == "mov edx, 0xffffffff")
    check("範囲外は 0x40f540 へ (0x45c448)", at(F, 0x45C448) == "call 0x40f540")
    check("型 0x14 (VT_I8) の範囲外も 0x40f540 (0x45c565)", at(F, 0x45C565) == "call 0x40f540")
    check("型 0x15 (VT_UI8) は 0x7fffffff 上限 (0x45c57a)", at(F, 0x45C57A) == "cmp rax, 0x7fffffff")

    # --- 0x40f540 / 0x40f560 = 例外送出の薄いラッパ ---
    check("0x40f540: cl = 4 で 0x4096d0 へ", at(G, 0x40F548) == "mov cl, 4" and at(G, 0x40F54E) == "call 0x4096d0")
    check("0x40f560: cl = 5 で 0x4096d0 へ", at(G, 0x40F568) == "mov cl, 5" if 0x40F568 in G else
          at(decode(0x40F560, 0x40F56E), 0x40F568) == "mov cl, 5")

    # --- 0x45c170: VariantInit → VariantChangeTypeEx(dest, src, 0x400, 0, VT_I4) → dest.lVal ---
    check("0x45c170: VariantInit(&tmp) を先に呼ぶ (0x457270)", at(W, 0x45C180) == "call 0x457270")
    check("0x457270 は oleaut32!VariantInit の thunk", imports.get(0x1971140) == "oleaut32.dll!VariantInit"
          and at(T, 0x457276) == "" and at(T, 0x457270) == "jmp qword ptr [rip + 0x1519eca]")
    check("0x45c170: LCID 0x400 (r8d) と flags 0 (r9)", at(W, 0x45C18C) == "mov r8d, 0x400"
          and at(W, 0x45C192) == "xor r9, r9")
    check("0x45c170: 第 5 引数 vt = 3 (VT_I4) を [rsp+0x20] へ", at(W, 0x45C195) == "mov word ptr [rsp + 0x20], 3")
    check("0x45c170: 戻り値 = dest.lVal = [rbp+0x40] (VARIANT の +8)",
          at(W, 0x45C1B5) == "mov eax, dword ptr [rbp + 0x40]")

    # --- 静的 import に無い間接 call (実行時に設定される関数ポインタ) は、確定扱いにしない ---
    W_slot = 0x45C19C + 7 + 0x1187D05
    check("0x45c170 の間接 call 先は静的 import に無い (VariantChangeTypeEx 形、推定)",
          W_slot not in imports and at(W, 0x45C1A3) == "call qword ptr [rax]", f"slot={W_slot:#x}")

    # --- ネガティブコントロール: 偽の期待は PASS (= 照合が自明に通らないこと) ---
    neg1 = at(F, 0x45C406 + 4) == "mov eax, dword ptr [rax + 8]"   # 型 2 を型 3 の式と誤認した期待 (偽のはず)
    check("ネガティブ: 型 2 の式を型 3 の式と誤認した期待は偽", not neg1)
    neg2 = at(G, 0x40F548) == "mov cl, 5"                          # 0x40f540 を cl=5 と誤認 (偽のはず)
    check("ネガティブ: 0x40f540 の cl を 5 と誤認した期待は偽", not neg2)

    print(f"\n{sum(RESULTS)}/{len(RESULTS)} PASS")
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
