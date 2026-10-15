#!/usr/bin/env python3
"""PY-368 (#4588 子 3/3): pe_py368_copy_ambig.py の終端 7 箇所を分類する。

- スタック slot [rbp+X] を基底・複製元とする行は、その slot への直前 store の格納値を 1 段分類する。
- AMBIG の合流行 (0x12c609e・0xfc820f) は、合流元の飛び元ごとの値を出す (resolve の注記)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py368_terminal.py

終了 0 = 完了。想定の 7 箇所と違えば終了 1。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pe_py203_edx_sites as E  # noqa: E402
import pe_py273_base as B  # noqa: E402
import pe_py368_copy_ambig as T  # noqa: E402

TERMINAL = {
    0x1021826: "COPY", 0x12ab8e8: "COPY",
    0x118a275: "AMBIG", 0x118a3f4: "AMBIG", 0x12e6abe: "AMBIG",
    0x12c609e: "AMBIG", 0xfc820f: "AMBIG",
}


def slot_chain(s, k, depth=0):
    """MEM setter k のアドレスを、[rbp+X] の slot の setter (index, mem) まで辿る。"""
    _, m, o = E.INS[k]
    mm, oo, _ = E.norm(m, o)
    ops = E.split_ops(oo)
    src = ops[1] if len(ops) == 2 else ""
    base = B.base_of(src) if "[" in src else None
    if base == "rbp" or depth > 2 or base is None:
        return k, E.norm_mem(src)
    b = E.resolve(s, k, base)
    if b.get("setter") is None or b["cls"] != "MEM":
        return k, E.norm_mem(src)
    return slot_chain(s, b["setter"], depth + 1)


def store_value(s, j):
    """直前 store (index j) の格納値。レジスタなら resolve で 1 段分類する。"""
    _, m, o = E.INS[j]
    mm, oo, _ = E.norm(m, o)
    ops = E.split_ops(oo)
    src = ops[1]
    if E.IMM_RE.match(src):
        return f"IMM {E.imm_text(src, ops[0])} @{E.va(j)}"
    if src in E.FAM and src not in E.PARTIAL:
        r = E.resolve(s, j, E.FAM[src])
        return f"{src} ← {E.desc(r)}" + (f" [notes: {'; '.join(r['notes'])}]" if r["notes"] else "")
    return f"{m} {o} @{E.va(j)}"


def main():
    B.setup()
    sites = sorted(E.cg_sites.get(E.TARGET, []))
    expected = {tuple(int(x, 16) for x in p.split(":")) for p in E.EXPECTED.split()}
    got = {(c, E.func_of(c)) for c in sites}
    if len(sites) != 60 or got != expected:
        sys.exit(f"直接 call の集合が想定と違う: 件数 {len(sites)}")

    print("\t".join(["call_va", "class", "chain", "slot", "slot_store", "store_value", "note"]))
    rows = 0
    for c in sorted(TERMINAL):
        if c not in sites:
            sys.exit(f"0x{c:x} が直接 call の集合にない")
        r = E.analyze(c)
        fn = E.func_of(c)
        s, i = E.ADDR_IDX[fn], E.ADDR_IDX[c]
        lw = E.last_writer(s, i, "rdx")
        fam = T.src_of_setter(s, lw[0]) if lw is not None else None
        if fam is None:
            sys.exit(f"0x{c:x} の setter が reg 複写でない")
        rows += 1
        if TERMINAL[c] == "AMBIG" and c in (0x12c609e, 0xfc820f):
            print("\t".join(E.clean(x) for x in [f"0x{c:x}", r["cls"], fam, "merge", "-", "-", r["note"]]))
            continue
        # 複製元の族 (fam) の setter を辿り、MEM なら slot まで遡る
        res = E.resolve(s, lw[0], fam)
        setter = res.get("setter")
        if res["cls"] == "AMBIG":
            lw2 = E.last_writer(s, lw[0], fam)
            setter = E.classify(s, lw2[0], lw2[1], fam, 0)["setter"]
        if setter is None or E.INS[setter][1] != "mov" and "[" not in E.INS[setter][2]:
            sys.exit(f"0x{c:x} の MEM setter が取れない")
        k, slot = slot_chain(s, setter)
        j = E.last_store(s, k, slot)
        sv = store_value(s, j) if j is not None else "直前 store 無し (窓内)"
        print("\t".join(E.clean(x) for x in [
            f"0x{c:x}", r["cls"], fam, slot, f"@{E.va(k)}", sv, r["note"]]))

    print(f"rows={rows}", file=sys.stderr)
    if rows != 7:
        sys.exit(f"終端の件数が 7 と違う: {rows}")


if __name__ == "__main__":
    main()
