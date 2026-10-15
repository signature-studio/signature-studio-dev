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

    ok = all(RESULTS)
    print(f"{sum(RESULTS)}/{len(RESULTS)} PASS")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
