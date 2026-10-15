#!/usr/bin/env python3
"""PY-342 (#4575): r8d 判定の行き先 (r8d_sites.tsv) と戻り値分岐 (0x104cc65 に届く経路) の突合。

  python3 analysis/py342_r8d_ret_cross.py <work/py53/fn.txt> <work/py65/r8d_sites.tsv> <outdir> [--negctl]

定義:
  入る   : 判定命令 (test/and) の VA が、CFG 上で戻り値読出し 0x104cc65 に前向きに届く (後ろ向き閉包に入る)。
  入らない: 届かない。
  行き先 : test の jcc について、ビット立ち (eax & mask != 0) の行き先と、ビット落ちの行き先を
           fn.txt の命令から独立に決める (je/jz は落ちで飛ぶ, jne/jnz は立ちで飛ぶ)。
  突合   : TSV の polarity 列の「立ち→」の行き先と、上の独立計算の行き先が一致するか。
           不一致 1 件 = mismatch。
  戻り値側: 入る判定について、立ち・落ちのどちらの行き先が 0x104cc65 に届くか (both/bitset/bitclear/none)。
path-insensitive (経路条件は分けない)。--negctl は TSV の 1 件の立ち・落ちを入れ替え、不一致が出ることを確かめる。
"""
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from py65_ret584_reach import load, preds  # noqa: E402

RET = 0x104CC65
RE_TAKEN = re.compile(r"立ち→(0x[0-9a-f]+)")


def closure(p, start):
    seen = set()
    stack = [start]
    while stack:
        v = stack.pop()
        for q in p.get(v, []):
            if q not in seen:
                seen.add(q)
                stack.append(q)
    return seen


def main():
    fn_path, tsv_path, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
    negctl = "--negctl" in sys.argv
    ins, order = load(fn_path)
    idx = {va: i for i, va in enumerate(order)}
    p = preds(ins, order)
    reach_ret = closure(p, RET) | {RET}

    rows = list(csv.DictReader(open(tsv_path), delimiter="\t"))
    if negctl:
        for r in rows:
            m = RE_TAKEN.search(r["polarity"])
            if m and "/" in r["polarity"]:
                a, b = r["polarity"].split(" / ")
                r["polarity"] = b.replace("落ち", "立ち", 1) + " / " + a.replace("立ち", "落ち", 1)
                break

    out = []
    mism = 0
    cls_cnt = {}
    in_cnt = {True: 0, False: 0}
    for r in rows:
        va = int(r["VA"], 16)
        inside = va in reach_ret
        in_cnt[inside] += 1
        jcc = r["jcc"]
        cls = "-"
        derived = ""
        tsv_bit = ""
        if r["kind"] == "test" and jcc in ("je", "jz", "jne", "jnz"):
            nxt = order[idx[va] + 1] if va in idx and idx[va] + 1 < len(order) else None
            tgt = int(r["target"], 16)
            if jcc in ("je", "jz"):
                bit_dest, clr_dest = nxt, tgt
            else:
                bit_dest, clr_dest = tgt, nxt
            derived = f"{bit_dest:#x}"
            m = RE_TAKEN.search(r["polarity"])
            tsv_bit = m.group(1) if m else ""
            if tsv_bit != derived:
                mism += 1
            b_in = bit_dest in reach_ret
            c_in = clr_dest in reach_ret
            cls = ("both" if b_in and c_in else "bitset" if b_in
                   else "bitclear" if c_in else "none")
        elif r["kind"] == "test":
            cls = "no-jcc(setne)"
        else:
            cls = "and(書換え)"
        cls_cnt[(inside, cls)] = cls_cnt.get((inside, cls), 0) + 1
        out.append((r["VA"], r["kind"], r["mask"], jcc, "入る" if inside else "入らない", cls, derived, tsv_bit))

    if negctl:
        print(f"negctl: 不一致 {mism} 件 (1 以上で検出)")
        return 0 if mism >= 1 else 1

    print(f"判定 {len(rows)} 件: 入る={in_cnt[True]} 入らない={in_cnt[False]}")
    for (inside, cls), n in sorted(cls_cnt.items(), key=lambda kv: (not kv[0][0], kv[0][1])):
        print(f"  {'入る' if inside else '入らない'} / {cls}: {n}")
    print(f"突合 (TSV の立ち行き先 vs fn.txt 独立計算): mismatch={mism}")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "r8d_ret_cross.tsv"), "w") as f:
        f.write("VA\tkind\tmask\tjcc\tret\tbranch\tderived_bitset\ttsv_bitset\n")
        for row in out:
            f.write("\t".join(row) + "\n")
    print(f"tsv={os.path.join(outdir, 'r8d_ret_cross.tsv')} rows={len(out)}")
    return 0 if mism == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
