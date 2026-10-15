#!/usr/bin/env python3
"""PY-126 (#3002): general.processRECEvent の呼出し鎖 (0xd69f00 → 0xd84740 → 0xd843d0 → 0xd846e0 → 0x1046a30) を PE から検証する。

  FL_WIN64_DIR=<展開先> python3 analysis/py126_process_rec_chain.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
各 assert は REPORT_PY126.md の VA 1 件に対応する (失敗すると非 0 で終わる)。
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
raw = open(PE, "rb").read()
pe = pefile.PE(data=raw, fast_load=True)
BASE = pe.OPTIONAL_HEADER.ImageBase


def fo_of(va):
    rva = va - BASE
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.PointerToRawData + (rva - s.VirtualAddress)
    sys.exit(f"VA {va:#x} が section 外")


def dis(va, n):
    fo = fo_of(va)
    return list(md.disasm(raw[fo:fo + n * 16], va))[:n]


def at(va, n=1):
    return dis(va, n)[-1]


def check(label, cond):
    print(("ok   " if cond else "FAIL ") + label)
    if not cond:
        sys.exit(1)


# 1. general.processRECEvent の handler 0xd69f00: PyArg 書式の後、0xd84740 を呼び、out[0] (status) と out+8 (dword) を読む
h = dis(0xD69F00, 80)
call_wrap = [i for i in h if i.mnemonic == "call" and i.op_str == "0xd84740"]
check("0xd69f00 が 0xd84740 を呼ぶ", len(call_wrap) == 1)
by_addr = {i.address: i for i in h}
check("0xd69f00: 0xd84740 呼出し直後 (0xd69f79) に status (out[0]) を rax へ読む", by_addr[0xD69F79].op_str == "rax, qword ptr [rbp + 0x58]")
check("0xd69f00: status 非 0 は 0xd69f94 (error 経路)", by_addr[0xD69F80].mnemonic == "jne" and by_addr[0xD69F80].op_str == "0xd69f94")
check("0xd69f00: 成功時は out+8 の dword (rbp+0x60) を読む", any(i.mnemonic == "mov" and "dword ptr [rbp + 0x60]" in i.op_str for i in h))
check("0xd69f00: error 経路は 0xd82c20 を呼ぶ", any(i.mnemonic == "call" and i.op_str == "0xd82c20" for i in h))

# 2. wrapper 0xd84740: eventId を zero-extend (r8d)、value と flags を sign-extend、sync=1、callback = 0xd846e0
ws = dis(0xD84740, 24)
check("0xd84740: eventId は mov r8d, r8d (unsigned)", any(i.mnemonic == "mov" and i.op_str == "r8d, r8d" for i in ws))
check("0xd84740: value は movsxd r9 (signed)", any(i.mnemonic == "movsxd" and i.op_str == "r9, r9d" for i in ws))
check("0xd84740: flags は movsxd (signed, [rsp+0x90])", any(i.mnemonic == "movsxd" and "rsp + 0x90" in i.op_str for i in ws))
check("0xd84740: sync flag = 1 (byte [rsp+0x50])", any(i.mnemonic == "mov" and i.op_str == "byte ptr [rsp + 0x50], 1" for i in ws))
check("0xd84740: dispatch 0xd843d0 を呼ぶ", any(i.mnemonic == "call" and i.op_str == "0xd843d0" for i in ws))
lea_cb = [i for i in ws if i.mnemonic == "lea" and i.op_str.startswith("rax, [rip")]
check("0xd84740: callback の lea は 1 箇所", len(lea_cb) == 1)
nxt = lea_cb[0].address + lea_cb[0].size
disp = int(lea_cb[0].op_str.split("rip")[1].strip(" ]").replace(" ", ""), 0)
check("0xd84740: callback = 0xd846e0 (次命令 + disp)", nxt + disp == 0xD846E0)

# 3. callback 0xd846e0: status = -2 → 述語真で status = 0 → 0x1046a30(eventId, value, flags)、結果を task+0x10 へ
cb = dis(0xD846E0, 24)
check("0xd846e0: 入口で status = -2 (0xfffffffffffffffe)", any(i.mnemonic == "mov" and "0xfffffffffffffffe" in i.op_str for i in cb))
check("0xd846e0: 述語 [vtbl+0x98] を呼ぶ", any(i.mnemonic == "call" and i.op_str == "qword ptr [rax + 0x98]" for i in cb))
check("0xd846e0: 述語真で status = 0", any(i.mnemonic == "mov" and i.op_str == "qword ptr [rbx + 0x60], 0" for i in cb))
check("0xd846e0: 0x1046a30 を呼ぶ", any(i.mnemonic == "call" and i.op_str == "0x1046a30" for i in cb))
check("0xd846e0: 結果を movsxd して task+0x10 へ", any(i.mnemonic == "movsxd" and i.op_str == "rax, eax" for i in cb))
check("0xd846e0: 第 1 引数は task+0x18 (eventId)", any(i.mnemonic == "mov" and i.op_str == "ecx, dword ptr [rbx + 0x18]" for i in cb))

# 4. 0x1046a30: 戻り値は [rbp+0x584] (int32)。早期 exit (global byte != 0) は -1、通常経路は [rbp+0x5b8] (初期値は引数 value)
body = dis(0x1046A30, 4680)
check("0x1046a30: 入口で ecx → [rbp+0x5b0] (eventId)", any(i.address == 0x1046D65 and i.op_str == "dword ptr [rbp + 0x5b0], ecx" for i in body))
check("0x1046a30: 入口で edx → [rbp+0x5b8] (value)", any(i.address == 0x1046D6B and i.op_str == "dword ptr [rbp + 0x5b8], edx" for i in body))
check("0x1046a30: 初期値 [rbp+0x584] = -1", any(i.address == 0x1046D79 and i.op_str == "dword ptr [rbp + 0x584], 0xffffffff" for i in body))
check("0x1046a30: 早期 exit 0x1046d8d は 0x104cc72 へ (値 -1 のまま返る)", any(i.address == 0x1046D8D and i.op_str == "0x104cc72" for i in body))
check("0x1046a30: 0x104cc6b で [rbp+0x5b8] を [rbp+0x584] へ複写", any(i.address == 0x104CC6B and i.op_str == "dword ptr [rbp + 0x584], eax" for i in body))
check("0x1046a30: 戻り値の読出しは 0x104cc65 の [rbp+0x5b8]", any(i.address == 0x104CC65 and i.op_str == "eax, dword ptr [rbp + 0x5b8]" for i in body))
rets = [i.address for i in body if i.mnemonic == "ret"]
check("0x1046a30: ret は 0x104ccca の 1 箇所", rets == [0x104CCCA])
writes_584 = [i.address for i in body if i.op_str.startswith("dword ptr [rbp + 0x584]") and i.mnemonic == "mov"]
check("0x1046a30: [rbp+0x584] への書込みは 2 箇所 (0x1046d79・0x104cc6b)", sorted(writes_584) == [0x1046D79, 0x104CC6B])
print("summary: processRECEvent 結果 = 0x1046a30 の戻り値 (int32)。0x1046a30 の分岐 (eventId 参照 38・flags 参照 186) は未確定")
