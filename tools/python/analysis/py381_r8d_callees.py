#!/usr/bin/env python3
"""PY-381 (#4776): 0x4 判定の立ち/落ち側の呼出し先のうち、中身を読めたものを分類する (実機不要)。

  python3 analysis/py381_r8d_callees.py <PE.bin> <work/py53/fn.txt> <outdir>

前段: analysis/py4769_r8d_single.py (到達集合・呼出し先の VA)。
既知の呼出し先 (逆アセンブルで中身を読んだもの):
  0xf82850 : al を返す関数 (al = [rbp+0x2b])。本体の直接の書込みはスタック上の [rbp+0x2b]・[rbp+0x2c]・[rbp+0x2e] のみ。呼出し先 (0xf8d730・0xf8d580・0xf783c0) は未読。
  0xfdeef0 : or dword [0x16bae80], 0x200 (固定ビットを立てるだけ)。
  0xfdef00 : or dword [0x16bae80], 0x1000 (固定ビットを立てるだけ)。
それ以外の呼出し先は『未確認』として数える。
検算: 既知 3 件の本体を capstone と objdump (intel) で照合し、0x4 の各側の呼出し集合を
      capstone 探索と objdump 探索で照合する。
"""
import os
import re
import subprocess
import sys

import capstone
import pefile

from py4769_r8d_single import explore, side_entries, sites
from py257_r8d_bits import load_objdump
from py64_branch_regions import load

KNOWN = {
    0xF82850: "bool_ret",
    0xFDEEF0: "or [0x16bae80],0x200",
    0xFDEF00: "or [0x16bae80],0x1000",
}
BODY = [(0xF82850, 0x40), (0xFDEEF0, 0x0B), (0xFDEF00, 0x0B)]


def text_of(pe_path):
    pe = pefile.PE(pe_path, fast_load=True)
    text = next(s for s in pe.sections if s.Name.startswith(b".text"))
    return pe, text


def disasm_capstone(pe_path, start, n):
    pe, text = text_of(pe_path)
    va0 = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress
    code = open(pe_path, "rb").read()[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    return [(m, o) for _, m, o in ((i.address, i.mnemonic, i.op_str)
                                   for i in md.disasm(code[start - va0:start - va0 + n], start))]


def norm(mn, ops):
    ops = ops.split("#")[0].lower().replace("ptr", "").replace(" ", "")
    ops = re.sub(r"\b(0x[0-9a-f]+|[0-9]+)\b", lambda m: hex(int(m.group(0), 0)), ops)
    return mn.lower(), ops


def disasm_objdump(pe_path, start, n):
    pe, text = text_of(pe_path)
    shift = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress - text.PointerToRawData
    out = subprocess.run(
        ["objdump", "-D", "-b", "binary", "-m", "i386:x86-64", "-M", "intel",
         f"--start-address={start - shift:#x}", f"--stop-address={start - shift + n:#x}", pe_path],
        capture_output=True, text=True, check=True,
    ).stdout
    res = []
    for ln in out.splitlines():
        parts = ln.split("\t")
        if len(parts) < 3 or not parts[2].strip():
            continue
        mn, _, ops = parts[2].strip().partition(" ")
        ops = ops.strip()
        if (mn.startswith("j") or mn == "call") and re.fullmatch(r"(0x)?[0-9a-f]+", ops.split()[0]):
            ops = f"{int(ops.split()[0], 16) + shift:#x}"
        res.append((mn, ops))
    return res


def callee_vas(calls):
    out = []
    for c in calls:
        _, _, ops = c.partition(":")
        ops = ops.strip()
        if ops.startswith("0x"):
            out.append(int(ops.split()[0], 16))
    return out


def main():
    pe_path, fn_path, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
    ins, nxt = load(fn_path)
    ob_ins, ob_nxt = load_objdump(pe_path)
    mismatch = 0

    for va, n in BODY:
        cap = [norm(m, o) for m, o in disasm_capstone(pe_path, va, n)]
        ob = [norm(m, o) for m, o in disasm_objdump(pe_path, va, n)]
        k = min(len(cap), len(ob))
        if k == 0 or cap[:k] != ob[:k]:
            mismatch += 1
            print(f"MISMATCH body={va:#x}")

    ss = [s for s in sites(ins, nxt) if s[1] == 0x4]
    ob_ss = {s[0]: s for s in sites(ob_ins, ob_nxt) if s[1] == 0x4}
    rows = []
    for s in ss:
        o = ob_ss.get(s[0])
        if o is None:
            mismatch += 1
            print(f"MISMATCH site={s[0]:#x} objdump 側に判定が無い")
            continue
        for (lab, entry), (lab2, entry2) in zip(side_entries(nxt, s), side_entries(ob_nxt, o)):
            r = explore(ins, nxt, entry)
            r2 = explore(ob_ins, ob_nxt, entry2)
            if (lab != lab2 or entry != entry2 or r["reach"] != r2["reach"]
                    or callee_vas(r["calls"]) != callee_vas(r2["calls"])):
                mismatch += 1
                print(f"MISMATCH site={s[0]:#x} side={lab}")
            cv = callee_vas(r["calls"])
            known = sorted({t for t in cv if t in KNOWN})
            unknown = sorted({t for t in cv if t not in KNOWN})
            rows.append((s[0], s[2], lab, entry, r["tail"], known, unknown))

    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "r8d_mask4_callees.tsv"), "w") as f:
        f.write("site\tjcc_va\tside\tentry\ttail\tknown_targets\tunknown_targets\n")
        for site, jva, lab, entry, tail, known, unknown in rows:
            f.write("\t".join([
                f"{site:#x}", f"{jva:#x}", lab, f"{entry:#x}", str(tail),
                ";".join(f"{t:#x}" for t in known) or "-",
                ";".join(f"{t:#x}" for t in unknown) or "-",
            ]) + "\n")

    print(f"mask=0x4 sides={len(rows)} mismatch={mismatch}")
    for lab in ("立ち", "落ち"):
        rs = [r for r in rows if r[2] == lab]
        print(f"side={lab} sides={len(rs)} "
              f"or0x1000={sum(0xFDEF00 in r[5] for r in rs)} "
              f"or0x200={sum(0xFDEEF0 in r[5] for r in rs)} "
              f"bool0xf82850={sum(0xF82850 in r[5] for r in rs)} "
              f"sides_with_unknown_calls={sum(bool(r[6]) for r in rs)}")
    return 0 if mismatch == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
