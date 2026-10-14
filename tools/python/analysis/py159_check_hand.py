#!/usr/bin/env python3
"""PY-159 (#3086): 65 件の書込みのうち、フレーム変数の合流越え (SLOT?) に依らない 7 件を手計算の式と突合する (実機不要)。

  python3 analysis/py159_check_hand.py <work/py53/fn.txt> [--negctl r8d]

- HAND は呼出し直前の代入を手で読んだ式。ACC は書込み前の [rbp+0x5b8] (機械側の ACC?⚠合流@... と同一視)。
- rint の定数 *(0x104cce0)・*(0x104cd00) は rip 相対の mulsd: 次命令の VA + disp で手計算した。
- CALL は ecx/edx/r8d を別々に式木にして比較する。VCALL は呼出し先が未確定のため突合しない (表のみ)。
- --negctl r8d: 0x1047719 の手計算の r8d を 0x3201 にする。mismatch 1 が出るはず (exit 1)。
- mismatch が 1 件以上なら exit 1。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import py64_check_expr as pc  # noqa: E402
import py88_writes as w  # noqa: E402

CALL_RE = re.compile(r"^CALL\[(0x[0-9a-f]+)\]\(ecx=(.*), edx=(.*), r8d=(.*)\)@0x[0-9a-f]+$")


def hand_entries(negctl):
    r8d_0 = "0x3201" if negctl == "r8d" else "0x3200"
    return [
        (0x1047719, ("CALL", "0x10469f0", {"ecx": "ACC", "edx": "0", "r8d": r8d_0})),
        (0x1047969, ("CALL", "0x10469f0", {"ecx": "ACC", "edx": "0", "r8d": "0x3200"})),
        (0x1047d98, ("CALL", "0x10469f0", {"ecx": "ACC", "edx": "0xffffed40", "r8d": "0x12c0"})),
        (0x104b305, ("CALL", "0x10469f0", {"ecx": "ACC", "edx": "0", "r8d": "0x3e80"})),
        (0x10483d3, ("RINT", "rint((f64(ACC) * *(0x104cce0)))")),
        (0x104a876, ("RINT", "rint((f64(ACC) * *(0x104cd00)))")),
        (0x104a999, ("RINT", "rint((f64(ACC) * *(0x104cd00)))")),
    ]


def compare(mach, hand):
    if hand[0] == "CALL":
        m = CALL_RE.match(mach)
        if not m:
            return False, f"CALL 形でない: {mach}"
        if m.group(1) != hand[1]:
            return False, f"CALL 先 {m.group(1)} != {hand[1]}"
        mine = {"ecx": m.group(2), "edx": m.group(3), "r8d": m.group(4)}
        for reg in ("ecx", "edx", "r8d"):
            hc = pc.parse_canon(hand[2][reg])
            mc = pc.parse_canon(pc.machine_norm(mine[reg]))
            if hc != mc:
                return False, f"{reg}: hand={hc!r} mach={mc!r}"
        return True, ""
    hc = pc.parse_canon(hand[1])
    mc = pc.parse_canon(pc.machine_norm(mach))
    return hc == mc, "" if hc == mc else f"hand={hc!r} mach={mc!r}"


NEGCTLS = ("r8d",)


def main():
    args = sys.argv[1:]
    negctl = None
    if "--negctl" in args:
        k = args.index("--negctl")
        if k + 1 >= len(args) or args[k + 1] not in NEGCTLS:
            print(f"usage: --negctl {{{'|'.join(NEGCTLS)}}} (値なし・未知の値はエラー)", file=sys.stderr)
            sys.exit(2)
        negctl = args[k + 1]
        del args[k:k + 2]
    ins, order = w.load(args[0])
    s = w.Slicer(ins, order)
    mism = 0
    for va, hand in hand_entries(negctl):
        i = s.idx[va]
        m, o = ins[va]
        mach = s.ev(w.parse_ops(o)[1], i, 0)
        ok, detail = compare(mach, hand)
        mism += 0 if ok else 1
        print(f"{va:#x}: {'一致' if ok else '不一致'}" + ("" if ok else f"\n    {detail}"))
    print(f"# n={len(hand_entries(negctl))} mismatch={mism}", file=sys.stderr)
    sys.exit(1 if mism else 0)


if __name__ == "__main__":
    main()
