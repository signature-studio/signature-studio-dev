#!/usr/bin/env python3
"""PY-65 (#2034): 0x1046a30 の r8d 判定 (`[rbp+0x5c0]` を読んで test/and する箇所) の各ビットの作用を分類する。

  python3 analysis/py65_r8d_bits.py <PE.bin> <work/py53/fn.txt> <outdir> [--negctl]

出力:
  <outdir>/r8d_sites.tsv  test/and の判定 1 件 1 行 (VA・マスク・jcc・ビット立ち/落ちの行き先・到達する ecx 分岐)
  <outdir>/r8d_others.tsv test/and 以外の [rbp+0x5c0] 参照 12 件 1 行 (mov+and+cmp の判定・格納・値の受け渡し)
  標準出力                 ビット別の件数と照合結果

照合 (別算法): objdump -M intel で同じ判定箇所を取り直し、VA・マスク・次の jcc/setcc と分岐先が
capstone 側 (fn.txt) と一致するかを見る。--negctl は capstone 側の 1 件のマスクを壊し、不一致が出ることを確かめる。
母集団の完全性: [rbp+0x5c0] の参照総数を fn のバイト列の走査 (c0 05 00 00) と capstone の件数で数えて一致を見る。
行き先は CFG 上の path-insensitive な到達で、ビットの作用の確定は REPORT_PY41.md の表と突合して判断する。
"""
import os
import re
import subprocess
import sys
from collections import Counter

import pefile

FN_START = 0x1046A30
FN_END = 0x104CCCB
COMMON_TAIL = 0x104CAAE
ENTRIES = {
    0x104C4AF: "E:ecx=0x40000001",
    0x1047497: "E:ecx∈[0,0x10000000)",
    0x104AA87: "E:ecx∈[0x70000000,0xf0000000)",
    0x104C2A6: "E:ecx=0x40000000",
    0x104C64F: "E:ecx=0x40000002",
    0x104C919: "E:ecx=0x40000005",
}
RE_JCC = re.compile(r"^(j\w+|set\w+)$")


def load_fn(path):
    ins = {}
    order = []
    for ln in open(path):
        m = re.match(r"(0x[0-9a-f]+): (\S+)\s*(.*)$", ln.rstrip("\n"))
        if m:
            va = int(m.group(1), 16)
            ins[va] = (m.group(2), m.group(3).strip())
            order.append(va)
    return ins, order


def cap_sites(ins, order):
    sites = []
    for i, va in enumerate(order):
        mn, op = ins[va]
        if mn != "mov" or not op.startswith("eax, dword ptr [rbp + 0x5c0]"):
            continue
        if i + 2 >= len(order):
            continue
        t_va = order[i + 1]
        t_mn, t_op = ins[t_va]
        if t_mn == "test" and t_op.startswith("eax, "):
            mask = int(t_op.split(", ")[1], 16)
            n_va = order[i + 2]
            n_mn, n_op = ins[n_va]
            tgt = int(n_op, 16) if n_mn.startswith("j") else None
            sites.append((t_va, "test", mask, n_mn if RE_JCC.match(n_mn) or n_mn.startswith("j") else "-", tgt, n_va))
    for va in order:
        mn, op = ins[va]
        if mn == "and" and op.startswith("dword ptr [rbp + 0x5c0], "):
            sites.append((va, "and", int(op.split(", ")[1], 16), "-", None, None))
    return sorted(sites)


def obj_sites(pe_path, shift):
    start = FN_START - shift
    stop = FN_END - shift + 1
    out = subprocess.run(
        ["objdump", "-D", "-b", "binary", "-m", "i386:x86-64", "-M", "intel",
         f"--start-address={start:#x}", f"--stop-address={stop:#x}", pe_path],
        capture_output=True, text=True, check=True,
    ).stdout
    rows = []
    for ln in out.splitlines():
        parts = ln.split("\t")
        if len(parts) < 3 or not parts[2].strip():
            continue
        va = int(parts[0].strip().rstrip(":"), 16) + shift
        body = parts[2].strip().split(None, 1)
        rows.append((va, body[0], body[1] if len(body) > 1 else ""))
    sites = []
    for i, (va, mn, op) in enumerate(rows):
        if mn == "mov" and op == "eax,DWORD PTR [rbp+0x5c0]" and i + 2 < len(rows):
            t_va, t_mn, t_op = rows[i + 1]
            if t_mn == "test" and t_op.startswith("eax,"):
                mask = int(t_op.split(",")[1], 16)
                n_va, n_mn, n_op = rows[i + 2]
                tgt = None
                if n_mn.startswith("j"):
                    tgt = int(n_op.split(",")[0], 16) + shift
                sites.append((t_va, "test", mask, n_mn if n_mn.startswith(("j", "set")) else "-", tgt, n_va))
        if mn == "and" and op.startswith("DWORD PTR [rbp+0x5c0],"):
            sites.append((va, "and", int(op.split(",")[1], 16), "-", None, None))
    return sorted(sites)


def reach_from(ins, start, stop_at):
    seen = set()
    todo = [start]
    while todo:
        va = todo.pop()
        if va in seen or va == stop_at or va not in ins:
            continue
        seen.add(va)
        mn, op = ins[va]
        if mn == "ret":
            continue
        if mn.startswith("j"):
            todo.append(int(op, 16))
            if mn == "jmp":
                continue
        todo.append(_NEXT.get(va, va + 1))
    return seen


_NEXT = {}


def owners(ins, order):
    for a, b in zip(order, order[1:]):
        _NEXT[a] = b
    reach = {}
    for e, lab in ENTRIES.items():
        reach[e] = reach_from(ins, e, COMMON_TAIL)
    return reach


def polarity(mn, mask, tgt, nxt):
    if mn == "-":
        return "-"
    if mn in ("je", "jz"):
        return f"立ち→{nxt:#x} / 落ち→{tgt:#x}"
    if mn in ("jne", "jnz"):
        return f"立ち→{tgt:#x} / 落ち→{nxt:#x}"
    if mn == "setne":
        return "立ち→真(1) / 落ち→偽(0)"
    return f"{mn}"


def byte_refs(pe_path, shift):
    with open(pe_path, "rb") as f:
        data = f.read()
    return data[FN_START - shift:FN_END + 1 - shift].count(b"\xc0\x05\x00\x00")


def ref_kinds(ins, order):
    pos = {va: k for k, va in enumerate(order)}
    out = []
    for va in order:
        mn, op = ins[va]
        if "[rbp + 0x5c0]" not in op:
            continue
        k = pos[va]
        nxt = [(order[j],) + ins[order[j]] for j in range(k + 1, min(k + 4, len(order)))]
        nxt += [(0, "", "")] * (3 - len(nxt))
        (_, m1, o1), (_, m2, o2), (v3, m3, o3) = nxt[0], nxt[1], nxt[2]
        load = op.startswith("eax, dword ptr [rbp + 0x5c0]")
        if mn == "and" and op.startswith("dword ptr [rbp + 0x5c0]"):
            kind = "and"
        elif mn == "mov" and op.startswith("dword ptr [rbp + 0x5c0]"):
            kind = "store"
        elif mn == "mov" and load and m1 == "test" and o1.startswith("eax, "):
            kind = "test"
        elif mn == "mov" and load and m1 == "and" and m2 == "cmp" and o2 == o1 and m3.startswith("j"):
            kind = "andcmp"
        else:
            kind = "other"
        if kind == "andcmp":
            fall, tgt = order[pos[v3] + 1], int(o3, 16)
            mask = int(o1.split(", ")[1], 16)
            pol = f"全立ち→{fall:#x} / 一部落ち→{tgt:#x}" if m3 == "jne" else f"全立ち→{tgt:#x} / 一部落ち→{fall:#x}"
            out.append((va, kind, mask, m3, tgt, pol, f"{m1} {o1} ; {m2} {o2}"))
        else:
            detail = " ; ".join(f"{m} {o}" for _, m, o in nxt[:2] if m)
            out.append((va, kind, None, "-", None, "-", f"{mn} {op} ; {detail}"))
    return out


def main():
    pe_path, fn_path, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
    negctl = "--negctl" in sys.argv
    pe = pefile.PE(pe_path, fast_load=True)
    text = next(s for s in pe.sections if s.Name.startswith(b".text"))
    shift = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress - text.PointerToRawData

    ins, order = load_fn(fn_path)
    cap = cap_sites(ins, order)
    if negctl:
        va0, kind, mask, mn, tgt, nva = cap[0]
        cap[0] = (va0, kind, mask ^ 0x40, mn, tgt, nva)
    ob = obj_sites(pe_path, shift)

    cap_set = [(a, b, c, d, e) for a, b, c, d, e, _ in cap]
    ob_set = [(a, b, c, d, e) for a, b, c, d, e, _ in ob]
    mism = sum(1 for x, y in zip(cap_set, ob_set) if x != y) + abs(len(cap_set) - len(ob_set))
    print(f"sites capstone={len(cap)} objdump={len(ob)} test={sum(1 for s in cap if s[1] == 'test')} and={sum(1 for s in cap if s[1] == 'and')}")
    print(f"objdump 照合: agree={len(cap_set) - mism} mismatch={mism}")
    refs = ref_kinds(ins, order)
    nb = byte_refs(pe_path, shift)
    print(f"[rbp+0x5c0] 参照: byte走査={nb} capstone={len(refs)} 内訳={dict(Counter(r[1] for r in refs))}")

    reach = owners(ins, order)
    rows = []
    for va, kind, mask, mn, tgt, nva in cap:
        own = [ENTRIES[e] for e in ENTRIES if va in reach[e]]
        if not own:
            own = ["前段(dispatch 前)" if va < 0x104742A else "共通後半(0x104caae 以降)" if va >= COMMON_TAIL else "未到達"]
        rows.append((va, kind, mask, mn, tgt, nva, polarity(mn, mask, tgt, nva), ";".join(own)))
    if negctl:
        print(f"negctl: 不一致 {mism} 件 (1 以上で検出)")
        return 0 if mism >= 1 else 1
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "r8d_sites.tsv"), "w") as f:
        f.write("VA\tkind\tmask\tjcc\ttarget\tpolarity\towners\n")
        for va, kind, mask, mn, tgt, nva, pol, own in rows:
            f.write(f"{va:#x}\t{kind}\t{mask:#x}\t{mn}\t{'' if tgt is None else hex(tgt)}\t{pol}\t{own}\n")
    print(f"tsv={os.path.join(outdir, 'r8d_sites.tsv')} rows={len(rows)}")
    others = [r for r in refs if r[1] not in ("test", "and")]
    with open(os.path.join(outdir, "r8d_others.tsv"), "w") as f:
        f.write("VA\tclass\tmask\tjcc\ttarget\tpolarity\tnext\n")
        for va, kind, mask, mn, tgt, pol, detail in others:
            f.write(f"{va:#x}\t{kind}\t{'-' if mask is None else hex(mask)}\t{mn}\t{'' if tgt is None else hex(tgt)}\t{pol}\t{detail}\n")
    print(f"others={os.path.join(outdir, 'r8d_others.tsv')} rows={len(others)}")
    return 0 if mism == 0 and nb == len(refs) else 1


if __name__ == "__main__":
    sys.exit(main())
