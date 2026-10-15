#!/usr/bin/env python3
"""FLEngine PE で、関数 0x415c30 の直接 call 元 (E8 rel32) ごとに、call 直後の rax の行き先を分類する (PY-396 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_ret_propagation.py <callee VA(16進, 既定 415c30)>

分類 (call 直後から順方向に制御フローを追う。分岐は両方、jmp は飛び先へ。深さ・命令数に上限あり):
  READ    : rax を読んでから書き換える前に読む経路がある (戻り値を使っている候補)
  RET     : rax を書き換えずに ret に達する経路がある (戻り値がそのまま上位関数の戻り値になり得る)
  CLOBBER : rax を書き換えてから先へ進む経路だけ (戻り値は捨てられている)
  UNKNOWN : 間接 jmp・上限到達などで判定を打ち切った
stosq / rep stosq は rax を読まず書き込み先として使うため READ から除外する (rax は 0 のゼロ埋め用)。
展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import os
import re
import sys
from collections import Counter

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
MAX_INS = 60
MAX_PATHS = 64
X86 = capstone.x86


def load():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = [(base + s.VirtualAddress, max(s.Misc_VirtualSize, s.SizeOfRawData),
             s.PointerToRawData, s.SizeOfRawData, s.Characteristics)
            for s in pe.sections]
    return raw, secs


def va_to_off(secs, va):
    for sva, size, praw, rsz, _ in secs:
        if sva <= va < sva + size and va - sva < rsz:
            return praw + (va - sva)
    return None


def text_ranges(secs):
    return [(sva, sva + size, praw, rsz) for sva, size, praw, rsz, ch in secs if ch & 0x20000000]


RAX_RE = re.compile(r"\b(rax|eax|ax|al|ah)\b")


def rax_effect(ins):
    """'read' / 'write' / None。rax 系レジスタについて、命令が値を読むか (read)、値を捨てて書き換えるか (write) を返す。"""
    mn = ins.mnemonic
    parts = [p.strip() for p in ins.op_str.split(",")] if ins.op_str else []
    if mn.startswith("stos") or mn.startswith("rep stos"):
        return "read"  # stosq は rax の値を [rdi] へ格納する
    if mn == "call":
        return "write"
    if mn == "ret" or mn.startswith("j"):
        return None
    if not any(RAX_RE.search(p) for p in parts):
        return None
    if mn in ("xor", "sub") and len(parts) == 2 and parts[0] == parts[1]:
        return "write"  # 自己ゼロ化は rax を読まない
    if mn in ("mov", "movzx", "movsx", "movsxd", "lea") and RAX_RE.fullmatch(parts[0]):
        return "read" if any(RAX_RE.search(p) for p in parts[1:]) else "write"
    return "read"


def classify(md, raw, secs, start_va, callee):
    results = set()
    stack = [(start_va, 0)]
    seen = set()
    n_paths = 0
    while stack:
        va, depth = stack.pop()
        if (va, depth // 8) in seen:
            continue
        seen.add((va, depth // 8))
        n_paths += 1
        if n_paths > MAX_PATHS:
            results.add("UNKNOWN")
            break
        off = va_to_off(secs, va)
        if off is None:
            results.add("UNKNOWN")
            continue
        done = False
        for i, ins in enumerate(md.disasm(raw[off:off + MAX_INS * 15], va)):
            if i >= MAX_INS:
                results.add("UNKNOWN")
                break
            eff = rax_effect(ins)
            if eff == "read":
                results.add("READ")
                done = True
                break
            if eff == "write":
                results.add("CLOBBER")
                done = True
                break
            if ins.mnemonic == "ret":
                results.add("RET")
                done = True
                break
            if ins.mnemonic == "jmp":
                if ins.operands and ins.operands[0].type == X86.X86_OP_IMM:
                    stack.append((ins.operands[0].imm, depth + 1))
                else:
                    results.add("UNKNOWN")
                done = True
                break
            if ins.mnemonic.startswith("j"):
                if ins.operands and ins.operands[0].type == X86.X86_OP_IMM:
                    stack.append((ins.operands[0].imm, depth + 1))
                else:
                    results.add("UNKNOWN")
                continue
            if ins.mnemonic == "int3" or ins.mnemonic == "(bad)":
                results.add("UNKNOWN")
                done = True
                break
        if not done:
            results.add("UNKNOWN")
    return results


def main():
    callee = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x415C30
    raw, secs = load()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    counts = Counter()
    sites = []
    for lo, hi, praw, rsz in text_ranges(secs):
        data = raw[praw:praw + rsz]
        pos = 0
        for m in range(len(data) - 4):
            if data[m] != 0xE8:
                continue
            rel = int.from_bytes(data[m + 1:m + 5], "little", signed=True)
            target = lo + m + 5 + rel
            if target == callee:
                sites.append(lo + m)
    for site in sites:
        res = classify(md, raw, secs, site + 5, callee)
        if "RET" in res:
            key = "RET" if "READ" not in res else "READ+RET"
        elif "READ" in res:
            key = "READ"
        elif res == {"CLOBBER"}:
            key = "CLOBBER"
        else:
            key = "UNKNOWN"
        counts[key] += 1
        print(hex(site), key, ",".join(sorted(res)))
    print("total", len(sites))
    for k, v in sorted(counts.items()):
        print(k, v)


if __name__ == "__main__":
    main()
