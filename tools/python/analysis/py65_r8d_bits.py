#!/usr/bin/env python3
"""PY-65 (#2034 の子・PY-257 #3816): 0x1046a30 の r8d 判定の立ち側・落ち側の作用を集計する (実機不要)。

  python3 analysis/py65_r8d_bits.py <PE.bin> <work/py53/fn.txt> <outdir>

判定箇所 = `mov eax, [rbp+0x5c0]` の直後の `test eax, M`。直後の jcc で分岐先を決める。
  je  : M のビットが全部 0 (落ち側) が分岐先。fall-through が立ち側。
  jne : M のどれかが 1 (立ち側) が分岐先。fall-through が落ち側。
各側の入口から fall-through だけで直線に辿り、経路上の作用を記録する。
  writes : 先頭オペランドがメモリの命令 (経路上・無条件)
  calls  : call (直接・間接)
  edges  : 経路上の jcc/jmp の分岐先 (early_exit = 0x104cc72 への辺)
  end    : jmp / ret / 共通後半 0x104caae (tail) / 0x104cc72 (exit, fall-through) / 関数外
同じ計算を objdump (intel) の逆アセンブルで独立に行い、判定箇所と経路の記録を照合する (mismatch 0 で exit 0)。
出力: <outdir>/r8d_sites.tsv (判定箇所ごとに両側の行)・<outdir>/r8d_scope.md (対象 13 マスクの要約表)。
共通後半 0x104caae 以降で [rbp+0x5b8] を読む命令も stdout に出す (tail_reads_5b8)。
"""
import os
import re
import subprocess
import sys

import pefile

from py64_branch_regions import EXIT, TAIL, load, region

FN_START = 0x1046A30
FN_END = 0x104CCCB
SCOPE = {0x4, 0x10, 0x14, 0x10000, 0x8000, 0x8A1, 0x240, 0x200, 0x1000, 0x2000, 0x2800, 0x4000, 0x3C0}
NO_WRITE = {"cmp", "test", "push", "call", "jmp", "lea", "ucomisd", "comisd", "ucomiss", "comiss"}


def load_objdump(pe_path):
    pe = pefile.PE(pe_path, fast_load=True)
    text = next(s for s in pe.sections if s.Name.startswith(b".text"))
    shift = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress - text.PointerToRawData
    out = subprocess.run(
        ["objdump", "-D", "-b", "binary", "-m", "i386:x86-64", "-M", "intel",
         f"--start-address={FN_START - shift:#x}", f"--stop-address={FN_END - shift + 1:#x}", pe_path],
        capture_output=True, text=True, check=True,
    ).stdout
    ins, order = {}, []
    for ln in out.splitlines():
        parts = ln.split("\t")
        if len(parts) < 3 or not parts[2].strip():
            continue
        va = int(parts[0].strip().rstrip(":"), 16) + shift
        if va >= FN_END:
            continue
        mn, _, ops = parts[2].strip().partition(" ")
        ops = ops.strip()
        if (mn.startswith("j") or mn == "call") and re.fullmatch(r"(0x)?[0-9a-f]+", ops.split()[0]):
            ops = f"{int(ops.split()[0], 16) + shift:#x}"
        ins[va] = (mn, ops)
        order.append(va)
    nxt = {a: order[i + 1] if i + 1 < len(order) else None for i, a in enumerate(order)}
    return ins, nxt


def mem_dst(mn, ops):
    if mn in NO_WRITE or not ops:
        return None
    first = ops.split(",")[0]
    m = re.search(r"\[(.*?)\]", first)
    if not m:
        return None
    return re.sub(r"(?<!\w)(\d+)(?!\w)", lambda d: f"{int(d.group(1)):#x}", m.group(1).replace(" ", ""))


def target(ops):
    return int(ops.split()[0], 16)


def norm(ops):
    return ops.replace(" ", "").lower()


def call_text(ops):
    tok = ops.split()[0]
    if re.fullmatch(r"(0x)?[0-9a-f]+", tok):
        return f"{int(tok, 16):#x}"
    return norm(ops)


def chain(ins, nxt, start):
    seq, writes, calls, edges = [], [], [], []
    end = ("oob", None)
    a = start
    while True:
        if a is None or a not in ins:
            end = ("oob", a)
            break
        if a == TAIL:
            end = ("tail", a)
            break
        if a == EXIT:
            end = ("exit", a)
            break
        if a in seq:
            end = ("loop", a)
            break
        mn, ops = ins[a]
        seq.append(a)
        slot = mem_dst(mn, ops)
        if slot:
            writes.append(f"{a:#x}:{slot}")
        if mn == "call":
            calls.append(f"{a:#x}:{call_text(ops)}")
        if mn == "ret":
            end = ("ret", a)
            break
        if mn == "jmp":
            end = ("jmp", target(ops))
            edges.append((a, target(ops)))
            break
        if mn.startswith("j"):
            edges.append((a, target(ops)))
        a = nxt[a]
    early = [a for a, t in edges if t == EXIT]
    return {
        "n": len(seq),
        "end": end,
        "writes": writes,
        "calls": calls,
        "edges": edges,
        "early": early,
    }


def sites(ins, nxt):
    order = sorted(ins)
    out = []
    for i, a in enumerate(order[:-2]):
        mn, ops = ins[a]
        if mn != "mov" or norm(ops) != "eax,dwordptr[rbp+0x5c0]":
            continue
        t_mn, t_ops = ins[order[i + 1]]
        if t_mn != "test" or not norm(t_ops).startswith("eax,"):
            continue
        j_a = order[i + 2]
        j_mn, j_ops = ins[j_a]
        mask = int(norm(t_ops).split(",")[1], 0)
        out.append((order[i + 1], mask, j_a, j_mn, j_ops))
    return out


def side_rows(ins, nxt, site):
    tva, mask, jva, jmn, jops = site
    fall = nxt[jva]
    if jmn in ("je", "jz"):
        sides = [("落ち", target(jops)), ("立ち", fall)]
    elif jmn in ("jne", "jnz"):
        sides = [("立ち", target(jops)), ("落ち", fall)]
    else:
        return [("?", jmn, None, None)]
    return [(lab, jmn, entry, chain(ins, nxt, entry)) for lab, entry in sides]


def fmt_end(end):
    kind, t = end
    return kind if t is None else f"{kind}:{t:#x}"


def row(site, side):
    tva, mask, jva, jmn, jops = site
    lab, jmn_, entry, c = side
    if c is None:
        return (f"{tva:#x}", f"{mask:#x}", f"{jva:#x}", jmn_, lab, "-", "0", "", "", "", "", "")
    return (
        f"{tva:#x}", f"{mask:#x}", f"{jva:#x}", jmn_, lab, f"{entry:#x}", str(c["n"]),
        fmt_end(c["end"]), ";".join(c["writes"]), ";".join(c["calls"]),
        ";".join(f"{a:#x}->{t:#x}" for a, t in c["edges"]), str(len(c["early"])),
    )


def rows_for(ins, nxt):
    out = []
    for s in sites(ins, nxt):
        for side in side_rows(ins, nxt, s):
            out.append((s, side))
    return out


def main():
    pe_path, fn_path, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
    ins, nxt = load(fn_path)
    cap = rows_for(ins, nxt)
    ob_ins, ob_nxt = load_objdump(pe_path)
    ob = rows_for(ob_ins, ob_nxt)

    cap_rows = [row(s, sd) for s, sd in cap]
    ob_rows = [row(s, sd) for s, sd in ob]
    mismatch = 0
    if len(cap_rows) != len(ob_rows):
        mismatch += abs(len(cap_rows) - len(ob_rows))
    head = ("site", "mask", "jcc_va", "jcc", "side", "entry", "n_instr", "end",
            "writes", "calls", "edges", "early_exit")
    for x, y in zip(cap_rows, ob_rows):
        if x != y:
            mismatch += 1
            cols = [head[i] for i in range(len(x)) if x[i] != y[i]]
            if mismatch <= 5:
                print(f"MISMATCH site={x[0]} side={x[4]} cols={cols}")

    os.makedirs(outdir, exist_ok=True)
    head = ("site", "mask", "jcc_va", "jcc", "side", "entry", "n_instr", "end",
            "writes", "calls", "edges", "early_exit")
    with open(os.path.join(outdir, "r8d_sites.tsv"), "w") as f:
        f.write("\t".join(head) + "\n")
        for r in cap_rows:
            f.write("\t".join(r) + "\n")

    side_of = {(r[0], r[4]): r for r in cap_rows}
    with open(os.path.join(outdir, "r8d_scope.md"), "w") as f:
        f.write("| 判定 | mask | jcc | 立ち: 入口 / 命令 / 終端 / 書込み ([rbp+0x5b8] の VA) / 呼出し | 落ち: 同じ |\n")
        f.write("|---|---|---|---|---|\n")
        for site in dict.fromkeys(r[0] for r in cap_rows if int(r[1], 16) in SCOPE):
            cells = []
            for side in ("立ち", "落ち"):
                r = side_of[(site, side)]
                w5 = [w.split(":")[0] for w in r[8].split(";") if w.endswith("rbp+0x5b8")]
                calls = len([c for c in r[9].split(";") if c])
                writes = len([w for w in r[8].split(";") if w])
                cells.append(f"{r[5]} / {r[6]} / {r[7]} / {writes} ({','.join(w5) or '-'}) / {calls}")
            f.write(f"| {site} | {r[1]} | {r[3]} | {cells[0]} | {cells[1]} |\n")
    tail = [a for a in region(ins, nxt, TAIL) if "[rbp + 0x5b8]" in ins[a][1] and not ins[a][1].startswith("dword ptr [rbp + 0x5b8]")]
    print("tail_reads_5b8=" + ",".join(f"{a:#x}" for a in tail))

    n_sites = len({r[0] for r in cap_rows})
    print(f"sites={n_sites} rows={len(cap_rows)} objdump_rows={len(ob_rows)} mismatch={mismatch}")
    return 0 if mismatch == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
