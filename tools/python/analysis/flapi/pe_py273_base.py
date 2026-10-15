#!/usr/bin/env python3
"""PY-273 (#3927): 0x128f9e0 の直接 call 60 箇所の edx setter の基底 (MEM 38) の上流を 1 段追う。

pe_py203_edx_sites.py の resolve を使い、MEM setter の基底レジスタの、setter 直前の値を分類する。
COPY 7 は複製元の値 (既に PY-203 で確定) をそのまま載せ、AMBIG 8 は合流元の基底を分類する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py273_base.py

終了 0 = 完了。想定の 60 件と違えば終了 1。
"""
import argparse
import collections
import os
import re
import sys

import capstone
import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pe_callgraph as cg  # noqa: E402
import pe_py203_edx_sites as E  # noqa: E402


def setup():
    E.INS = cg.load()
    E.ADDR_IDX = {a: k for k, (a, _, _) in enumerate(E.INS)}
    E.FUNCS = cg.function_starts(E.INS)
    raw = open(cg.PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    text = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
    E.TEXT_VA = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress
    E.TEXT = raw[text.PointerToRawData:text.PointerToRawData + min(text.Misc_VirtualSize, text.SizeOfRawData)]
    E.CS = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    E.JTS, E.JT, E.NB_TGT = [], [], []
    for s, (a, m, o) in enumerate(E.INS):
        if m.startswith("j") and o.startswith("0x"):
            t = E.ADDR_IDX.get(int(o, 16))
            if t is None:
                E.NB_TGT.append(int(o, 16))
                continue
            E.JTS.append((t, s))
            E.JMP_TO[t].append(s)
    E.NB_TGT.sort()
    E.JTS.sort()
    E.JT = [t for t, _ in E.JTS]
    for a, m, o in E.INS:
        if m == "call" and o.startswith("0x"):
            E.cg_sites.setdefault(int(o, 16), []).append(a)


BASE_RE = re.compile(r"\[(\w+)")


def base_of(mem):
    m = BASE_RE.search(mem)
    return m.group(1) if m else None


def mem_setter_base(row):
    """MEM setter の命令から基底レジスタ族を得る。"""
    _, m, o = E.INS[row]
    mm, oo, _ = E.norm(m, o)
    ops = E.split_ops(oo)
    src = ops[1] if len(ops) == 2 else ""
    return base_of(src) if "[" in src else None


def main():
    ap = argparse.ArgumentParser(description="PY-273: 0x128f9e0 の edx setter の基底の上流 (1 段)")
    ap.parse_args()
    setup()

    sites = sorted(E.cg_sites.get(E.TARGET, []))
    expected = {tuple(int(x, 16) for x in p.split(":")) for p in E.EXPECTED.split()}
    got = {(c, E.func_of(c)) for c in sites}
    if len(sites) != 60 or got != expected:
        sys.exit(f"直接 call の集合が想定と違う: 件数 {len(sites)}")

    rows = []
    for c in sites:
        r = E.analyze(c)
        fn = E.func_of(c)
        s, i = E.ADDR_IDX[fn], E.ADDR_IDX[c]
        lw = E.last_writer(s, i, "rdx")
        setter = lw[0] if lw is not None else None
        base = mem_setter_base(setter) if setter is not None and r["cls"] == "MEM" else None
        up = None
        if base is not None:
            # 基底レジスタの、setter 直前の値。rbp は関数内のスロットなので、スロットの直前 store を見る
            if base == "rbp":
                up = ("FRAME", None, "スタックスロット (rbp+X)")
            else:
                bres = E.resolve(s, setter, base)
                up = (bres["cls"], bres.get("setter"), E.desc(bres))
        rows.append((c, r, base, up))

    cnt = collections.Counter()
    print("\t".join(["call_va", "class", "base_reg", "base_upstream_class", "base_upstream", "base_setter"]))
    for c, r, base, up in rows:
        if r["cls"] != "MEM":
            print("\t".join(E.clean(x) for x in [f"0x{c:x}", r["cls"], "-", "-", r["value"], "-"]))
            continue
        cls = up[0] if up else "UNKNOWN"
        cnt[(base, cls)] += 1
        print("\t".join(E.clean(x) for x in [
            f"0x{c:x}", "MEM", base, cls, up[2] if up else "-",
            f"0x{up[1]:x}" if up and up[1] is not None else "-",
        ]))

    print("summary: " + ", ".join(f"{b}/{k}={v}" for (b, k), v in sorted(cnt.items())), file=sys.stderr)
    print(f"rows={len(rows)} MEM={sum(1 for _, r, _, _ in rows if r['cls'] == 'MEM')}", file=sys.stderr)


if __name__ == "__main__":
    main()
