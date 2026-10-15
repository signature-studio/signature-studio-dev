#!/usr/bin/env python3
# 殻 (Delphi) の engine 読込経路の書込元を逆アセンブルで追う補助 (#3625 / PLG-F4-6)。
# 結論と行番号は tools/plugins/reverb_delay/REPORT_APPENDIX.md §18-7。 本スクリプトは材料を出すだけで判定はしない。
#   FL_WIN64_DIR=<fl-win64 展開先> python3 tools/plugins/reverb_delay/loadpath_trace.py <block> fn <VA>
#   ... <block> refs <VA> [size]   その範囲を rip 相対で参照する命令 (グローバル変数の読書き元)
#   ... <block> disp <disp>        メモリオペランドの変位が一致する命令 (ベースレジスタ不問)
#   ... <block> calls <VA> ...     関数の直接 call 先 (thunk は API 名)
#   ... <block> bytes <VA> <n>     生バイト (定数・文字集合の確認)
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shell_bind import Pe, direct_target, refs_into  # noqa: E402
from capstone.x86 import X86_OP_MEM  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("block", type=int)
    ap.add_argument("cmd", choices=["fn", "refs", "disp", "calls", "bytes"])
    ap.add_argument("args", nargs="*")
    a = ap.parse_args()
    root = os.environ.get("FL_WIN64_DIR")
    if not root:
        sys.exit("FL_WIN64_DIR を設定する (fl-win64 を展開。docs/WORKFLOW.md §11)")
    p = Pe(os.path.join(root, "extracted", f"block{a.block:05d}_PE.bin"))
    th = p.thunks()

    if a.cmd == "fn":
        for va in a.args:
            f = p.func_of(int(va, 16))
            if f is None:
                print(f"{va}: 関数が無い")
                continue
            print(f"func {f[0]:#x}-{f[1]:#x} size={f[1] - f[0]:#x}")
            for i in p.insns(f):
                t = direct_target(i)
                ann = f"  ; call {t:#x}" + (f" [{th[t]}]" if t in th else "") if t is not None else ""
                print(f"{i.address:#x}: {i.mnemonic} {i.op_str}{ann}")
    elif a.cmd == "refs":
        lo = int(a.args[0], 16)
        hi = lo + (int(a.args[1], 16) if len(a.args) > 1 else 1)
        for f, ins in refs_into(p, lo, hi):
            print(f"{ins.address:#x} (fn {f[0]:#x}): {ins.mnemonic} {ins.op_str}")
    elif a.cmd == "disp":
        d = int(a.args[0], 16)
        for f in p.code:
            for i in p.insns(f):
                for op in i.operands:
                    if op.type == X86_OP_MEM and op.mem.disp == d:
                        print(f"{i.address:#x} (fn {f[0]:#x}): {i.mnemonic} {i.op_str}")
    elif a.cmd == "calls":
        for va in a.args:
            f = p.func_of(int(va, 16))
            print(f"== fn {f[0]:#x} size={f[1] - f[0]:#x}")
            for i in p.insns(f):
                t = direct_target(i)
                if t is not None:
                    print(f"   {i.address:#x} call {t:#x}" + (f" [{th[t]}]" if t in th else ""))
    elif a.cmd == "bytes":
        va, n = int(a.args[0], 16), int(a.args[1], 16)
        b = p.read(va, n)
        print(f"{va:#x} len={n:#x}: {b.hex(' ') if b else 'unmapped'}")


if __name__ == "__main__":
    main()
