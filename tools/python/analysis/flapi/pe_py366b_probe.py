#!/usr/bin/env python3
"""PY-366 (#4543) 続き: 0x4129f5 の大域 0x15eac80 (qword) の書き込み元の確認 (解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py366b_probe.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
  (<展開先>/extracted/block00031_PE.bin が存在すること)
終了 0 = 全 PASS。1 件でも FAIL なら終了 1。
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
G = 0x15EAC80
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    text = [s for s in pe.sections if s.Name.startswith(b".text")][0]

    def fo_of(va):
        return text.PointerToRawData + (va - base - text.VirtualAddress)

    def decode(start, end):
        out = []
        va = start
        while va < end:
            got = list(md.disasm(raw[fo_of(va):fo_of(va) + 16], va, 1))
            if not got:
                va += 1
                continue
            out.append(got[0])
            va += got[0].size
        return out

    def rip_ea(ins):
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                return ins.address + ins.size + op.mem.disp
        return None

    # 1. 0x4129ed-0x4129f5: [G] の非 0 判定 (0x412a12 へ飛ぶ)
    ins = {i.address: i for i in decode(0x4129ED, 0x4129F7)}
    check("0x4129ed: cmp qword [G],0 (G=0x15eac80)", rip_ea(ins[0x4129ED]) == G)
    check("0x4129f5: [G]!=0 なら 0x412a12 へ飛ぶ", ins[0x4129F5].mnemonic == "jne" and ins[0x4129F5].op_str == "0x412a12")

    # 2. 0x412a12-0x412a28: [G] の値を先頭ポインタとして 0x25 qword を復元して 0x412936 へ戻る
    seg = {i.address: i for i in decode(0x412A12, 0x412A2D)}
    check("0x412a12: rsi = [G] (復元元は G の指す先)", rip_ea(seg[0x412A12]) == G)
    check("0x412a25: rep movsq で 0x25 qword を複写 (rdi=G, rsi=[G])",
          seg[0x412A20].op_str == "ecx, 0x25" and seg[0x412A25].mnemonic == "rep movsq"
          and seg[0x412A25].op_str == "qword ptr [rdi], qword ptr [rsi]" and rip_ea(seg[0x412A19]) == G)
    check("0x412a28: 0x412936 のループへ戻る", seg[0x412A28].mnemonic == "jmp" and seg[0x412A28].op_str == "0x412936")

    # 3. G への store は .text 全体で rip 相対 mov に現れない (書き込みは間接)
    stores = []
    va = base + text.VirtualAddress
    code_end = va + text.Misc_VirtualSize
    cur = va
    while cur < code_end:
        got = list(md.disasm(raw[fo_of(cur):fo_of(cur) + 16], cur, 1))
        if not got:
            cur += 1
            continue
        i = got[0]
        cur += i.size
        if i.mnemonic == "mov" and i.op_str.startswith("qword ptr [rip") or i.mnemonic == "mov" and i.op_str.startswith("dword ptr [rip"):
            if i.op_str.count(",") == 1 and rip_ea(i) in (G, G + 4):
                stores.append(i.address)
    check("G への rip 相対 store は 0 件 (間接書き込み)", not stores, " ".join(hex(a) for a in stores))

    # 4. 0x412160 の r13 選択: G (0x412176) と 0x15eada8 (0x412186, [rbp+0x170]>=2)
    f = {i.address: i for i in decode(0x412160, 0x412190)}
    check("0x412176: r13 = G (lea)", f[0x412176].mnemonic == "lea" and rip_ea(f[0x412176]) == G)
    check("0x41217d-0x412186: [rbp+0x170]>=2 なら r13 = 0x15eada8 (別の枠)",
          f[0x41217D].op_str == "dword ptr [rbp + 0x170], 2" and rip_ea(f[0x412186]) == 0x15EADA8)

    # 5. 0x4121c3: [r13] = rax (rax は rcx の退避先) ← G 書き込みは r13 経由
    w = {i.address: i for i in decode(0x4121C3, 0x4121C7)}
    check("0x4121c3: mov [r13], rax (r13=G の時に G を書く)", w[0x4121C3].mnemonic == "mov" and w[0x4121C3].op_str == "qword ptr [r13], rax")

    # 6. 0x412160 の呼び出し元 (0x41d984) と 0x41d8f0 が含む関数の先頭
    d = {i.address: i for i in decode(0x41D984, 0x41D98A)}
    check("0x41d984: call 0x412160 (G 書き込み関数の唯一の call 元)", d[0x41D984].mnemonic == "call" and d[0x41D984].op_str == "0x412160")

    # 7. 0x412770 (rcx = G で呼ばれる): rdi = rax = G。0x41279b の rep movsq は G の指す先から G へ書く
    r = {i.address: i for i in decode(0x412770, 0x4127A5)}
    check("0x412770: rdi = rax = rcx (G) で 0x41279b の rep movsq が G 側へ書く",
          r[0x41277D].op_str == "rax, rcx" and r[0x412793].op_str == "rdi, rax" and r[0x412796].op_str == "ecx, 0x25"
          and r[0x41279B].mnemonic == "rep movsq" and r[0x41279B].op_str == "qword ptr [rdi], qword ptr [rsi]")
    c = {i.address: i for i in decode(0x4129E1, 0x4129ED)}
    check("0x4129e1-0x4129e8: rcx = G (lea) で 0x412770 を呼ぶ", rip_ea(c[0x4129E1]) == G and c[0x4129E8].mnemonic == "call" and c[0x4129E8].op_str == "0x412770")

    # 8. 0x412160 の G 側 (r13 = G) への書き込み: 0x4121b8 の rep movsq (rdi = r13+0x38)・[r13+0x10]・[r13+0x20]・[r13]
    f2 = {i.address: i for i in decode(0x4121AB, 0x4121C8)}
    check("0x412160: r13 側への書き込みは 4 箇所 (rep movsq 0x4121b8 を含む)",
          f2[0x4121AB].op_str == "rdi, [r13 + 0x38]" and f2[0x4121B8].mnemonic == "rep movsq"
          and f2[0x4121B8].op_str == "qword ptr [rdi], qword ptr [rsi]"
          and f2[0x4121BB].op_str == "qword ptr [r13 + 0x10], rdx" and f2[0x4121BF].op_str == "qword ptr [r13 + 0x20], r8"
          and f2[0x4121C3].op_str == "qword ptr [r13], rax")

    # 9. 0x4129f7-0x412a0d: [0x15e6068] (G と別の .bss 大域) の非 0 なら間接 call、0 なら 0x412a07 へ直行して ExitProcess
    x = {i.address: i for i in decode(0x4129F7, 0x412A12)}
    check("0x4129f7: cmp qword [0x15e6068], 0 (G とは別の大域)", rip_ea(x[0x4129F7]) == 0x15E6068)
    check("0x4129ff: je 0x412a07 (0 なら間接 call を飛ばす)", x[0x4129FF].mnemonic == "je" and x[0x4129FF].op_str == "0x412a07")
    check("0x412a01: call qword [0x15e6068] (間接 call。先は静的に未確定)",
          x[0x412A01].mnemonic == "call" and x[0x412A01].op_str.startswith("qword ptr [rip") and rip_ea(x[0x412A01]) == 0x15E6068)
    check("0x412a07: ecx = [0x13a5000] → call 0x406fc0 (ExitProcess の thunk)",
          x[0x412A07].mnemonic == "mov" and rip_ea(x[0x412A07]) == 0x13A5000 and x[0x412A0D].mnemonic == "call" and x[0x412A0D].op_str == "0x406fc0")
    # 10. 0x406fc0 の thunk が kernel32!ExitProcess であること (import 表照合)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    imports = {imp.address: f"{e.dll.decode()}!{imp.name.decode()}"
               for e in pe.DIRECTORY_ENTRY_IMPORT for imp in e.imports if imp.address is not None and imp.name}
    t = list(md.disasm(raw[fo_of(0x406FC0):fo_of(0x406FC0) + 6], 0x406FC0, 1))[0]
    check("0x406fc0: thunk は kernel32!ExitProcess", t.mnemonic == "jmp" and imports.get(rip_ea(t)) == "kernel32.dll!ExitProcess")

    ok = all(RESULTS)
    print(f"{sum(RESULTS)}/{len(RESULTS)} PASS")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
