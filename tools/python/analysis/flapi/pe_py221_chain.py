#!/usr/bin/env python3
"""PY-221 (#3617): 0x11fba90 の `[rbp+0x140]` の上流を PE 上で照合する。0x11fbc44 の `r8d = [[rbp+0x140]+0x20]` (0x1192f80 の第 3 引数) の基底。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py221_chain.py
  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py221_chain.py --ablate-write 0x11fc526   (ネガティブコントロール)

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
  (<展開先>/extracted/block00031_PE.bin が存在すること)
終了 0 = 全 PASS。1 件でも FAIL なら終了 1。
"""
import argparse
import bisect
import os
import re
import sys

import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pe_callgraph as cg  # noqa: E402

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
INS = cg.load()
STARTS = cg.function_starts(INS)
IDX = {a: i for i, (a, _, _) in enumerate(INS)}
TXT = {a: (f"{m} {o}").strip() for a, m, o in INS}
MNEM = {a: m for a, m, _ in INS}
RESULTS = []

F_START = 0x11FBA90
SLOT = "[rbp + 0x140]"
LOOP_HEAD = 0x11FBB3D
READ_R8 = 0x11FBC40
CALL_1192F80 = 0x11FBC44
ADVANCE_6668D0 = 0x6668D0


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print("PASS" if ok else "FAIL", name, detail)


def next_addr(a):
    return INS[IDX[a] + 1][0]


def rip_target(a):
    m = re.search(r"\[rip ([+-]) (0x[0-9a-f]+)\]", TXT[a])
    if not m:
        return None
    d = int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
    return next_addr(a) + d


def func_range(va):
    i = bisect.bisect_right(STARTS, va) - 1
    s = STARTS[i]
    return s, STARTS[i + 1]


def first_operand(text):
    return text.split(" ", 1)[1].split(", ")[0] if " " in text else ""


def writes_to(lo, hi, slot):
    out = {}
    for a, m, o in INS:
        if lo <= a < hi and m not in ("cmp", "test", "push") and slot in first_operand(TXT[a]):
            out[a] = TXT[a]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ablate-write", default=None, help="この VA の書込みを観測から外す (ネガティブコントロール)")
    args = ap.parse_args()
    ablate = int(args.ablate_write, 16) if args.ablate_write else None

    s, e = func_range(F_START)
    check("F: 0x11fba90 は関数先頭", s == F_START and e == 0x11FC650, f"{hex(s)}..{hex(e)}")

    writes = writes_to(s, e, SLOT)
    if ablate is not None:
        writes.pop(ablate, None)
    exp_writes = {0x11FBB28: "mov qword ptr [rbp + 0x140], rax", 0x11FC526: "mov qword ptr [rbp + 0x140], rax"}
    check("W: [rbp+0x140] への書込みは 2 箇所 (初回 0x11fbb28・ループ末尾 0x11fc526)",
          writes == exp_writes, str({hex(k): v for k, v in writes.items()}))

    ok = TXT.get(0x11FBB23) == "call 0x6668d0" and TXT.get(0x11FBB28) == "mov qword ptr [rbp + 0x140], rax"
    ok = ok and TXT.get(0x11FBB37) == "je 0x11fc53b" and TXT.get(0x11FBB2F, "").startswith("cmp qword ptr [rbp + 0x140], 0")
    check("H: 初回の経路 0x11fbb23 call → 0x11fbb28 store → 0x11fbb2f null 判定 → 0x11fbb37 je (fallthrough で 0x11fbb3d へ)", ok)

    win = [a for a, _, _ in INS if LOOP_HEAD <= a <= READ_R8]
    calls = [a for a in win if MNEM[a] == "call"]
    slot_w = [a for a in win if SLOT in first_operand(TXT[a]) and MNEM[a] not in ("cmp", "test", "push")]
    check("N: 読出し窓 [0x11fbb3d, 0x11fbc40] に call も [rbp+0x140] への書込みも無い",
          not calls and not slot_w, f"窓 {len(win)} 命令・call {len(calls)}・書込み {len(slot_w)}")

    indirect = [a for a in win if (MNEM[a] == "jmp" and not TXT[a].split(" ", 1)[-1].startswith("0x")) or MNEM[a] == "ret"]
    check("N2: 窓内に間接 jmp と ret が無い (制御の飛び先が線形走査で決まる)", not indirect, str([hex(a) for a in indirect]))

    entry_in = []
    for a, m, o in INS:
        if m.startswith("j") and o.startswith("0x"):
            t = int(o, 16)
            if LOOP_HEAD < t <= READ_R8 and not (LOOP_HEAD <= a <= READ_R8):
                entry_in.append(hex(a))
    check("J: 窓の内部 (0x11fbb3d の次から 0x11fbc40 まで) へ窓の外から入る直接 jmp/jcc は 0", not entry_in, str(entry_in))

    heads = []
    for a, m, o in INS:
        if m.startswith("j") and o.startswith("0x") and int(o, 16) == LOOP_HEAD:
            heads.append(hex(a))
    check("L: 0x11fbb3d (ループ頭) への直接の飛び込みは 0x11fc535 の jne だけ",
          heads == ["0x11fc535"], str(heads))
    check("L2: 0x11fbc39 の読出しは [rbp+0x140] の値 (r8d = [rax+0x20]、0x11fbc44 は call 0x1192f80)",
          TXT.get(0x11FBC39) == "mov rax, qword ptr [rbp + 0x140]"
          and TXT.get(READ_R8) == "mov r8d, dword ptr [rax + 0x20]"
          and TXT.get(CALL_1192F80) == "call 0x1192f80",
          TXT.get(READ_R8, ""))

    G1 = rip_target(0x11FBAF5)
    check("G1: 0x11fbaf5 の大域 G = 0x15e2e18 (RIP 相対の解決)", G1 == 0x15E2E18 and TXT[0x11FBAF5].startswith("mov rax, qword ptr [rip"),
          hex(G1) if G1 else "None")
    plist = [TXT[a] for a in (0x11FBAF5, 0x11FBAFC, 0x11FBAFF, 0x11FBB06, 0x11FBB0D, 0x11FBB14, 0x11FBB18, 0x11FBB1C)]
    exp_plist = ["mov rax, qword ptr [rip + 0x3e731c]", "mov rax, qword ptr [rax]", "mov qword ptr [rbp + 0x100], rax",
                 "mov rax, qword ptr [rbp + 0x100]", "mov rcx, qword ptr [rbp + 0x100]", "mov rcx, qword ptr [rcx + 0x18]",
                 "mov qword ptr [rax + 0x20], rcx", "mov rcx, qword ptr [rbp + 0x100]"]
    check("P: 初回の P = *(*G) を [rbp+0x100] へ置き、P+0x20 を P+0x18 の値に設定してから call 0x6668d0 (rcx = P)",
          plist == exp_plist and TXT[0x11FBB23] == "call 0x6668d0", "")

    body = [TXT[a] for a, _, _ in INS if ADVANCE_6668D0 <= a <= 0x6668E6]
    exp_body = ["mov rax, qword ptr [rcx + 0x10]", "cmp rax, qword ptr [rcx + 0x20]", "jne 0x6668de",
                "xor eax, eax", "jmp 0x6668e6", "mov rax, qword ptr [rax + 8]",
                "mov qword ptr [rcx + 0x10], rax", "ret"]
    check("A: 0x6668d0 = カーソル P+0x10 を [node+8] で 1 つ進める (終端 P+0x20 と一致なら 0)",
          body == exp_body, "" if body == exp_body else str(body))

    tail = [TXT[a] for a in (0x11FC4E8, 0x11FC4EF, 0x11FC4F2, 0x11FC4F6, 0x11FC4FA, 0x11FC4FE, 0x11FC502, 0x11FC506,
                             0x11FC508, 0x11FC510, 0x11FC512, 0x11FC516, 0x11FC51A, 0x11FC51E, 0x11FC522, 0x11FC526,
                             0x11FC52D, 0x11FC535)]
    exp_tail = ["mov rax, qword ptr [rip + 0x3e6929]", "mov rax, qword ptr [rax]", "mov qword ptr [rbp + 0x78], rax",
                "mov rax, qword ptr [rbp + 0x78]", "mov rax, qword ptr [rax + 0x10]", "mov rcx, qword ptr [rbp + 0x78]",
                "cmp rax, qword ptr [rcx + 0x20]", "jne 0x11fc512", "mov qword ptr [rbp + 0x70], 0", "jmp 0x11fc522",
                "mov rax, qword ptr [rax + 8]", "mov rcx, qword ptr [rbp + 0x78]", "mov qword ptr [rcx + 0x10], rax",
                "mov qword ptr [rbp + 0x70], rax", "mov rax, qword ptr [rbp + 0x70]", "mov qword ptr [rbp + 0x140], rax",
                "cmp qword ptr [rbp + 0x140], 0", "jne 0x11fbb3d"]
    check("T: ループ末尾 0x11fc4e8〜0x11fc535 は 0x6668d0 と同じ前進 (同じ大域 G を読む・終端の再設定なし)",
          tail == exp_tail, "" if tail == exp_tail else str(tail))
    G2 = rip_target(0x11FC4E8)
    check("T2: ループ末尾の大域は G と同一 (0x15e2e18)", G2 == G1, hex(G2) if G2 else "None")

    hits = []
    for a, m, o in INS:
        t = rip_target(a)
        if t is not None and t == G1:
            hits.append(a)
    loads = [a for a in hits if re.match(r"^mov (r\w+), qword ptr \[rip ", TXT[a])]
    check("G: G (0x15e2e18) を指す RIP 相対の全 {0} 件はすべて読込み (mov reg, [rip+X])・書込みと lea は 0".format(len(hits)),
          len(hits) == len(loads) and len(hits) >= 1, f"hits={len(hits)} loads={len(loads)}")

    Y = 0x16B6E00
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    rva = G1 - base
    sec = next(x for x in pe.sections if x.VirtualAddress <= rva < x.VirtualAddress + x.Misc_VirtualSize)
    off = sec.PointerToRawData + (rva - sec.VirtualAddress)
    init = int.from_bytes(raw[off:off + 8], "little")
    sec_name = sec.Name.rstrip(b"\0").decode()
    check("I: G の .data 初期値 = Y (0x16b6e00)、G の節は .data", init == Y and sec_name == ".data",
          f"section={sec_name} init={hex(init)}")
    yhits = {}
    for a, m, o in INS:
        t = rip_target(a)
        if t == Y:
            yhits[a] = TXT[a]
    exp_y = {0xBD6901: "mov rax, qword ptr [rip + 0xae04f8]", 0xBD69E4: "mov rcx, qword ptr [rip + 0xae0415]",
             0xBD69F0: "mov qword ptr [rip + 0xae0405], 0", 0xBD6A28: "mov qword ptr [rip + 0xae03d1], rax"}
    check("Y: Y (0x16b6e00 = P の格納先) への RIP 相対の参照は 4 件 (読込み 2・書込み 2)",
          yhits == exp_y, str({hex(k): v for k, v in yhits.items()}))
    check("Y2: Y の書込み 0xbd6a28 は call 0x6666d0 (dl=1, r8d=0x40) の戻り値、0xbd69f0 は call 0x40faa0 の後の 0",
          TXT.get(0xBD6A23) == "call 0x6666d0" and TXT.get(0xBD6A1B) == "mov dl, 1"
          and TXT.get(0xBD6A1D) == "mov r8d, 0x40" and TXT.get(0xBD69EB) == "call 0x40faa0",
          "")

    n_fail = RESULTS.count(False)
    print(f"summary: {len(RESULTS) - n_fail}/{len(RESULTS)} PASS")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
