#!/usr/bin/env python3
"""PY-198 (#3442): 0x12a4450 の 6 呼出し元の ecx 設定と、0x128f9e0 の [rbp+0x838] → 表セル 0x15e26a0 経由の書込みを PE 上で照合する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py198_probe.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
REPORT_PY198.md の結論 (呼出し元 6 件の ecx 設定命令・書込み経路・セルの静的値) を PE から照合する。
終了 0 = 全 PASS。1 件でも FAIL なら終了 1。
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
RAW = open(PE, "rb").read()
PEF = pefile.PE(data=RAW, fast_load=True)
BASE = PEF.OPTIONAL_HEADER.ImageBase
MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
MD.detail = True

CELL = 0x15E26A0
CUR = 0x193FA10
CALLEE = 0x12A4450

# (呼出し元の関数先頭, 呼出し命令の VA, ecx を最後に設定する命令の VA, その命令)
CALLERS = [
    (0x1021670, 0x10219F8, 0x10219E5, "mov ecx, eax"),
    (0x1046A30, 0x10485AA, 0x104859A, "mov ecx, dword ptr [rbp + 0x338]"),
    (0x1192F80, 0x1193C45, 0x1193C3E, "mov ecx, eax"),
    (0x12AB520, 0x12AB58B, 0x12AB583, "mov ecx, dword ptr [rdx + 0x10]"),
    (0x12AB710, 0x12AB911, 0x12AB90A, "neg ecx"),
    (0x12ACB70, 0x12ACBE7, 0x12ACBDF, "mov ecx, dword ptr [rbx + 0x18]"),
]

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(ok)
    print("PASS" if ok else "FAIL", name, detail)


def file_off(va):
    rva = va - BASE
    for s in PEF.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.PointerToRawData + (rva - s.VirtualAddress)
    raise SystemExit("VA が section 外: " + hex(va))


def sweep(start, end):
    out = []
    va = start
    while va < end:
        ins = next(MD.disasm(RAW[file_off(va):file_off(va) + 16], va), None)
        if ins is None:
            break
        out.append(ins)
        va += ins.size
    return out


def text(ins):
    return f"{ins.mnemonic} {ins.op_str}".strip()


def rip_target(ins):
    for op in ins.operands:
        if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
            return ins.address + ins.size + op.mem.disp
    return None


def at(insns, va):
    return next(i for i in insns if i.address == va)


def jumps_into(insns, lo, hi):
    return [hex(i.address) for i in insns
            if i.mnemonic.startswith("j") and i.op_str.startswith("0x")
            and lo <= int(i.op_str, 16) <= hi]


GPR = {}
for _b in ("a", "b", "c", "d"):
    for _n in (_b + "l", _b + "h", _b + "x", "e" + _b + "x", "r" + _b + "x"):
        GPR[_n] = "r" + _b + "x"
for _b in ("si", "di", "bp", "sp"):
    for _n in (_b, _b + "l", "e" + _b, "r" + _b):
        GPR[_n] = "r" + _b
for _k in range(8, 16):
    for _n in (f"r{_k}", f"r{_k}d", f"r{_k}w", f"r{_k}b"):
        GPR[_n] = f"r{_k}"


def fam(name):
    return GPR.get(name, name)


def cell_stores(insns, starts):
    """表セル由来のポインタ (読んだ直後のレジスタ・mov での複製) 経由の store を、分岐は両方辿って集める。
    call に渡したものは passed に入れる (呼出し先での書込みは数えない)。"""
    idx = {i.address: i for i in insns}
    work = [(ld.address + ld.size, frozenset([fam(ld.reg_name(ld.operands[0].reg))])) for ld in starts]
    seen, stores, passed = set(), [], []
    while work:
        va, s = work.pop()
        if (va, s) in seen or not s or va not in idx:
            continue
        seen.add((va, s))
        i = idx[va]
        ops = i.operands
        m = i.mnemonic
        if m == "ret" or (m == "jmp" and not i.op_str.startswith("0x")):
            continue
        if m == "jmp":
            work.append((int(i.op_str, 16), s))
            continue
        if m.startswith("j"):
            work.append((int(i.op_str, 16), s))
            work.append((va + i.size, s))
            continue
        if m == "call":
            if s & {"rcx", "rdx", "r8", "r9"}:
                passed.append(hex(va))
            work.append((va + i.size, s - {"rax", "rcx", "rdx", "r8", "r9", "r10", "r11"}))
            continue
        if ops and ops[0].type == capstone.x86.X86_OP_MEM and m not in ("cmp", "test", "lea"):
            if ops[0].mem.base and fam(i.reg_name(ops[0].mem.base)) in s:
                stores.append(hex(va))
        ns = s
        if ops and ops[0].type == capstone.x86.X86_OP_REG and m not in ("cmp", "test"):
            d = fam(i.reg_name(ops[0].reg))
            if (m == "mov" and len(ops) > 1 and ops[1].type == capstone.x86.X86_OP_REG
                    and fam(i.reg_name(ops[1].reg)) in s):
                ns = s | {d}
            else:
                ns = s - {d}
        work.append((va + i.size, frozenset(ns)))
    return stores, passed


def cell_static():
    off = file_off(CELL)
    return int.from_bytes(RAW[off:off + 8], "little")


check("cell 0x15e26a0 の静的値 == 0x193fa10", cell_static() == CUR, hex(cell_static()))

for fn, call_va, set_va, want in CALLERS:
    body = sweep(fn, call_va + 5)
    call = at(body, call_va)
    setter = at(body, set_va)
    between = [i for i in body if set_va < i.address < call_va]
    clobber = [text(i) for i in between if "ecx" in i.op_str or "rcx" in i.op_str]
    ok = (call.mnemonic == "call" and rip_target(call) is None
          and int(call.op_str, 16) == CALLEE
          and text(setter) == want and not clobber)
    check(f"呼出し元 {hex(call_va)} (in {hex(fn)}) の ecx 設定 = {want}", ok,
          f"set@{hex(set_va)} call@{hex(call_va)} between_ecx_writes={clobber}")

FN = 0x128F9E0
FN_END = 0x1294AB8
fbody = sweep(FN, FN_END)
frame_writes = [i for i in fbody if i.mnemonic == "mov" and "[rbp + 0x838]" in i.op_str
                and i.op_str.startswith("dword ptr [rbp + 0x838]")]
check("0x128f9e0 で [rbp+0x838] へ書くのは 1 箇所 (エントリの edx 保存)",
      len(frame_writes) == 1 and text(frame_writes[0]) == "mov dword ptr [rbp + 0x838], edx"
      and frame_writes[0].address == 0x1290067,
      f"{len(frame_writes)} 件 {[hex(i.address) for i in frame_writes]}")

g_load = at(fbody, 0x12900CA)
check("0x12900ca は表セル 0x15e26a0 を読む (mov rax, [rip+..])",
      g_load.mnemonic == "mov" and rip_target(g_load) == CELL, hex(rip_target(g_load) or 0))
check("0x12900d1: ecx = [rbp+0x838]", text(at(fbody, 0x12900D1)) == "mov ecx, dword ptr [rbp + 0x838]")
check("0x12900d7: *(表セル の指す先) = ecx",
      text(at(fbody, 0x12900D7)) == "mov dword ptr [rax], ecx")

ld = at(sweep(CALLEE, CALLEE + 0x180), 0x12A4528)
check("0x12a4528 は表セル 0x15e26a0 を読む", ld.mnemonic == "mov" and rip_target(ld) == CELL,
      hex(rip_target(ld) or 0))
cb = sweep(CALLEE, CALLEE + 0x180)
check("0x12a452f/0x12a4531: V1 = *(表セル の指す先) を [rbp+0x3c] へ保存",
      text(at(cb, 0x12A452F)) == "mov eax, dword ptr [rax]"
      and text(at(cb, 0x12A4531)) == "mov dword ptr [rbp + 0x3c], eax")
st = at(cb, 0x12A4583)
check("0x12a4583 は表セル 0x15e26a0 を読み、0x12a458d で [rbp+0x3c] の値を書き戻す",
      st.mnemonic == "mov" and rip_target(st) == CELL
      and text(at(cb, 0x12A458A)) == "mov ecx, dword ptr [rbp + 0x3c]"
      and text(at(cb, 0x12A458D)) == "mov dword ptr [rax], ecx")

check("0x129007c-0x129008e: idx < 0 は書込み側 (0x12900bb) に入らず、0 ≤ idx ≤ 0x1f5 だけ入る",
      text(at(fbody, 0x129007C)) == "test rax, rax"
      and text(at(fbody, 0x129007F)) == "jl 0x1290090"
      and text(at(fbody, 0x1290081)) == "movsxd rax, dword ptr [rbp + 0x838]"
      and text(at(fbody, 0x1290088)) == "cmp rax, 0x1f5"
      and text(at(fbody, 0x129008E)) == "jle 0x12900bb"
      and text(at(fbody, 0x12900B6)).startswith("jmp")
      and jumps_into(fbody, 0x12900BB, 0x12900D7) == ["0x129008e"]
      and jumps_into(fbody, 0x1290081, 0x129008E) == []
      and not [i for i in fbody if i.mnemonic == "call" and 0x12900BB <= i.address <= 0x12900D7])

SUB = sweep(0x12A4390, 0x12A4446)
check("0x12a4390: rbx = 引数 rcx。[rbx+0x3c] へ書くのは 0x12a4438 の 1 箇所で、0x12a4434 が一致したときだけ",
      text(at(SUB, 0x12A439D)) == "mov rbx, rcx"
      and rip_target(at(SUB, 0x12A442D)) == CELL
      and text(at(SUB, 0x12A4434)) == "cmp dword ptr [rcx], esi"
      and text(at(SUB, 0x12A4436)) == "jne 0x12a443b"
      and text(at(SUB, 0x12A4438)) == "mov dword ptr [rbx + 0x3c], eax"
      and jumps_into(SUB, 0x12A4438, 0x12A4438) == []
      and [hex(i.address) for i in SUB if text(i).startswith("mov dword ptr [rbx + 0x3c]")] == ["0x12a4438"])

CALLEE_BODY = sweep(CALLEE, 0x12A46A6)
calls_sub = [hex(i.address) for i in CALLEE_BODY if i.mnemonic == "call" and i.op_str == "0x12a4390"]
check("0x12a4450 → 0x12a4390 の直接 call は 2 箇所で、いずれも直前に rcx = rbp",
      calls_sub == ["0x12a4558", "0x12a4576"]
      and text(at(CALLEE_BODY, 0x12A4553)) == "mov rcx, rbp"
      and text(at(CALLEE_BODY, 0x12A4571)) == "mov rcx, rbp",
      f"calls={calls_sub}")
check("0x12a4450 内で [rbp+0x3c] へ書くのは 0x12a4531 (V1 保存) の 1 箇所",
      [hex(i.address) for i in CALLEE_BODY if text(i).startswith("mov dword ptr [rbp + 0x3c]")] == ["0x12a4531"])

st_f, passed_f = cell_stores(fbody, [i for i in fbody if i.mnemonic == "mov" and rip_target(i) == CELL])
check("0x128f9e0: 表セル由来ポインタ経由の直接 store は 0x12900d7 の 1 件",
      st_f == ["0x12900d7"], f"stores={st_f} passed_to_call={passed_f}")
st_c, passed_c = cell_stores(CALLEE_BODY, [i for i in CALLEE_BODY if i.mnemonic == "mov" and rip_target(i) == CELL])
check("0x12a4450: 表セル由来ポインタ経由の直接 store は 0x12a458d の 1 件",
      st_c == ["0x12a458d"], f"stores={st_c} passed_to_call={passed_c}")
st_s, passed_s = cell_stores(SUB, [i for i in SUB if i.mnemonic == "mov" and rip_target(i) == CELL])
check("0x12a4390: 表セル由来ポインタ経由の直接 store は 0 件",
      st_s == [], f"stores={st_s} passed_to_call={passed_s}")

print(f"{sum(RESULTS)}/{len(RESULTS)} PASS")
sys.exit(0 if all(RESULTS) else 1)
