#!/usr/bin/env python3
"""PY-219 (#3615): 0x1046a30 の [rbp+0x5b8] (cur) の経路上流と、[rbp+0x4e8] の基底・添字を PE 上で照合する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py219_probe.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
REPORT_PY219.md の結論を照合する。終了 0 = 全 PASS。1 件でも FAIL なら終了 1。
"""
import bisect
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pe_callgraph as pc  # noqa: E402
import pefile  # noqa: E402

INS = pc.load()
STARTS = pc.function_starts(INS)
IDX = {a: i for i, (a, _, _) in enumerate(INS)}
TXT = {a: f"{m} {o}".strip() for a, m, o in INS}
N = len(INS)
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print("PASS" if ok else "FAIL", name, detail)


ENTRY = 0x1046A30
i0 = bisect.bisect_right(STARTS, ENTRY) - 1
END = STARTS[i0 + 1]
FN = [k for k, (a, _, _) in enumerate(INS) if ENTRY <= a < END]
PRED = {k: [] for k in range(N)}
SUCC = {k: [] for k in range(N)}
for k in FN:
    a, m, o = INS[k]
    nxt = k + 1 if k + 1 < N else None
    if m == "jmp":
        if int(o, 16) in IDX:
            SUCC[k].append(IDX[int(o, 16)])
    elif m.startswith("j"):
        if int(o, 16) in IDX:
            SUCC[k].append(IDX[int(o, 16)])
        if nxt is not None:
            SUCC[k].append(nxt)
    elif m not in ("ret", "ud2", "int3", "hlt") and nxt is not None:
        SUCC[k].append(nxt)
for k in FN:
    for s in SUCC[k]:
        PRED[s].append(k)


def writes_to(slot):
    pat = re.compile(r"^(mov|and|or|xor|add|sub|inc|dec) (dword|qword|byte|word) ptr \[" + re.escape(slot) + r"\]")
    return [k for k in FN if pat.match(TXT[INS[k][0]])]


def reaching(target, slot):
    ws = set(writes_to(slot))
    start = IDX[target]
    defs, seen, stack, entry_hit = set(), {start}, [start], False
    while stack:
        n = stack.pop()
        if not PRED[n] and n != start:
            entry_hit = True
        for p in PRED[n]:
            if p in seen:
                continue
            seen.add(p)
            if p in ws:
                defs.add(p)
                continue
            stack.append(p)
    return {INS[d][0] for d in defs}, entry_hit


def pure_closure(target):
    s = IDX[target]
    seen, st = {s}, [s]
    while st:
        n = st.pop()
        for p in PRED[n]:
            if p not in seen:
                seen.add(p)
                st.append(p)
    return seen


def fva(a):
    return INS[IDX[a]][0]


W58 = writes_to("rbp + 0x5b8")
check("[rbp+0x5b8] への dword mov の書込みは 74 件 (関数内)",
      len(W58) == 74, f"{len(W58)}")
OVL = re.compile(r"^(mov|and|or|xor|add|sub|inc|dec) (byte|word|dword|qword) ptr \[rbp \+ 0x5b[5-9a-f]\]")
check("[rbp+0x5b5〜0x5bf] への重なる書込み (dword mov 以外) は 0 件",
      [INS[k][0] for k in FN if OVL.match(TXT[INS[k][0]]) and k not in W58] == [])
check("[rbp+0x5b8] のアドレス取得は 0x104a924 の lea 1 件",
      [INS[k][0] for k in FN if TXT[INS[k][0]].startswith("lea") and "rbp + 0x5b8]" in TXT[INS[k][0]]] == [0x104A924])

r_cur, e1 = reaching(0x10485AA, "rbp + 0x5b8")
check("0x10485aa の直前の [rbp+0x5b8] の到達する最終書込みは 0x1048445 の 1 件 (エントリまで無書込みの経路 0)",
      r_cur == {0x1048445} and not e1, f"{[hex(x) for x in r_cur]} entry={e1}")

dom_seen = set()
st = [IDX[0x10485AA]]
dom_seen.add(IDX[0x10485AA])
bad = False
while st:
    n = st.pop()
    for p in PRED[n]:
        if INS[p][0] == 0x1048445 or p in dom_seen:
            continue
        dom_seen.add(p)
        if not PRED[p]:
            bad = True
        st.append(p)
check("0x1048445 は 0x10485aa の全経路を支配する (0x1048445 を避ける後ろ向き経路はエントリに届かない)", not bad)
check("隠れた書込み (lea r8・call 0xc61250 の 0x104a92b) は 0x1048445 を避ける経路に現れない",
      IDX[0x104A92B] not in dom_seen)

r_w, _ = reaching(0x10483EA, "rbp + 0x5b8")
check("0x10483ea の入力 W の到達集合は {0x1046d6b (edx), 0x10483d3 (0x40c660 の戻り値)}",
      r_w == {0x1046D6B, 0x10483D3}, f"{[hex(x) for x in sorted(r_w)]}")
check("0x1046d6b の直前まで edx は書き換えられない (0x1046a30〜0x1046d6b に edx/rdx への書込みは 0 件)",
      not [k for k in FN if INS[k][0] < 0x1046D6B and re.match(r"^(mov|xor|lea|add|sub|pop|movzx|movsxd) (edx|rdx|dl|dx)\b", TXT[INS[k][0]])])
check("0x10483d3 の直前は call 0x40c660 (cvtsd2si rax, xmm0 = 最近接丸め)",
      TXT.get(0x10483CE) == "call 0x40c660")

r_f, _ = reaching(0x1048476, "rbp + 0x5c0")
check("[rbp+0x5c0] (フラグ) の 0x1048476 への到達は 0x1046d71 (r8d) の 1 件",
      r_f == {0x1046D71}, f"{[hex(x) for x in r_f]}")
check("0x1048470〜0x104847b: test 0x20 が成立すると 0x104cc72 へ抜ける (0x1048481 へは進まない)",
      TXT.get(0x104847B) == "jne 0x104cc72" and PRED[IDX[0x104847B]] == [IDX[0x1048476]] and TXT.get(0x1048476) == "test eax, 0x20")
check("0x104cc72 は 0x10485aa の先行節閉包に入らない", IDX[0x104CC72] not in pure_closure(0x10485AA))
check("0x1048445: mov dword ptr [rbp+0x5b8], eax の直前は mov eax, [rbp+0x348] (clamp 結果)",
      TXT.get(0x104843F) == "mov eax, dword ptr [rbp + 0x348]")

r_348 = reaching(0x104843F, "rbp + 0x348")
check("[rbp+0x348] (clamp 結果) の書込みは 3 件 (0x10483f6・0x104840a・0x1048438)",
      [INS[k][0] for k in writes_to("rbp + 0x348")] == [0x10483F6, 0x104840A, 0x1048438],
      f"{[hex(INS[k][0]) for k in writes_to('rbp + 0x348')]}")

r_4e8 = reaching(0x10485AA, "rbp + 0x4e8")[0]
check("[rbp+0x4e8] の 0x10485aa への到達は 0x10474d8 の 1 件", r_4e8 == {0x10474D8})
check("0x10474d4 の基底: rax = *(*G + 8)、G = [0x15e2218]・添字 rcx = movsxd [rbp+0x580]",
      TXT.get(0x10474BF) == "mov rax, qword ptr [rip + 0x59ad52]" and TXT.get(0x10474C6) == "mov rax, qword ptr [rax]"
      and TXT.get(0x10474C9) == "mov rax, qword ptr [rax + 8]" and TXT.get(0x10474CD) == "movsxd rcx, dword ptr [rbp + 0x580]"
      and TXT.get(0x10474D4) == "mov rax, qword ptr [rax + rcx*8]")
r_580 = reaching(0x10474CD, "rbp + 0x580")[0]
check("[rbp+0x580] (添字) の 0x10474cd への到達は 0x10474a0 の 1 件 (= shr (エントリ ecx) 16)", r_580 == {0x10474A0},
      f"{[hex(x) for x in r_580]}")
check("0x10474a0 の直前: mov eax, [rbp+0x5b0] → shr eax, 0x10",
      TXT.get(0x104749D) == "shr eax, 0x10" and TXT.get(0x1047497) == "mov eax, dword ptr [rbp + 0x5b0]")
r_5b0 = reaching(0x1047497, "rbp + 0x5b0")[0]
check("[rbp+0x5b0] (エントリ ecx) の 0x1047497 への到達は 0x1046d65 の 1 件", r_5b0 == {0x1046D65})
check("0x1047497 への経路は 0x1047456 (jb) のみ (エントリ ecx が [0, 0x0fffffff] の範囲)",
      PRED[IDX[0x1047497]] == [IDX[0x1047456]] and TXT.get(0x1047456) == "jb 0x1047497")
check("境界検査は同じ G (= [0x15e2218]) の +0x10 に対して行う (0x10474b6 cmp ecx, [rax+0x10])",
      TXT.get(0x10474B6) == "cmp ecx, dword ptr [rax + 0x10]" and TXT.get(0x10474AD) == "mov rax, qword ptr [rax]")


def rip_target(insaddr):
    nxt = INS[IDX[insaddr] + 1][0]
    m = re.search(r"\[rip \+ (0x[0-9a-f]+)\]", TXT[insaddr])
    return nxt + int(m.group(1), 16)


check("[0x599d68]・[0x599d80] の RIP 先は同じスロット 0x15e2198 (clamp の上限 A は両方同じ)",
      rip_target(0x1048411) == 0x15E2198 and rip_target(0x1048429) == 0x15E2198)
check("[0x59ad6b]・[0x59ad52] の RIP 先は同じグローバル 0x15e2218 (G)",
      rip_target(0x10474A6) == 0x15E2218 and rip_target(0x10474BF) == 0x15E2218)

raw = open(os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin"), "rb").read()
pe = pefile.PE(data=raw, fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase


def read_va(va, n):
    rva = va - base
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            off = s.PointerToRawData + (rva - s.VirtualAddress)
            return raw[off:off + n]
    return None


ptr = struct.unpack("<Q", read_va(0x15E2198, 8))[0]
check("スロット 0x15e2198 の静的な値は 0x14188a8 (.data)", ptr == 0x14188A8, hex(ptr))
D = struct.unpack("<i", read_va(ptr, 4))[0]
check("0x14188a8 の dword は 502 (A = 502 - 2 = 500)", D == 502, str(D))
RIP_ST, RIP_LD = 0, 0
for k in range(N - 1):
    t = TXT[INS[k][0]]
    if "[rip + 0x" not in t:
        continue
    mm = re.search(r"\[rip \+ (0x[0-9a-f]+)\]", t)
    if INS[k + 1][0] + int(mm.group(1), 16) == 0x15E2198:
        if t.startswith("mov qword ptr [rip") or t.startswith("mov dword ptr [rip"):
            RIP_ST += 1
        elif re.match(r"^mov r[a-z0-9]+, ", t):
            RIP_LD += 1
check("0x15e2198 への RIP 相対の store は .text 全体で 0 件 (読出し mov r*,[rip] は %d 件)" % RIP_LD,
      RIP_ST == 0 and RIP_LD == 235, f"store={RIP_ST} load={RIP_LD}")
K = struct.unpack("<d", read_va(0x104CCE0, 8))[0]
check("定数 0x104cce0 (0x10483c6 の mulsd) = 1000 / 2^31", K == 1000 / 2**31, repr(K))

print(f"{sum(RESULTS)}/{len(RESULTS)} PASS")
sys.exit(0 if all(RESULTS) else 1)
