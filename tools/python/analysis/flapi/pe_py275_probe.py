#!/usr/bin/env python3
"""PY-275 (#3944): TUndoEvent_MovedFXTracks の生成結果の格納先 (キー 0x16) と、その取り出し経路の確認 (解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py275_probe.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import bisect
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pe_callgraph as pc  # noqa: E402

GEN = 0x101CA60
SETTER = 0x1019B30
MAP_SET = 0x102BB80
MAP_GET = 0x102BB20
KEYED_LOOP = 0x101A6E0
SLOT1_CALL = re.compile(r"qword ptr \[(r\w+) \+ (0x[0-9a-f]+|\d+)\]")
FAILS = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f" :: {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def main():
    insns = pc.load()
    addr_k = {a: k for k, (a, _, _) in enumerate(insns)}
    starts = pc.function_starts(insns)

    def fstart(a):
        i = bisect.bisect_right(starts, a) - 1
        return starts[i] if i >= 0 else None

    def before(a, n=4):
        k = addr_k[a]
        return [o for _, _, o in insns[max(0, k - n):k]]

    gen_setter = [a for a, m, o in insns if m == "call" and o == hex(SETTER) and fstart(a) == GEN]
    check("P1 0x101ca60 は 0x1019b30 を dl=0x16 で呼ぶ (生成結果は r8 で渡す)",
          len(gen_setter) == 1 and "dl, 0x16" in before(gen_setter[0]) and "r8, rax" in before(gen_setter[0]),
          str([hex(a) for a in gen_setter]))

    setter_body = [o for a, m, o in insns if m == "call" and o == hex(MAP_SET) and fstart(a) == SETTER]
    check("P2 0x1019b30 は [rbx+0x40] (Self の map) を第 1 引数にして 0x102bb80 を呼ぶ",
          len(setter_body) == 1 and any(o == "rcx, qword ptr [rbx + 0x40]" for a, m, o in insns
                                        if SETTER <= a < SETTER + 0x20), str(setter_body))

    store = [a for a, m, o in insns if m == "call" and o == "0x102b750" and fstart(a) == MAP_SET]
    check("P3 0x102bb80 は 0x102b750 (キー edx・値 r8 を格納) を呼ぶ",
          len(store) == 1, str([hex(a) for a in store]))

    get16 = [a for a, m, o in insns if m == "call" and o == hex(MAP_GET) and "dl, 0x16" in before(a)]
    check("P4 キー 0x16 の取り出し (0x102bb20 の dl=0x16) は 1 件 (0x101cab0 内)",
          len(get16) == 1 and fstart(get16[0]) == 0x101CAB0, str([hex(a) for a in get16]))

    after16 = [o for a, m, o in insns[addr_k[get16[0]] + 1:addr_k[get16[0]] + 8] if m == "call"]
    check("P5 0x101cab0 は取り出したオブジェクトを 0x1021b10 (初期化) に渡し、slot 1 は呼ばない",
          after16[:1] == ["0x1021b10"] and not any(
              SLOT1_CALL.search(o) and int(SLOT1_CALL.search(o).group(2), 0) == 8
              for a, m, o in insns[addr_k[get16[0]]:addr_k[get16[0]] + 12] if m == "call"),
          str(after16))

    tbl_writes = [a for a, m, o in insns if m == "mov" and o == "byte ptr [rax + 0xc], 0x16"]
    check("P6 0x16 を キー表 (0x101a6e0 の [rbp+0x118]) に書くのは 0x101a9b9 の 1 件",
          len(tbl_writes) == 1 and fstart(tbl_writes[0]) == KEYED_LOOP, str([hex(a) for a in tbl_writes]))

    keyed = [a for a, m, o in insns if m == "call" and o == hex(MAP_GET) and fstart(a) == KEYED_LOOP]
    tab = [a for a in keyed if "rdx, byte ptr [rbp + 0xe7]" in before(a, 4)]
    const_b = [a for a in keyed if "dl, 0xb" in before(a, 3)]
    check("P7 0x101a6e0 の getter 6 件は、キー表由来 (dl=[rbp+0xe7]) 4 件と固定キー 0xb 2 件",
          len(keyed) == 6 and len(tab) == 4 and len(const_b) == 2,
          f"表 {[hex(a) for a in tab]}、0xb {[hex(a) for a in const_b]}")

    dyn = [a for a, m, o in insns if m == "call" and (mm := SLOT1_CALL.search(o)) and int(mm.group(2), 0) == 8]
    check("P8 call [reg+8] の全件は 1638 件 (C3 と一致)", len(dyn) == 1638, f"{len(dyn)} 件")

    b_setters = [a for a, m, o in insns if m == "call" and o == "0x1019b30" and "dl, 0xb" in before(a, 3)]
    check("P9 キー 0xb の格納元は 0x101cc60 (0x16 とは別の生成関数)",
          b_setters and all(fstart(a) == 0x101CC60 for a in b_setters), str([hex(a) for a in b_setters]))
    print(f"\nsummary: {'ALL PASS' if not FAILS else 'FAIL: ' + ', '.join(FAILS)}")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
