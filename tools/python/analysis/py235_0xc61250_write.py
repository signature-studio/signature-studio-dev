#!/usr/bin/env python3
"""PY-235 (#4585 / 親 #3779 受入 1): 0xc61250 が [rbp+0x5b8] へ書く値の式を PE の命令列から検証する。

  FL_WIN64_DIR=<展開先> python3 analysis/py235_0xc61250_write.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
各 assert は REPORT_PY235.md の式 1 行に対応する (失敗すると非 0 で終わる)。
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
raw = open(PE, "rb").read()
pe = pefile.PE(data=raw, fast_load=True)
BASE = pe.OPTIONAL_HEADER.ImageBase
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)


def fo_of(va):
    rva = va - BASE
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.PointerToRawData + (rva - s.VirtualAddress)
    sys.exit(f"VA {va:#x} が section 外")


def dis(lo, hi):
    out = {}
    for i in md.disasm(raw[fo_of(lo):fo_of(hi) + 16], lo):
        if i.address >= hi:
            break
        out[i.address] = f"{i.mnemonic} {i.op_str}"
    return out


def check(label, cond):
    print(("ok   " if cond else "FAIL ") + label)
    if not cond:
        sys.exit(1)


def has(d, va, mnem, *subs):
    t = d.get(va, "")
    return t.split(" ", 1)[0] == mnem and all(s in t for s in subs)


def calls(d):
    return sorted(t.split(" ", 1)[1] for t in d.values() if t.startswith("call "))


# 呼出し元: 0x1046a30 の本体内で 0xc61250 を呼ぶのは 0x104a92b の 1 箇所
BODY = dis(0x1046A30, 0x104CCCA)
callers = [va for va, t in BODY.items() if t == "call 0xc61250"]
check("caller: 0xc61250 を呼ぶ箇所は本体内に 1 件 (0x104a92b)", callers == [0x104A92B])
check("caller 0x104a924: r8 = &[rbp+0x5b8] (out)", has(BODY, 0x104A924, "lea", "r8", "0x5b8"))
check("caller 0x104a91e: edx = eventId [rbp+0x5b0]", has(BODY, 0x104A91E, "mov", "edx", "0x5b0"))
check("caller 0x104a914: rax = [rip+0x598bf5] (= 0x15e3510)", has(BODY, 0x104A914, "mov", "rax", "[rip + 0x598bf5]"))
check("caller 0x104a91b: rcx = [rax] (obj)", has(BODY, 0x104A91B, "mov", "rcx", "[rax]"))
check("caller 0x104a932: al != 0 で 0x104a9cd へ (found は [rbp+0x5b8] を再計算しない)", has(BODY, 0x104A932, "jne", "0x104a9cd"))

# 0xc61250 本体
F = dis(0xC61250, 0xC612AA)
check("0xc61250: rbx = rcx (obj), esi = edx (eventId), rdi = r8 (out)",
      has(F, 0xC6125D, "mov", "rbx", "rcx") and has(F, 0xC61260, "mov", "esi", "edx") and has(F, 0xC61262, "mov", "rdi", "r8"))
check("0xc61250: T = [obj+0x30]", has(F, 0xC61273, "mov", "rcx", "[rbx + 0x30]"))
check("0xc61250: call 0xc62db0(T, eventId, &[rbp+0x28])", has(F, 0xC6127D, "call", "0xc62db0") and has(F, 0xC61279, "lea", "r8", "0x28"))
check("0xc61250: found = esi = eax (0xc62db0 の戻り)", has(F, 0xC61282, "mov", "esi", "eax"))
check("0xc61250: test sil,sil; je 0xc6129c", has(F, 0xC61292, "test", "sil") and has(F, 0xC61295, "je", "0xc6129c"))
check("0xc61250: 書く値 = [rbp+0x2c] (= qword [rbp+0x28] の上位 dword)", has(F, 0xC61297, "mov", "eax", "0x2c"))
check("0xc61250: store [rdi] = eax (0xc6129a)", has(F, 0xC6129A, "mov", "[rdi]", "eax"))
stores = [va for va, t in F.items() if t.split(" ", 1)[0] == "mov" and "[rdi]" in t.split(",")[0]]
check("0xc61250: [rdi] への store は 0xc6129a の 1 件", stores == [0xC6129A])
check("0xc61250: 呼出しは 0xc62db0 と vtable 間接呼出しのみ", [c for c in calls(F) if not c.startswith("qword ptr")] == ["0xc62db0"])

# 0xc62db0: idx = 0xc62630(T, eventId, K), K = 0xc626e0(T)。idx >= 0 のとき [rdi] = qword [arr + 16*idx + 8]、else [rdi] = 0
D = dis(0xC62DB0, 0xC62E02)
check("0xc62db0: 呼出しは 0xc626e0 と 0xc62630 のみ", calls(D) == ["0xc62630", "0xc626e0"])
check("0xc62db0: K = 0xc626e0(T)", has(D, 0xC62DC4, "call", "0xc626e0"))
check("0xc62db0: idx = 0xc62630(T, eventId, K)", has(D, 0xC62DD1, "call", "0xc62630") and has(D, 0xC62DCE, "mov", "r8d", "eax"))
check("0xc62db0: found = (idx >= 0) (setge al)", has(D, 0xC62DDC, "setge", "al") and has(D, 0xC62DD9, "test", "rcx, rcx"))
check("0xc62db0: arr = [T+8] (rdx)", has(D, 0xC62DE3, "mov", "rdx", "[rbx + 8]"))
check("0xc62db0: 要素 = [arr + idx*16 + 8] (rcx = 2*idx)", has(D, 0xC62DEA, "mov", "rcx", "[rdx + rcx*8 + 8]"))
check("0xc62db0: found で [rdi] = 要素 qword", has(D, 0xC62DEF, "mov", "qword ptr [rdi], rcx"))
check("0xc62db0: not found で [rdi] = 0", has(D, 0xC62DF4, "mov", "qword ptr [rdi], 0"))

# 0xc62630: T の open-address hash 表 (n = [arr-8]) を K で線形探査。空 slot (key -1) で ~slot (負) を返す
E = dis(0xC62630, 0xC626E0)
check("0xc62630: arr = [T+8] (rax), n = [arr-8] (r13)", has(E, 0xC6264A, "mov", "rax", "[rax + 8]") and has(E, 0xC62656, "mov", "r13", "[r13 - 8]"))
check("0xc62630: n == 0 で -2^63 を返す (not found)", has(E, 0xC6265F, "movabs", "rdi", "0x8000000000000000"))
check("0xc62630: p0 = sext32(K) & (n-1)", has(E, 0xC6266B, "movsxd", "rdi, esi") and has(E, 0xC62672, "and", "rdi, rax"))
check("0xc62630: entry = arr + 16*slot (r14)", has(E, 0xC62684, "lea", "r14, [rax + rcx*8]"))
check("0xc62630: key == -1 で ~slot を返す (not found)", has(E, 0xC6268B, "cmp", "eax, -1") and has(E, 0xC62690, "not", "rdi"))
check("0xc62630: key == K のとき Y.vt[+0x18](Y, aux @+4, eventId) で照合", has(E, 0xC62695, "cmp", "eax, esi") and has(E, 0xC626A5, "mov", "edx, dword ptr [r14 + 4]") and has(E, 0xC626AF, "call", "qword ptr [rax + 0x18]"))
check("0xc62630: 照合成功で slot を返す (found)", has(E, 0xC626B2, "test", "al, al") and has(E, 0xC626B4, "jne", "0xc626d0"))

# 0xc626e0: K = ((Y.vt[+0x20]() & 0x7fffffff) + 1) & 0x7fffffff, Y = [T+0x18]
G = dis(0xC626E0, 0xC62703)
check("0xc626e0: Y = [T+0x18]", has(G, 0xC626E4, "mov", "rax", "0x18]"))
check("0xc626e0: K = (Y.vt[+0x20]() & 0x7fffffff) + 1 & 0x7fffffff", has(G, 0xC626F1, "and", "eax, 0x7fffffff") and has(G, 0xC626F6, "add", "eax, 1") and has(G, 0xC626F9, "and", "eax, 0x7fffffff"))

# 0xc62720 (挿入側・0xc61250 の経路には無い): entry = {u32 key @+0, u32 aux @+4, u64 value @+8}, stride 16
H = dis(0xC62720, 0xC62772)
check("0xc62720: key @+0 = edx, aux @+4 = r9d, value qword @+8", has(H, 0xC62734, "mov", "dword ptr [rax], edx") and has(H, 0xC62736, "mov", "dword ptr [rax + 4], r9d") and has(H, 0xC62742, "mov", "qword ptr [rax + 8], rcx"))

print("PASS")
