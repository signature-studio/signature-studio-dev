#!/usr/bin/env python3
"""PY-273 5 段目 (#5407): ENTRY 格納関数 0xd843d0 の第 1 引数 (rcx = rbx) を、直接 call 全箇所で 1 段分類する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py273_d843_arg1.py

- 0xd843d0 は ENTRY の格納先 (rbx 9 の ENTRY 経路) で、直接呼出し 164 箇所 (pe_callgraph.py callers)。
- 各呼出し直前の rcx 族を pe_py203_edx_sites.resolve で分類する (窓は所属関数の先頭から呼出し直前まで)。
- stdout: TSV (call_va, caller_fn, class, value)。stderr: クラス別件数。
終了 0 = 完了。想定の 164 件と違えば終了 1。
"""
import collections
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pe_py273_base as B  # noqa: E402
import pe_py203_edx_sites as E  # noqa: E402

TARGET = 0xD843D0


def main():
    B.setup()
    sites = sorted(E.cg_sites.get(TARGET, []))
    if len(sites) != 164:
        sys.exit(f"直接 call の件数が想定と違う: {len(sites)}")
    cnt = collections.Counter()
    print("\t".join(["call_va", "caller_fn", "class", "value"]))
    for c in sites:
        fn = E.func_of(c)
        s, i = E.ADDR_IDX[fn], E.ADDR_IDX[c]
        r = E.resolve(s, i, "rcx")
        cnt[r["cls"]] += 1
        print("\t".join(E.clean(x) for x in [f"0x{c:x}", f"0x{fn:x}", r["cls"], E.desc(r)]))
    print("summary: " + ", ".join(f"{k}={v}" for k, v in sorted(cnt.items())), file=sys.stderr)
    print(f"rows={len(sites)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
