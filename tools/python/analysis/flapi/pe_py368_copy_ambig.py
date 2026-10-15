#!/usr/bin/env python3
"""PY-368 (#4588): 0x128f9e0 の edx の COPY 7・AMBIG 8 の複製元の基底を 2 段目まで分類する。

pe_py203_edx_sites.py の分類で COPY・AMBIG になった 15 箇所について、複製元 (mov edx, reg の reg) の
出どころを resolve で追い、その出どころが MEM [base+X] なら基底レジスタの直前値を 1 段分類する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py368_copy_ambig.py

終了 0 = 完了。想定の COPY 7・AMBIG 8 と違えば終了 1。
"""
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pe_py203_edx_sites as E  # noqa: E402
import pe_py273_base as B  # noqa: E402


def src_of_setter(s, setter):
    """mov edx, reg の reg の族。それ以外は None。"""
    _, m, o = E.INS[setter]
    mm, oo, _ = E.norm(m, o)
    ops = E.split_ops(oo)
    if mm in ("mov", "movabs") and len(ops) == 2 and ops[1] in E.FAM and ops[1] not in E.PARTIAL:
        return E.FAM[ops[1]]
    return None


def terminal(s, pos, fam):
    """族 fam の pos 直前の値を 1 段。AMBIG は主経路の setter をもう 1 段分類する。MEM なら基底レジスタの直前値を 1 段追加する。"""
    r = E.resolve(s, pos, fam)
    out = {"cls": r["cls"], "desc": E.desc(r), "base": None, "base_cls": None, "base_desc": None}
    if r["cls"] == "AMBIG":
        lw = E.last_writer(s, pos, fam)
        r = E.classify(s, lw[0], lw[1], fam, 0)
        out.update(cls=f"AMBIG 主経路={r['cls']}", desc=f"主経路 {E.desc(r)}")
    if r["cls"] == "MEM" and r.get("setter") is not None:
        base = B.mem_setter_base(r["setter"])
        if base is not None and base != "rbp":
            b = E.resolve(s, r["setter"], base)
            out.update(base=base, base_cls=b["cls"], base_desc=E.desc(b))
        elif base == "rbp":
            out.update(base="rbp", base_cls="FRAME", base_desc="スタックスロット (rbp+X)")
    return out


def main():
    ap = __import__("argparse").ArgumentParser(description="PY-368: COPY 7・AMBIG 8 の複製元の基底 (2 段目)")
    ap.parse_args()
    B.setup()

    sites = sorted(E.cg_sites.get(E.TARGET, []))
    expected = {tuple(int(x, 16) for x in p.split(":")) for p in E.EXPECTED.split()}
    got = {(c, E.func_of(c)) for c in sites}
    if len(sites) != 60 or got != expected:
        sys.exit(f"直接 call の集合が想定と違う: 件数 {len(sites)}")

    print("\t".join(["call_va", "class", "src_fam", "src_class", "src_value", "base_reg", "base_class", "base_value"]))
    cnt = collections.Counter()
    for c in sites:
        r = E.analyze(c)
        if r["cls"] not in ("COPY", "AMBIG"):
            continue
        fn = E.func_of(c)
        s, i = E.ADDR_IDX[fn], E.ADDR_IDX[c]
        lw = E.last_writer(s, i, "rdx")
        fam = src_of_setter(s, lw[0]) if lw is not None else None
        if fam is None:
            print("\t".join(E.clean(x) for x in [f"0x{c:x}", r["cls"], "-", "-", "setter が reg 複写でない", "-", "-", "-"]))
            cnt[(r["cls"], "NOT_COPY")] += 1
            continue
        t = terminal(s, lw[0], fam)
        cnt[(r["cls"], t["cls"], t["base_cls"] or "-")] += 1
        print("\t".join(E.clean(x) for x in [
            f"0x{c:x}", r["cls"], fam, t["cls"], t["desc"], t["base"] or "-", t["base_cls"] or "-", t["base_desc"] or "-",
        ]))

    print("summary: " + ", ".join(f"{'/'.join(map(str, k))}={v}" for k, v in sorted(cnt.items())), file=sys.stderr)
    print(f"rows={sum(cnt.values())}", file=sys.stderr)
    if sum(cnt.values()) != 15:
        sys.exit(f"COPY・AMBIG の件数が 15 と違う: {sum(cnt.values())}")


if __name__ == "__main__":
    main()
