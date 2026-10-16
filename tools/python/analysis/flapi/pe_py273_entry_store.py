#!/usr/bin/env python3
"""PY-273 4 段目 (#5407): rbx ENTRY の格納先オフセット (+0x58・+0x1f4) の読み書きを .text 全体で数える。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py273_entry_store.py

- 0xd843d0 は第 3 引数 (rdi) を `mov [rbx+0x58], rdi` で格納する。0xd5e6c0・0xd615a0・0xd626c0 の ENTRY はこの経路。
- 0x1185840 は 0xff70c2 で `mov [rbx+0x1f4], rax` される。
- 各オフセットを `[reg+off]` で読む命令・書く命令を、所属関数の数つきで数える。
  オフセットだけでは格納先オブジェクトの型を区別できないため、件数は上限の目安に留まる。
終了 0 = 完了。
"""
import bisect
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pe_callgraph as cg  # noqa: E402


def main():
    insns = cg.load()
    starts = sorted(cg.function_starts(insns))

    def func_of(va):
        i = bisect.bisect_right(starts, va) - 1
        return starts[i] if i >= 0 else None

    for off in ["0x58", "0x1f4"]:
        reads, writes = [], []
        for a, m, o in insns:
            if f"+ {off}]" not in o:
                continue
            if m == "mov" and (o.startswith("qword ptr [") or o.startswith("dword ptr [")):
                writes.append(a)
            elif "[" in o:
                reads.append(a)
        print(f"OFF\t{off}\treads={len(reads)}\treads_funcs={len({func_of(a) for a in reads})}"
              f"\twrites={len(writes)}\twrite_funcs={len({func_of(a) for a in writes})}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
