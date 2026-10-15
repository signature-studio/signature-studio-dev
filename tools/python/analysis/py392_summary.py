#!/usr/bin/env python3
"""PY-392 (#4828): py392_ret584_suffcond.py の出力を付録 (表 + cube の TSV) に集計する。

  python3 analysis/py392_summary.py <work/py392/suffcond.tsv> <work/py341/ret584_dominators.tsv> <outdir>

出力: <outdir>/REPORT_APPENDIX_PY392.md (表)・<outdir>/REPORT_APPENDIX_PY392_cubes.tsv (cube の全リテラル)
"""
import os
import sys


def rows_of(path):
    with open(path) as f:
        next(f)
        for ln in f:
            yield ln.rstrip("\n").split("\t")


def main():
    suff, dom, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
    forced = {}
    for p in rows_of(dom):
        forced[int(p[0], 16)] = 0 if p[3].startswith("(") else p[3].count("; ") + 1
    os.makedirs(outdir, exist_ok=True)
    live = [p for p in rows_of(suff) if p[6] == "True"]
    md = [
        "# PY-392 (#4828): 0x104cc65 に届く 72 件の十分条件 (付録)",
        "",
        f"自動生成: `python3 analysis/py392_ret584_suffcond.py work/py53/fn.txt work/py392` → "
        f"`python3 analysis/py392_summary.py work/py392/suffcond.tsv work/py341/ret584_dominators.tsv tools/python` "
        f"(件数 {len(live)})。",
        "",
        "列: 書込み VA・書く値の式 (`py53` の命令)・必須分岐数 (`py341`)・代表 cube の分岐数・BDD の排他 cube 数 (変数順序依存)。",
        "",
        "| 書込み VA | 書く値の式 | 必須分岐 | 代表 cube の分岐数 | BDD の排他 cube 数 |",
        "|---|---|---:|---:|---:|",
    ]
    cubes = ["write_VA\tcube_lits\tcube (分岐 VA。立ちは無印・落ちは !)"]
    for p in live:
        w = int(p[0], 16)
        md.append(f"| {w:#x} | `{p[1]}` | {forced.get(w, 0)} | {p[7]} | {p[5]} |")
        cubes.append(f"{w:#x}\t{p[7]}\t{p[8]}")
    with open(os.path.join(outdir, "REPORT_APPENDIX_PY392.md"), "w") as f:
        f.write("\n".join(md) + "\n")
    with open(os.path.join(outdir, "REPORT_APPENDIX_PY392_cubes.tsv"), "w") as f:
        f.write("\n".join(cubes) + "\n")
    print(f"rows={len(live)}")


if __name__ == "__main__":
    main()
