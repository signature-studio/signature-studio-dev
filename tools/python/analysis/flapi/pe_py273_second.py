#!/usr/bin/env python3
"""PY-273 (#3927) 2 段目: pe_py273_base.py の 1 段目の上流を、基底レジスタの setter ごとに追う。

rbx/rax の MEM setter の基底について、基底の setter 直前の値を resolve し、
ENTRY (関数の引数のまま) に届く行は、その関数の直接呼出し元を caller_note で列挙する。
rbp は関数内のスロットなので、スロットの直前 store を見る (pe_py203_edx_sites の last_store)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py273_second.py

終了 0 = 完了。
"""
import argparse
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pe_py273_base as B  # noqa: E402
import pe_py203_edx_sites as E  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="PY-273: MEM 38 の基底の 2 段目 (ENTRY の呼出し元)")
    ap.parse_args()
    B.setup()

    sites = sorted(E.cg_sites.get(E.TARGET, []))
    cnt = collections.Counter()
    print("\t".join(["call_va", "base_reg", "base_setter", "upstream_class", "upstream", "note"]))
    for c in sites:
        fn = E.func_of(c)
        s, i = E.ADDR_IDX[fn], E.ADDR_IDX[c]
        r = E.analyze(c)
        if r["cls"] != "MEM":
            continue
        lw = E.last_writer(s, i, "rdx")
        setter = lw[0] if lw is not None else None
        base = B.mem_setter_base(setter)
        if base == "rbp":
            cnt[("rbp", "FRAME")] += 1
            continue
        bres = E.resolve(s, setter, base)
        cls = bres["cls"]
        cnt[(base, cls)] += 1
        note = ""
        if cls == "ENTRY":
            note = E.caller_note(fn, s)
        print("\t".join(E.clean(x) for x in [
            f"0x{c:x}", base, E.va(setter), cls, E.desc(bres), note,
        ]))

    print("summary: " + ", ".join(f"{b}/{k}={v}" for (b, k), v in sorted(cnt.items())), file=sys.stderr)


if __name__ == "__main__":
    main()
