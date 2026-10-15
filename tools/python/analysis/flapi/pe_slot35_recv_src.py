#!/usr/bin/env python3
"""PY-190 / #3371 の補助: `call qword ptr [reg + 0x118]` (VMT slot 35) の受け手レジスタについて、
呼出し箇所の直前 (同一関数内・既定 80 命令) で最後に書かれた値の出どころを分類する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_slot35_recv_src.py

分類 (出どころの形だけ。型は決めない):
  rip     : [rip+...] からの load (大域変数・VMT スロット参照)
  stack   : [rbp+...] / [rsp+...] からの load (ローカル・引数の退避先)
  call    : 直前の call の戻り値 (rax) をそのまま使用
  deref   : 他レジスタ経由の load ([reg+...])
  other   : その他の代入 (lea・算術・reg 間 mov など)
  clobber : 途中の call で caller-saved レジスタが壊れた後に、定義が見つからない
  none    : 窓内に定義が無い (関数引数 rcx/rdx/r8/r9 の可能性を含む)
"""
import bisect
import collections
import os
import re
import struct

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
CALL = re.compile(r"qword ptr \[(r\w+) \+ 0x118\]")
RIP = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")
CALLER_SAVED = {"rax", "rcx", "rdx", "r8", "r9", "r10", "r11"}
WRITERS = {"mov", "lea", "movzx", "movsxd", "movsx", "xchg"}
REGS = {"rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rbp", "rsp", "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15"}
WINDOW = 1 << 20
LINES = []


def classify(ins):
    src = ins.op_str.split(",", 1)[1].strip() if "," in ins.op_str else ""
    m = RIP.search(src)
    if m:
        d = int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
        return "rip@%x" % (ins.address + ins.size + d)
    if "[rbp" in src or "[rsp" in src:
        return "stack"
    m = re.search(r"\[(r\w+)", src)
    if m:
        return "deref:" + m.group(1)
    return "reg:" + src if src in REGS else "other"


def trace(body, reg, depth=0):
    for k in range(len(body) - 1, -1, -1):
        ins = body[k]
        if ins.mnemonic == "call":
            if reg in CALLER_SAVED:
                return "call" if reg == "rax" else "clobber"
            continue
        if ins.mnemonic not in WRITERS:
            continue
        dest = ins.op_str.split(",", 1)[0].strip()
        if dest != reg:
            continue
        kind = classify(ins)
        if depth < 4 and (kind.startswith("reg:") or kind.startswith("deref:")):
            src = kind.split(":", 1)[1]
            sub = trace(body[:k], src, depth + 1)
            return ("%s<-%s" % (kind.split(":")[0], sub))
        return kind
    return "none"


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    sec = {s.Name.rstrip(b"\0"): s for s in pe.sections}
    text = sec[b".text"]
    text_lo = base + text.VirtualAddress
    tb = raw[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
    pd = raw[sec[b".pdata"].PointerToRawData:sec[b".pdata"].PointerToRawData + sec[b".pdata"].SizeOfRawData]
    funcs = sorted((base + b, base + e) for b, e, _ in (struct.unpack_from("<III", pd, i) for i in range(0, len(pd) - 11, 12)) if b)
    starts = [f[0] for f in funcs]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = False

    sites = []
    pos = 0
    while pos < len(tb):
        chunk = tb[pos:pos + 0x10000 + 32]
        last = None
        for ins in md.disasm(chunk, text_lo + pos):
            if ins.address - text_lo - pos >= 0x10000:
                break
            last = ins
            if ins.mnemonic == "call" and CALL.search(ins.op_str):
                sites.append((ins.address, CALL.search(ins.op_str).group(1)))
        pos = pos + 1 if last is None else last.address - text_lo + last.size

    hist = collections.Counter()
    for a, reg in sites:
        i = bisect.bisect_right(starts, a) - 1
        if i < 0 or not (funcs[i][0] <= a < funcs[i][1]):
            hist["none"] += 1
            print("%x fn=- reg=%s src=none" % (a, reg))
            continue
        f0 = funcs[i][0]
        body = list(md.disasm(tb[f0 - text_lo:a - text_lo], f0))
        body = body[-WINDOW:]
        kind = trace(body, reg)
        hist[kind.split(":")[0]] += 1
        LINES.append("%x fn=%x reg=%s src=%s" % (a, f0, reg, kind))
        print(LINES[-1])

    print("total:", len(sites))
    for k, v in sorted(hist.items(), key=lambda kv: -kv[1]):
        print("  %s: %d" % (k, v))
    leaves = collections.Counter(re.findall(r"rip@[0-9a-f]+", "\n".join(LINES)))
    print("rip leaf globals (receiver chain の起点):")
    for k, v in leaves.most_common():
        print("  %s: %d" % (k, v))


if __name__ == "__main__":
    main()
