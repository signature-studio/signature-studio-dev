#!/usr/bin/env python3
"""PY-203 (#3476): 0x12a4450 の呼出し元の残りの引数の上流を PE 上で照合する。0x128f9e0 の edx 60 箇所は pe_py203_edx_sites.py が分類する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py203_probe.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
REPORT_PY203.md の結論 (確定した範囲) を PE から照合する。終了 0 = 全 PASS。1 件でも FAIL なら終了 1。
"""
import bisect
import os
import re
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pe_callgraph as pc  # noqa: E402

INS = pc.load()
STARTS = pc.function_starts(INS)
RAW = open(os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin"), "rb").read()
TXT = {a: f"{m} {o}".strip() for a, m, o in INS}
IDX = {a: i for i, (a, _, _) in enumerate(INS)}
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print("PASS" if ok else "FAIL", name, detail)


def fn(va):
    i = bisect.bisect_right(STARTS, va) - 1
    s = STARTS[i]
    e = STARTS[i + 1] if i + 1 < len(STARTS) else s + 0x10000
    return s, e


def window(lo, hi):
    return [(a, m, o) for a, m, o in INS if lo <= a <= hi]


def direct_callers(target):
    return [a for a, m, o in INS if m == "call" and o == hex(target)]


def jumps_into(lo, hi, outside):
    return [a for a, m, o in INS if m.startswith("j") and o.startswith("0x")
            and lo <= int(o, 16) <= hi and outside(a)]


def is_r9_write(text):
    return re.match(r"^(mov|movzx|movsx|movsxd|lea|xor|add|sub|pop|and|or)\s+(r9|r9d|r9w|r9b)\b", text) is not None


# 1. 0x1192f80 (呼出し元 0x1193c45): ecx = sgn(edi - esi)、edi/esi は [rbp+0x54] の上位 16bit / 下位 16bit
FN_A, FN_A_END = fn(0x1192F80)
check("0x1192f80 の先頭: 第 3 引数 r8d を [rbp+0x54] へ保存 (0x1192f99)",
      FN_A == 0x1192F80 and TXT.get(0x1192F99) == "mov dword ptr [rbp + 0x54], r8d", hex(FN_A))
w54 = [a for a, m, o in window(FN_A, FN_A_END) if m == "mov" and o.startswith("dword ptr [rbp + 0x54],")]
r54 = [a for a, m, o in window(FN_A, FN_A_END) if "dword ptr [rbp + 0x54]" in o and not o.startswith("dword ptr [rbp + 0x54],")]
check("[rbp+0x54] への書込みは 1 箇所 (0x1192f99)、読出しは 8 件 (NC: 読みも数えると 9 件)",
      w54 == [0x1192F99] and len(r54) == 8, f"write={[hex(x) for x in w54]} read={len(r54)}")
check("0x1193bcd-0x1193bd9: esi = [rbp+0x54] & 0xffff、edi = [rbp+0x54] >> 16",
      TXT.get(0x1193BCD) == "mov esi, dword ptr [rbp + 0x54]" and TXT.get(0x1193BD0) == "and esi, 0xffff"
      and TXT.get(0x1193BD6) == "mov edi, dword ptr [rbp + 0x54]" and TXT.get(0x1193BD9) == "shr edi, 0x10")
check("0x1193c1c-0x1193c45: ecx = sgn(edi - esi) を経て 0x12a4450 を呼ぶ",
      TXT.get(0x1193C1C) == "mov eax, edi" and TXT.get(0x1193C1E) == "sub eax, esi"
      and TXT.get(0x1193C3E) == "mov ecx, eax" and TXT.get(0x1193C45) == "call 0x12a4450")
check("0x1193c1c-0x1193c45 の sgn 区間に、区間外からの飛び込みは 0 件",
      jumps_into(0x1193C1D, 0x1193C45, lambda a: not (0x1193C1C <= a <= 0x1193C45)) == [])
check("0x1192f80 の直接呼出しは 1 件 (0x11fbc44)、r8d = [rax+0x20] を直前に設定",
      direct_callers(0x1192F80) == [0x11FBC44] and TXT.get(0x11FBC40) == "mov r8d, dword ptr [rax + 0x20]",
      [hex(x) for x in direct_callers(0x1192F80)])

# 2. 0x12ab710 (呼出し元 0x12ab911): ecx = -sgn(r9d)。r9d は 0x12ab71e で esi へ保存される第 4 引数
check("0x12ab71e: esi = r9d (0x12ab710 の第 4 引数)", TXT.get(0x12AB71E) == "mov esi, r9d")
callers_ab710 = direct_callers(0x12AB710)
check("0x12ab710 の直接呼出しは 1 件 (0x12ac257 in 0x12ac210)", callers_ab710 == [0x12AC257],
      [hex(x) for x in callers_ab710])
FN_C, _ = fn(0x12AC257)
check("0x12ac210 の先頭から 0x12ac257 まで r9/r9d への書込みは 0 件 (r9d は 0x12ac210 の第 4 引数のまま)",
      FN_C == 0x12AC210 and not [a for a, m, o in window(FN_C, 0x12AC256)
                                  if is_r9_write(f"{m} {o}")])
check("0x12ac210 の直接呼出しは 0 件 (上流は間接呼出し・未追跡)", direct_callers(0x12AC210) == [])

# 3. 間接呼出しのみと見られる関数 (rdx / 第 2 引数の上流が未追跡)
for fva in (0x12AB520, 0x12ACB70, 0x1021670):
    check(f"{hex(fva)}: 直接 E8 呼出し 0 件", direct_callers(fva) == [], "")
    refs = [a for a, m, o in INS if m != "call" and not m.startswith("j") and re.search(r"\b" + hex(fva) + r"\b", o)]
    check(f"{hex(fva)}: 即値・絶対参照の命令 0 件", refs == [], [hex(x) for x in refs])
    rr = subprocess.run([sys.executable, os.path.join(HERE, "pe_rip_refs.py"), format(fva, "x")],
                        capture_output=True, text=True, env=os.environ)
    check(f"{hex(fva)}: RIP 相対参照 0 件 (pe_rip_refs.py)", rr.returncode == 0 and "hits 0" in rr.stdout + rr.stderr,
          (rr.stdout + rr.stderr).strip()[:60])
pat = struct.pack("<I", 0x12AB520)
off = RAW.find(pat)
check("0x12ab520 の 4 バイトは .text のデータ島 (file 0xe796bb) に現れ、直後に ShortString 'TFXForm' がある (VMT 推定の根拠)",
      off == 0xE796BB and RAW[off + 8:off + 16] == b"\x07TFXForm", hex(off))

# 4. 0x1046a30 (呼出し元 0x10485aa): ecx = sgn([rbp+0x5b8] - [[rbp+0x4e8]+0x258])
FN_D, FN_D_END = fn(0x1046A30)
check("0x1048440-0x1048445: [rbp+0x5b8] は [rbp+0x348] の clamp 結果 (eax) で書かれる",
      TXT.get(0x104843F) == "mov eax, dword ptr [rbp + 0x348]" and TXT.get(0x1048445) == "mov dword ptr [rbp + 0x5b8], eax")
w5b8 = [a for a, m, o in window(FN_D, FN_D_END) if m == "mov" and o.startswith("dword ptr [rbp + 0x5b8],")]
check("[rbp+0x5b8] への 32bit 書込みは関数内に複数 (経路ごとの状態変数)", len(w5b8) > 1, f"{len(w5b8)} 件")
check("0x1048446-0x1048556 の内側へ、区間外の 0x10485bb から 0x104850f へ飛び込む枝がある",
      jumps_into(0x1048446, 0x1048556, lambda a: not (0x1048446 <= a <= 0x1048556)) == [0x10485BB])
w4e8 = [a for a, m, o in window(FN_D, FN_D_END) if m == "mov" and o.startswith("qword ptr [rbp + 0x4e8],")]
check("[rbp+0x4e8] への書込みは 1 箇所 (0x10474d8)、rax = [rax+rcx*8] (0x10474d4)",
      w4e8 == [0x10474D8] and TXT.get(0x10474D4) == "mov rax, qword ptr [rax + rcx*8]")

# 5. 0x45c290 (呼出し元 0x10219e0): eax = 戻り値 = [rbp+0x3c] の最後の書込み
FN_E, FN_E_END = fn(0x45C290)
check("0x45c290 の戻り値: 0x45c8c8 で eax = [rbp+0x3c]、0x45c8d0 で ret",
      FN_E == 0x45C290 and TXT.get(0x45C8C8) == "mov eax, dword ptr [rbp + 0x3c]" and TXT.get(0x45C8D0) == "ret")
SRC_OK = re.compile(r"call 0x(40f540|45c040|45c170|45c1c0|45c290)|"
                    r"(movsx|movzx|mov) (rax|eax), (byte|word|dword|qword) ptr \[rax( \+ (0x)?[0-9a-f]+)?\]")
w3c = [a for a, m, o in window(FN_E, FN_E_END) if o == "dword ptr [rbp + 0x3c], eax"]
prev_ok = [a for a in w3c if SRC_OK.fullmatch(TXT[INS[IDX[a] - 1][0]])]
check("0x45c290 の [rbp+0x3c] への書込み (36 件) の直前は、call (0x40f540・0x45c040・0x45c170・0x45c1c0・再帰 0x45c290) か [rax(+8)] の読出しのみ",
      len(w3c) == 36 and len(prev_ok) == len(w3c), f"write={len(w3c)} matched={len(prev_ok)}")
calls_n = sum(1 for a in w3c if TXT[INS[IDX[a] - 1][0]].startswith("call"))
check("0x45c290 の書込みのうち call 由来は 24 件、[rax...] 読出し由来は 12 件",
      calls_n == 24 and len(w3c) - calls_n == 12, f"call={calls_n}")

print(f"{sum(RESULTS)}/{len(RESULTS)} PASS")
sys.exit(0 if all(RESULTS) else 1)
