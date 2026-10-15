#!/usr/bin/env python3
"""findEventID の未発見時の値 (helper 0xf8c8e0 → fallback 0xf78640 → 0xf784c0) と値変換器 (global 0x15e4280) を FLEngine PE で再確認する (PY-400 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py400_probe.py

REPORT_PY390.md §3・§4 の未確定 2 点を、命令と参照先の assert で固定する。assert が落ちたら PE が変わっている。
展開: tar --zstd -xf <artifacts>/fl-win64.tar.zst -C <展開先>
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
CONVERTER_GLOBAL = 0x15E4280


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True

    def v2o(va):
        rva = va - base
        for s in pe.sections:
            if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
                return s.PointerToRawData + (rva - s.VirtualAddress)
        sys.exit(f"VA {va:#x} が section 外")

    def decode(va, count):
        """va から count 命令を関数単位で読む (線形全体走査は整列が崩れるので使わない)。"""
        out = {}
        for i, ins in enumerate(md.disasm(raw[v2o(va):v2o(va) + count * 16], va)):
            if i >= count:
                break
            out[ins.address] = ins
        return out

    def rip_ea(ins):
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                return ins.address + ins.size + op.mem.disp
        return None

    checks = []

    def ok(cond, label):
        checks.append((bool(cond), label))
        print(("OK   " if cond else "NG   ") + label)

    # 1. findEventID の未発見経路: helper 0xf8c8e0 は見つからないと edi=-1 のまま。fallback 0xf78640 を通す。
    h = decode(0xF8C8E0, 80)
    ok(h[0xF8C8ED].mnemonic == "or" and h[0xF8C8ED].op_str == "edi, 0xffffffff",
       "helper 0xf8c8e0: 初期値 edi=-1 (0xf8c8ed)")
    ok(h[0xF8C95C].mnemonic == "call" and int(h[0xF8C95C].op_str, 16) == 0xF78640,
       "helper 0xf8c8e0: fallback 0xf78640 を呼ぶ (0xf8c95c)")
    ok(h[0xF8C965].mnemonic == "or" and h[0xF8C965].op_str == "edi, 0xffffffff",
       "helper 0xf8c8e0: fallback 対象が無いときも edi=-1 (0xf8c965)")

    f = decode(0xF78640, 6)
    ok(f[0xF7864C].mnemonic == "call" and int(f[0xF7864C].op_str, 16) == 0xF784C0,
       "fallback 0xf78640: 0xf784c0 を呼び eax をそのまま返す (0xf7864c)")

    c = decode(0xF784C0, 0x80)
    ok(c[0xF784DD].mnemonic == "or" and c[0xF784DD].op_str == "eax, 0xffffffff",
       "0xf784c0: 戻り値の初期値 -1 (0xf784dd)")
    ok(c[0xF78573].mnemonic == "je" and int(c[0xF78573].op_str, 16) == 0xF785FF,
       "0xf784c0: 対象 object (rbx) が 0 なら戻り値 -1 のまま 0xf785ff へ (0xf78573)")
    ok(c[0xF78608].mnemonic == "mov" and c[0xF78608].op_str == "eax, dword ptr [rbp + 0x3c]",
       "0xf784c0: 戻りは [rbp+0x3c] (未発見時は -1) (0xf78608)")

    # 2. 変換器: 0xd75b9f が [0x15e4280] を読み、その指す先を call する。
    d = decode(0xD75B80, 12)
    ok(rip_ea(d[0xD75B9F]) == CONVERTER_GLOBAL and d[0xD75BA6].mnemonic == "call"
       and d[0xD75BA6].op_str == "qword ptr [rax]",
       "findEventID: 0xd75b9f が global 0x15e4280 を読み call [rax] (0xd75ba6)")
    d76 = decode(0xD7611A, 4)
    ok(rip_ea(d76[0xD76120]) == CONVERTER_GLOBAL and d76[0xD76127].mnemonic == "call",
       "isDoubleClick: 0xd76120 が同じ global 0x15e4280 を読み call [rax] (0xd76127)")

    slot_static = int.from_bytes(raw[v2o(CONVERTER_GLOBAL):v2o(CONVERTER_GLOBAL) + 8], "little")
    ok(slot_static == 0x16B8298,
       "global 0x15e4280 の静的初期値は 0x16b8298 (関数ポインタ格納場所)")

    # 3. 0x16b8298 への登録: 0xc396c5 が 0x4235f0 の戻りを格納し、引数の名前は 0xc3a292 の UTF-16 "PyLong_FromLong"。
    r = decode(0xC39660, 30)
    ok(r[0xC396C0].mnemonic == "call" and int(r[0xC396C0].op_str, 16) == 0x4235F0,
       "登録 0xc396c0: 0x4235f0 (名前解決) を呼ぶ")
    ok(rip_ea(r[0xC396C5]) == 0x16B8298 and r[0xC396C5].mnemonic == "mov",
       "登録 0xc396c5: 解決結果を 0x16b8298 に格納")
    name_va = rip_ea(r[0xC396B9])
    ok(name_va == 0xC3A292, "登録 0xc396b9: 名前文字列 0xc3a292 を渡す")
    name = raw[v2o(name_va):v2o(name_va) + 64].decode("utf-16-le").split("\x00")[0]
    ok(name == "PyLong_FromLong", f"名前文字列 0xc3a292 == {name!r}")

    print("all checks passed" if all(x for x, _ in checks) else "CHECK FAILED")
    if not all(x for x, _ in checks):
        sys.exit(1)


if __name__ == "__main__":
    main()
