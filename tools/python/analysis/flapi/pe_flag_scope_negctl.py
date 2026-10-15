#!/usr/bin/env python3
"""pe_flag_scope_check.py の対照 (#3649・PY-283)。正の対照と、1 件を変えたときの出力の変化を出す (1 コマンド)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_flag_scope_negctl.py

- 正の対照 (経路が見つかる): 0xc4dba0→0x10002a0 (深さ 1)・0xc4ecf0→0x10002a0 (深さ 2)・0xd5c800→0x10002a0・0xd5c800→0x63a730。
- 負の対照 (経路が無い): 0xc4dba0→0xd5c800。
- 変更 1 (経路探索の感度): 0xc4ecf0 の直接 call 0xc4f32e (→0xc4dba0) 1 件を外す。0xc4ecf0→0x10002a0 の経路が消えるはず。
- 変更 2 (0/12 の感度): 書込み関数 0xc4dba0 からハンドラ 0xd5c800 への直接 call を 1 件足す。到達数が 0/12 から 1/12 に変わるはず。
- 変更 3 (書込み VA の感度): 書込み 18 件の VA のうち 0xd1a2ac を +1 にずらす。mov byte ptr 命令の件数が 18 から 17 に変わるはず。
"""
import bisect
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pe_callgraph as pc  # noqa: E402
import pe_flag_scope_check as chk  # noqa: E402


def main():
    insns = pc.load()
    starts = pc.function_starts(insns)

    def func_of(va):
        i = bisect.bisect_right(starts, va) - 1
        return starts[i] if i >= 0 else None

    calls_of = collections.defaultdict(set)
    for a, m, o in insns:
        if m == "call" and o.startswith("0x"):
            calls_of[func_of(a)].add(int(o, 16))
    ins = {a: (m, o) for a, m, o in insns}
    writers = sorted({func_of(w[1]) for w in chk.WRITES})
    handler = chk.HANDLER

    def reach(cg):
        return sum(1 for f in writers if pc.walk([f], cg, {handler}, 60)[1])

    def path_txt(hits):
        if not hits:
            return "no path"
        return f"depth {len(hits[0]) - 1}: " + " -> ".join(hex(x) for x in hits[0][::-1])

    def byte_stores(vas):
        return sum(1 for va in vas if ins.get(va, ("", ""))[0] == "mov" and "byte ptr" in ins.get(va, ("", ""))[1])

    print("正の対照 (経路が見つかる)")
    for root, tgt in ((0xC4DBA0, 0x10002A0), (0xC4ECF0, 0x10002A0), (0xD5C800, 0x10002A0), (0xD5C800, 0x63A730)):
        print(f"  {hex(root)} -> {hex(tgt)}: {path_txt(pc.walk([root], calls_of, {tgt}, 60)[1])}")
    print("負の対照 (経路が無い)")
    print(f"  0xc4dba0 -> {hex(handler)}: {path_txt(pc.walk([0xC4DBA0], calls_of, {handler}, 60)[1])}")
    print(f"基準: 書込み関数到達 {reach(calls_of)} of {len(writers)}・mov byte ptr 命令 {byte_stores([w[1] for w in chk.WRITES])} of {len(chk.WRITES)}")

    cut = {k: set(v) for k, v in calls_of.items()}
    cut[0xC4ECF0].discard(0xC4DBA0)
    print("変更 1 (0xc4f32e の 0xc4ecf0→0xc4dba0 を外す)")
    print(f"  0xc4ecf0 -> 0x10002a0: {path_txt(pc.walk([0xC4ECF0], cut, {0x10002A0}, 60)[1])}")

    add = {k: set(v) for k, v in calls_of.items()}
    add[0xC4DBA0].add(handler)
    print("変更 2 (0xc4dba0→0xd5c800 の直接 call を 1 件足す)")
    print(f"  書込み関数到達 {reach(add)} of {len(writers)}")

    vas = [w[1] for w in chk.WRITES]
    shifted = [va + 1 if va == 0xD1A2AC else va for va in vas]
    print("変更 3 (0xd1a2ac を +1 にずらす)")
    print(f"  mov byte ptr 命令 {byte_stores(shifted)} of {len(shifted)}")


if __name__ == "__main__":
    main()
