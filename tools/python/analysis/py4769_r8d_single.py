#!/usr/bin/env python3
"""PY-257 の子 (#4769): 単独ビット判定の立ち側・落ち側について、jcc の分岐先を含む全経路の作用を集計する (実機不要)。

  python3 analysis/py4769_r8d_single.py <PE.bin> <work/py53/fn.txt> <outdir>

py257_r8d_bits.py は条件 jcc の分岐先を辿らない。本スクリプトは各側の入口から、fall-through・jmp・jcc の
両方の辺を辿る (有界: 共通後半 0x104caae (tail)・早期 exit 0x104cc72 (exit)・ret で止める)。
集計 (到達した全命令について):
  writes5b8 : [rbp+0x5b8] への書込み命令の VA
  slots     : 書込み先のスロット (メモリ先頭オペランドの式) の種類数
  calls     : call 命令の VA と呼出し先
  exit      : 0x104cc72 に到達するか
  tail      : 0x104caae に到達するか
  oob       : 関数外・不明命令への到達数
検算: 同じ探索を objdump (intel) の逆アセンブルで行い、側ごとの (到達命令数・書込み・呼出し・exit/tail/oob) を照合する。
"""
import os
import sys

from py257_r8d_bits import SLOT, load_objdump, mem_dst, sites, target
from py64_branch_regions import EXIT, TAIL, load

SINGLE = {0x4, 0x10, 0x14, 0x10000, 0x8000, 0x1000, 0x2000, 0x4000, 0x200}
HEAD = ("site", "mask", "jcc_va", "side", "entry", "reach", "exit", "tail", "oob",
        "writes5b8", "slots", "calls")


def explore(ins, nxt, entry):
    seen, stack = set(), [entry]
    writes5b8, slots, calls = [], set(), []
    exit_hit = tail_hit = False
    oob = 0
    while stack:
        a = stack.pop()
        if a == TAIL:
            tail_hit = True
            continue
        if a == EXIT:
            exit_hit = True
            continue
        if a is None or a not in ins:
            oob += 1
            continue
        if a in seen:
            continue
        seen.add(a)
        mn, ops = ins[a]
        slot = mem_dst(mn, ops)
        if slot:
            slots.add(slot)
            if slot == SLOT:
                writes5b8.append(a)
        if mn == "call":
            calls.append(f"{a:#x}:{ops}")
        if mn == "ret":
            continue
        if mn == "jmp":
            stack.append(target(ops))
        elif mn.startswith("j"):
            stack.append(target(ops))
            stack.append(nxt[a])
        else:
            stack.append(nxt[a])
    return {
        "reach": len(seen), "exit": exit_hit, "tail": tail_hit, "oob": oob,
        "writes5b8": writes5b8, "slots": slots, "calls": calls,
    }


def side_entries(nxt, site):
    tva, mask, jva, jmn, jops = site
    fall = nxt[jva]
    if jmn in ("je", "jz"):
        return [("落ち", target(jops)), ("立ち", fall)]
    if jmn in ("jne", "jnz"):
        return [("立ち", target(jops)), ("落ち", fall)]
    return []


def summary(ins, nxt, site):
    out = []
    for lab, entry in side_entries(nxt, site):
        r = explore(ins, nxt, entry)
        out.append((lab, entry, r))
    return out


def fingerprint(r):
    return (r["reach"], r["exit"], r["tail"], r["oob"],
            tuple(f"{a:#x}" for a in r["writes5b8"]), len(r["slots"]), len(r["calls"]))


def main():
    pe_path, fn_path, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
    ins, nxt = load(fn_path)
    ob_ins, ob_nxt = load_objdump(pe_path)
    ss = [s for s in sites(ins, nxt) if s[1] in SINGLE]
    ob_ss = {s[0]: s for s in sites(ob_ins, ob_nxt) if s[1] in SINGLE}
    mismatch = 0
    rows = []
    for s in ss:
        cap = summary(ins, nxt, s)
        o = ob_ss.get(s[0])
        ob = summary(ob_ins, ob_nxt, o) if o else []
        if o is None or len(ob) != len(cap):
            mismatch += 1
            print(f"MISMATCH site={s[0]:#x} objdump の判定が無い")
        for (lab, entry, r), (lab2, entry2, r2) in zip(cap, ob):
            if lab != lab2 or entry != entry2 or fingerprint(r) != fingerprint(r2):
                mismatch += 1
                print(f"MISMATCH site={s[0]:#x} side={lab}")
        for lab, entry, r in cap:
            rows.append((f"{s[0]:#x}", f"{s[1]:#x}", f"{s[2]:#x}", lab, f"{entry:#x}", r))

    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "r8d_single.tsv"), "w") as f:
        f.write("\t".join(HEAD) + "\n")
        for site, mask, jva, lab, entry, r in rows:
            f.write("\t".join([
                site, mask, jva, lab, entry, str(r["reach"]), str(r["exit"]), str(r["tail"]), str(r["oob"]),
                ";".join(f"{a:#x}" for a in r["writes5b8"]) or "-", str(len(r["slots"])),
                ";".join(r["calls"]) or "-",
            ]) + "\n")

    print(f"sites={len(ss)} sides={len(rows)} mismatch={mismatch}")
    for mask in sorted({r[1] for r in rows}):
        rs = [r for r in rows if r[1] == mask]
        print(f"mask={mask} sides={len(rs)} exit_sides={sum(r[5]['exit'] for r in rs)} "
              f"tail_sides={sum(r[5]['tail'] for r in rs)} "
              f"reach_min={min(r[5]['reach'] for r in rs)} reach_max={max(r[5]['reach'] for r in rs)} "
              f"w5b8_sides={sum(bool(r[5]['writes5b8']) for r in rs)} "
              f"calls_sides={sum(bool(r[5]['calls']) for r in rs)}")
    return 0 if mismatch == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
