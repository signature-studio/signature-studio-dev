#!/usr/bin/env python3
"""PY-65 (#2034 の子・PY-257 #3816): 0x1046a30 の r8d 判定の立ち側・落ち側の作用を集計する (実機不要)。

  python3 analysis/py65_r8d_bits.py <PE.bin> <work/py53/fn.txt> <outdir>

判定箇所 = `mov eax, [rbp+0x5c0]` の直後の `test eax, M`。直後の jcc で分岐先を決める。
  je  : M のビットが全部 0 (落ち側) が分岐先。fall-through が立ち側。
  jne : M のどれかが 1 (立ち側) が分岐先。fall-through が落ち側。
各側の入口から経路を辿る (chain)。経路の規則:
  - fall-through は辿る。無条件 jmp は分岐先へ辿る。
  - 条件 jcc は分岐先を辿らない (fall-through だけを辿る)。分岐先は edges に、未追跡の本数は open_jcc に記録する。
  - 止める所: 共通後半 0x104caae (tail)・早期 exit 0x104cc72 (exit)・ret・関数外・経路の再訪 (loop)。
記録 (経路上):
  writes  : 先頭オペランドがメモリの命令
  calls   : call (直接・間接)。呼出し先の中の書込みは見ない
  edges   : 経路上の jcc/jmp の分岐先 (jmp は追跡済み・jcc は未追跡)
  early   : edges のうち分岐先が 0x104cc72 の本数
  end     : tail / exit / ret / oob / loop。end_src は終端へ入った命令の VA
  tail_src: end が tail の側について、入口までの経路で最後に [rbp+0x5b8] へ書かれた命令 (VA と式)。無ければ「入口前の値」
同じ計算を objdump (intel) の逆アセンブルで独立に行い、判定箇所と経路の記録を照合する (mismatch 0 で exit 0)。
出力: <outdir>/r8d_sites.tsv (判定箇所ごとに両側の行)・r8d_scope.md (対象 13 マスクの要約表)・
r8d_tail_src.md (end が tail の側の読み値の決まり)。共通後半 0x104caae 以降で [rbp+0x5b8] を読む命令は stdout に出す (tail_reads_5b8)。
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
MOV_LIKE = {"mov", "movzx", "movsx", "movsxd", "movss", "movsd", "movaps", "movups", "movd", "movq"}
SLOT = "rbp+0x5b8"
HEAD = ("site", "mask", "jcc_va", "jcc", "side", "entry", "n_instr", "end", "end_src",
        "writes", "calls", "edges", "early_exit", "open_jcc", "tail_src")


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


def reads_slot(mn, ops):
    o = norm(ops)
    if mn == "lea" or f"[{SLOT}]" not in o:
        return False
    if f"[{SLOT}]" not in o.split(",")[0]:
        return True
    return not (mn in MOV_LIKE or mn.startswith("set"))


def target(ops):
    return int(ops.split()[0], 16)


def norm(ops):
    return ops.replace(" ", "").lower()


def canon(ops):
    return re.sub(r"\s*([+,])\s*", r"\1", ops).lower()


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
            edges.append((a, target(ops)))
            a = target(ops)
            continue
        if mn.startswith("j"):
            edges.append((a, target(ops)))
        a = nxt[a]
    w5 = [w for w in writes if w.endswith(f":{SLOT}")]
    if end[0] != "tail":
        tail_src = "-"
    elif w5:
        va = int(w5[-1].split(":")[0], 16)
        tail_src = f"{va:#x} {ins[va][0]} {canon(ins[va][1])}"
    else:
        tail_src = "入口前の値"
    return {
        "n": len(seq),
        "end": end,
        "src": seq[-1] if seq else None,
        "writes": writes,
        "calls": calls,
        "edges": edges,
        "early": [x for x, t in edges if t == EXIT],
        "open_jcc": [x for x, _ in edges if ins[x][0] != "jmp"],
        "tail_src": tail_src,
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
        return (f"{tva:#x}", f"{mask:#x}", f"{jva:#x}", jmn_, lab, "-", "0", "-", "-", "", "", "", "0", "", "-")
    return (
        f"{tva:#x}", f"{mask:#x}", f"{jva:#x}", jmn_, lab, f"{entry:#x}", str(c["n"]),
        fmt_end(c["end"]), f"{c['src']:#x}" if c["src"] is not None else "-",
        ";".join(c["writes"]), ";".join(c["calls"]),
        ";".join(f"{a:#x}->{t:#x}" for a, t in c["edges"]), str(len(c["early"])),
        ";".join(f"{a:#x}" for a in c["open_jcc"]) or "-", c["tail_src"],
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
    for x, y in zip(cap_rows, ob_rows):
        if x != y:
            mismatch += 1
            cols = [HEAD[i] for i in range(len(x)) if x[i] != y[i]]
            if mismatch <= 5:
                print(f"MISMATCH site={x[0]} side={x[4]} cols={cols}")

    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "r8d_sites.tsv"), "w") as f:
        f.write("\t".join(HEAD) + "\n")
        for r in cap_rows:
            f.write("\t".join(r) + "\n")

    side_of = {(r[0], r[4]): r for r in cap_rows}
    with open(os.path.join(outdir, "r8d_scope.md"), "w") as f:
        f.write("| 判定 | mask | jcc | 立ち: 入口 / 命令 / 終端 (終端へ入った命令) / 書込み ([rbp+0x5b8] の VA) / 呼出し / 未追跡 jcc | 落ち: 同じ |\n")
        f.write("|---|---|---|---|---|\n")
        for site in dict.fromkeys(r[0] for r in cap_rows if int(r[1], 16) in SCOPE):
            cells = []
            for side in ("立ち", "落ち"):
                r = side_of[(site, side)]
                w5 = [w.split(":")[0] for w in r[9].split(";") if w.endswith(f":{SLOT}")]
                calls = len([c for c in r[10].split(";") if c])
                writes = len([w for w in r[9].split(";") if w])
                opn = len([j for j in r[13].split(";") if j and j != "-"])
                cells.append(f"{r[5]} / {r[6]} / {r[7]} ({r[8]}) / {writes} ({','.join(w5) or '-'}) / {calls} / {opn}")
            f.write(f"| {site} | {r[1]} | {r[3]} | {cells[0]} | {cells[1]} |\n")
    with open(os.path.join(outdir, "r8d_tail_src.md"), "w") as f:
        f.write("| 判定 | mask | 側 | 入口 | 経路の命令数 | 読み値の決まり (経路上で最後に [rbp+0x5b8] へ書かれた命令・無ければ入口前の値) |\n")
        f.write("|---|---|---|---|---|---|\n")
        for r in cap_rows:
            if r[7].startswith("tail:"):
                f.write(f"| {r[0]} | {r[1]} | {r[4]} | {r[5]} | {r[6]} | {r[14]} |\n")

    tail = [a for a in region(ins, nxt, TAIL) if reads_slot(*ins[a])]
    print("tail_reads_5b8=" + ",".join(f"{a:#x}" for a in tail))
    sides = [sd[3] for _, sd in cap if sd[3] is not None]
    print(f"sides={len(sides)} end_exit={sum(c['end'][0] == 'exit' for c in sides)} "
          f"end_tail={sum(c['end'][0] == 'tail' for c in sides)} "
          f"sides_with_exit_jcc={sum(any(ins[x][0] != 'jmp' and t == EXIT for x, t in c['edges']) for c in sides)} "
          f"sides_with_open_jcc={sum(bool(c['open_jcc']) for c in sides)} "
          f"sides_with_5b8_write={sum(any(w.endswith(':' + SLOT) for w in c['writes']) for c in sides)}")

    n_sites = len({r[0] for r in cap_rows})
    print(f"sites={n_sites} rows={len(cap_rows)} objdump_rows={len(ob_rows)} mismatch={mismatch}")
    return 0 if mismatch == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
