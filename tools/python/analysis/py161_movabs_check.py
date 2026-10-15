#!/usr/bin/env python3
"""PY-161 (#3101): 0x104b843 の call 0x10469f0 の引数 edx・r8d (movabs 2 件を含む表引き) を整数演算で検算する (実機不要)。

  python3 analysis/py161_movabs_check.py <work/py53/fn.txt> [--negctl]

- 対象は 0x104b7f9〜0x104b83e の命令列。fn.txt の命令文字列だけを読み、整数演算 (mod 2^64) で
  movabs・lea (rip 相対・レジスタ同士)・movsxd・mov (base + index*8) を順に実行して、表の要素のアドレスを求める。
- 入力 k = ecx & 0xffff。j = k + 0x70000000 (PY-160 §3 の式)。期待値は edx 側 0x1539eb4 + 8k・r8d 側 0x1539eb8 + 8k (mod 2^64)。
- py88_writes.py の式 (0x104b843 の edx・r8d) に、movabs の即値と G[0x1549cb4] と SLOT[rbp+0x570]?@0x104aa97*8 が現れることも確かめる (式と整数演算の橋渡し)。
- --negctl: 1 つ目の movabs の即値を +8 にずらす。edx 側だけ mismatch が出るはず。
- mismatch が 1 件以上・橋渡しが失敗したら exit 1。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import py88_writes as pw  # noqa: E402

M = 1 << 64
LO, HI = 0x104B7FF, 0x104B83E
K_SAMPLES = [0x0, 0x1, 0x1234, 0xFFFF]
EXPECT = {"rdx": 0x1539EB4, "r8": 0x1539EB8}
REG64 = {"edx": "rdx", "r8d": "r8"}


def load(path):
    ins, order = {}, []
    for ln in open(path):
        m = re.match(r"(0x[0-9a-f]+): (\S+)\s*(.*)$", ln.strip())
        if m:
            a = int(m.group(1), 16)
            ins[a] = (m.group(2), m.group(3))
            order.append(a)
    return ins, order


def run(ins, order, k, delta_at=None):
    regs = {}
    j = (k + 0x70000000) % M
    addr = {}
    idx = {a: i for i, a in enumerate(order)}
    for a in order:
        if not (LO <= a <= HI):
            continue
        mn, ops = ins[a]
        parts = [p.strip() for p in ops.split(",")]
        if mn == "movabs":
            imm = int(parts[1], 16) + (8 if a == delta_at else 0)
            regs[parts[0]] = imm % M
        elif mn == "lea" and "rip" in ops:
            disp = int(re.search(r"rip \+ (0x[0-9a-f]+)", ops).group(1), 16)
            nxt = order[idx[a] + 1]
            regs[parts[0]] = (nxt + disp) % M
        elif mn == "lea":
            base, index = re.search(r"\[(\w+) \+ (\w+)\]", ops).groups()
            regs[parts[0]] = (regs[base] + regs[index]) % M
        elif mn == "movsxd" and "[rbp + 0x570]" in ops:
            regs[parts[0]] = j
        elif mn == "mov" and "dword ptr [" in ops:
            base, index = re.search(r"\[(\w+) \+ (\w+)\*8\]", ops).groups()
            addr[REG64[parts[0]]] = (regs[base] + regs[index] * 8) % M
    return addr


def main():
    path = sys.argv[1]
    negctl = "--negctl" in sys.argv[2:]
    ins, order = load(path)
    delta_at = 0x104B7FF if negctl else None
    mismatch = 0
    for k in K_SAMPLES:
        got = run(ins, order, k, delta_at)
        for reg, base in EXPECT.items():
            want = (base + 8 * k) % M
            ok = got.get(reg) == want
            mismatch += 0 if ok else 1
            print(f"k={k:#06x} {reg:3s} got={got.get(reg, 0):#018x} want={want:#018x} {'ok' if ok else 'MISMATCH'}")
    s = pw.Slicer(*pw.load(path))
    call_i = s.idx[0x104B83E]
    bridge = {
        "edx": (s.resolve("d", call_i, 0), ["0xfffffffc7fff0200", "G[0x1549cb4]", "SLOT[rbp+0x570]?@0x104aa97*8"]),
        "r8d": (s.resolve("r8", call_i, 0), ["0xfffffffc7fff0204", "G[0x1549cb4]", "SLOT[rbp+0x570]?@0x104aa97*8"]),
    }
    for reg, (text, needles) in bridge.items():
        miss = [n for n in needles if n not in text]
        print(f"py88 {reg}: {'ok' if not miss else 'MISSING ' + ', '.join(miss)}")
        mismatch += 1 if miss else 0
    print(f"mismatch={mismatch}")
    sys.exit(1 if mismatch else 0)


if __name__ == "__main__":
    main()
