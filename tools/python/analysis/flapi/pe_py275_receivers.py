#!/usr/bin/env python3
"""PY-275 (#4995 残件・#5471): 格納配列 [map+8] の読出し値が slot 1 (call [reg+8]) の receiver になるかの確認 (解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py275_receivers.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'

対象 3 関数 (0x69b640・0x8c9d20・0xb70190) について、逆アセの決まった命令列で次を検査する。
  - [map+8] 読出し箇所と slot 1 呼出し箇所の列挙
  - slot 1 の receiver のレジスタを作る直前の命令の出所
本 probe は関数内の命令列だけを見る。読出し値を引数として callee に渡した先の追跡はしない (REPORT_PY275.md §7a)。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pe_callgraph as pc  # noqa: E402

F_A, F_B, F_C = 0x69B640, 0x8C9D20, 0xB70190
FAILS = []
SLOT1 = re.compile(r"^call qword ptr \[(r\w+) \+ (?:0x8|8)\]$")
MAP_READ = re.compile(r"^mov (r\w+), qword ptr \[(r\w+) \+ (r\w+)\*8 \+ 8\]$")


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f" :: {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def main():
    insns = pc.load()
    addr_k = {a: k for k, (a, _, _) in enumerate(insns)}
    ints = [a for a, m, _ in insns if m == "int3"]
    ends = {}

    def fend(f):
        if f not in ends:
            ends[f] = min(a for a in ints if a > f)
        return ends[f]

    def txt(a):
        _, m, o = insns[addr_k[a]]
        return f"{m} {o}".strip()

    def body(f):
        hi = fend(f)
        return [a for a, _, _ in insns if f <= a < hi]

    def before(a, n):
        k = addr_k[a]
        return [txt(insns[j][0]) for j in range(max(0, k - n), k)]

    def hexes(xs):
        return [hex(x) for x in xs]

    print("bounds: " + ", ".join(f"{hex(f)}..{hex(fend(f))}" for f in (F_A, F_B, F_C)))

    fa, fb, fc = body(F_A), body(F_B), body(F_C)
    loads_a = [a for a in fa if MAP_READ.match(txt(a))]
    slots_a = [a for a in fa if SLOT1.match(txt(a))]
    check("R1 0x69b640 の [map+8] 読出しは 2 件 (69b74b・69b88e)",
          hexes(loads_a) == ["0x69b74b", "0x69b88e"], str(hexes(loads_a)))
    check("R2 0x69b640 の slot 1 呼出しは 5 件 (69b79e・69b7f1・69ba6c・69bdcc・69be0c)",
          hexes(slots_a) == ["0x69b79e", "0x69b7f1", "0x69ba6c", "0x69bdcc", "0x69be0c"], str(hexes(slots_a)))
    check("R3 0x69b7f1 の receiver は 0x68b3a0 の戻り値 (call 0x68b3a0 → mov rcx, rax → mov rbx, [rax])",
          before(0x69B7F1, 4) == ["call 0x68b3a0", "mov rcx, rax", "mov rdx, qword ptr [rbp + 0xc0]", "mov rbx, qword ptr [rax]"],
          str(before(0x69B7F1, 4)))
    single = [txt(a) for a in body(0x68B3A0)]
    check("R4 0x68b3a0 は [rip+...] の大域変数だけを読む (map の [reg+idx*8] を読まない)",
          any("rip" in o for o in single) and not any(MAP_READ.match(o) for o in single), str(single))
    for a in (0x69B79E, 0x69BA6C):
        check(f"R5 {hex(a)} の receiver は [rbp+0x120/0x128] 経由で [Self+0x44] (mov rax, [rax+0x44])",
              "mov rax, qword ptr [rax + 0x44]" in before(a, 6), str(before(a, 6)))
    check("R6 0x69b640 の slot 1 呼出し (0x69b7f1 を除く) の receiver は [rbp+0xd8]・[rbp+0xe0] (読出し値の格納先) を使わない",
          all(not any(o.endswith("[rbp + 0xd8]") or o.endswith("[rbp + 0xe0]") for o in before(a, 3))
              for a in slots_a if a != 0x69B7F1))

    loads_b = [a for a in fb if MAP_READ.match(txt(a))]
    slots_b = [a for a in fb if SLOT1.match(txt(a))]
    check("R7 0x8c9d20 の [map+8] 読出しは 1 件 (8c9e38)", hexes(loads_b) == ["0x8c9e38"], str(hexes(loads_b)))
    check("R8 0x8c9d20 の slot 1 呼出しは 1 件 (8ca1be)", hexes(slots_b) == ["0x8ca1be"], str(hexes(slots_b)))
    writes_b = [a for a in fb if txt(a) in ("mov qword ptr [rbp + 0x28], rcx", "mov qword ptr [rbp + 0x28], rax")]
    check("R9 0x8c9d20 の receiver [rbp+0x28] は 1 箇所 (8c9d8f) だけに書かれ、その直前は virtual call [rax+0x10]",
          hexes(writes_b) == ["0x8c9d8f"] and "call qword ptr [rax + 0x10]" in before(0x8C9D8F, 2),
          str(hexes(writes_b)) + " " + str(before(0x8C9D8F, 2)))

    loads_c = [a for a in fc if MAP_READ.match(txt(a))]
    slots_c = [a for a in fc if SLOT1.match(txt(a))]
    check("R10 0xb70190 の [reg+idx*8+8] 読出しは 1 件 (b7024b。固定テーブル [Self+0x950] 由来)",
          hexes(loads_c) == ["0xb7024b"], str(hexes(loads_c)))
    check("R11 0xb70190 の slot 1 呼出しは 1 件 (b70297)", hexes(slots_c) == ["0xb70297"], str(hexes(slots_c)))
    check("R12 0xb70190 の slot 1 receiver は [Self+0x988] (b7028a)。読出し値の格納先 rdi (新規オブジェクト) ではない",
          txt(0xB7028A) == "mov rax, qword ptr [rax + 0x988]"
          and "mov rdi, qword ptr [rax]" in before(0xB70297, 1),
          str(before(0xB70297, 2)))

    # 0x69b640 の r8 引数 (69bb8e) の先: 0x69b340 内の slot 1 receiver の出所 (#4995 未解決 1)
    f_r = body(0x69B340)
    slots_r = [a for a in f_r if SLOT1.match(txt(a))]
    check("R13 0x69b340 の slot 1 呼出しは 2 件 (69b496・69b52e)",
          hexes(slots_r) == ["0x69b496", "0x69b52e"], str(hexes(slots_r)))
    check("R14 0x69b340 の slot 1 receiver は [[this+0x10]] 由来 (69b465・69b48d・69b4fb・69b52b)",
          txt(0x69B465) == "mov rcx, qword ptr [rcx + 0x10]" and txt(0x69B48D) == "mov rbx, qword ptr [rcx]"
          and txt(0x69B4FB) == "mov rax, qword ptr [rax + 0x10]" and txt(0x69B52B) == "mov rbx, qword ptr [rax]",
          str([txt(0x69B465), txt(0x69B48D), txt(0x69B4FB), txt(0x69B52B)]))
    check("R15 69bb8e の r8 引数は [rbp+0xe0] の複写 [rbp+0xd0] (69bb4c→69bb53→69bb69)。0x69b340 の slot 1 receiver は rbx を [rcx]・[rax] から直接取る (r8・rsi 由来ではない)",
          txt(0x69BB4C) == "mov rax, qword ptr [rbp + 0xe0]" and txt(0x69BB53) == "mov qword ptr [rbp + 0xd0], rax"
          and txt(0x69BB69) == "mov r8, qword ptr [rbp + 0xd0]"
          and txt(0x69B48D) == "mov rbx, qword ptr [rcx]" and txt(0x69B52B) == "mov rbx, qword ptr [rax]",
          "")

    print(f"\nsummary: {'ALL PASS' if not FAILS else 'FAIL: ' + ', '.join(FAILS)}")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
