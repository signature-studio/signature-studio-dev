#!/usr/bin/env python3
"""#3009: 殻 (block23663) → engine (block23664) の DispatchToEngine の selector 2・4 の戻り値と、
殻の wrapper (sel 2 = 0x846a80、sel 4 = 0x846ac0) の呼出し元の内側 id・戻り値の使用を出す。
また関数 0x84bc30 と 0x843930 への参照 (pdata の全関数の命令単位の走査) を出す。
usage: dispatch_selectors.py <fl-win64 extracted dir> [--nc]
  --nc: 期待値を 1 つ変えて exit 1 になることを確かめる (negative control)。 通常実行は期待値が一致すれば exit 0。
"""
import bisect
import os
import sys

import capstone
import pefile
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

ENGINE = "block23664_PE.bin"
SHELL = "block23663_PE.bin"
ZERO_TAILS = {0x180147CF5, 0x180147D02}  # cf5: jmp 先 (xor eax,eax の直前)、d02: xor eax,eax
VALUE_TAIL = 0x180147D04  # 戻り値 rax をそのまま返す共通出口
TABLE_SEL2 = (0x148350, 15)  # engine: sel 2 の第 2 段 (r9 を添字)
TABLE_SEL4 = (0x14838C, 15)  # engine: sel 4 の第 2 段
TABLE_TOP = (0x14831C, 13)  # engine: DispatchToEngine の第 1 段 (rdx-2)
WRAP_SEL2, WRAP_SEL4 = 0x846A80, 0x846AC0
TARGET_INNER = 0x84BC30
TARGET_STR = 0x843930


class Image:
    def __init__(self, path):
        self.pe = pefile.PE(path, fast_load=True)
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.pe.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]]
        )
        self.secs = [
            (self.base + s.VirtualAddress, s.Misc_VirtualSize, s.get_data(), s.Name.rstrip(b"\0").decode())
            for s in self.pe.sections
        ]
        self.funcs = sorted(
            {(self.base + e.struct.BeginAddress, self.base + e.struct.EndAddress)
             for e in self.pe.DIRECTORY_ENTRY_EXCEPTION}
        )
        self.starts = [f[0] for f in self.funcs]
        self.cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.cs.detail = True

    def rd(self, va, n):
        for lo, sz, d, _ in self.secs:
            if lo <= va < lo + sz:
                o = va - lo
                return d[o:o + n]
        raise ValueError(f"{va:#x} is outside the image")

    def func_of(self, va):
        k = bisect.bisect_right(self.starts, va) - 1
        if k >= 0 and self.funcs[k][0] <= va < self.funcs[k][1]:
            return self.funcs[k]
        return None

    def insns(self, start, end):
        return list(self.cs.disasm(self.rd(start, end - start), start))


def table_targets(img, tva, n):
    out = []
    for k in range(n):
        raw = img.rd(tva + 4 * k, 4)
        out.append(img.base + int.from_bytes(raw, "little", signed=True))
    return out


def classify_case(img, va):
    """va から直線的に読み、最初の無条件 jmp / ret / 共通出口で戻り値の型を決める。"""
    seen = []
    for i in img.cs.disasm(img.rd(va, 0x200), va):
        seen.append(i)
        if i.address in ZERO_TAILS:
            return "zero", seen[0], i
        if i.address == VALUE_TAIL:
            return "value", seen[0], seen[-2] if len(seen) > 1 else seen[0]
        if i.mnemonic == "jmp":
            if i.operands and i.operands[0].type == X86_OP_IMM:
                t = i.operands[0].imm
                if t in ZERO_TAILS:
                    return "zero", seen[0], i
                if t == VALUE_TAIL:
                    return "value", seen[0], seen[-2] if len(seen) > 1 else seen[0]
            return "other", seen[0], i
        if i.mnemonic == "ret":
            return "other", seen[0], i
        if len(seen) > 60:
            break
    return "other", seen[0], seen[-1]


def used_after_call(ins, k):
    """call の直後 8 命令で rax/eax を読むか、先に書くか、call/ret に達するか。"""
    for i in ins[k + 1:k + 9]:
        ops = i.op_str
        dst_rax = ops.startswith(("rax,", "eax,")) or ops == "eax, eax"
        reads = ("rax" in ops or "eax" in ops)
        if i.mnemonic == "ret":
            return "pass-through (ret)"
        if i.mnemonic == "call":
            return "unused before call"
        if reads and i.mnemonic in ("test", "cmp"):
            return f"used ({i.mnemonic} {ops})"
        if dst_rax and i.mnemonic in ("mov", "xor", "lea", "movsxd", "movzx"):
            if i.mnemonic == "xor" and ops == "eax, eax":
                return f"overwritten ({i.mnemonic} {ops})"
            if not (ops.split(", ", 1)[1].count("rax") or ops.split(", ", 1)[1].count("eax")):
                return f"overwritten ({i.mnemonic} {ops})"
        if reads:
            return f"used ({i.mnemonic} {ops})"
    return "unused in 8 insns"


def call_sites(img, target):
    hits = []
    for fs, fe in img.funcs:
        ins = img.insns(fs, fe)
        for k, i in enumerate(ins):
            if i.mnemonic == "call" and i.operands and i.operands[0].type == X86_OP_IMM \
                    and i.operands[0].imm == target:
                hits.append((i.address, fs, ins, k))
    return hits


def all_refs(img, targets):
    hits = {t: [] for t in targets}
    for fs, fe in img.funcs:
        for i in img.insns(fs, fe):
            for op in i.operands:
                if op.type == X86_OP_IMM and op.imm in hits:
                    hits[op.imm].append((i.address, f"{i.mnemonic} {i.op_str}", fs))
                if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                    t = i.address + i.size + op.mem.disp
                    if t in hits:
                        hits[t].append((i.address, f"{i.mnemonic} {i.op_str}", fs))
    for lo, sz, d, name in img.secs:
        if name.startswith(".text"):
            continue
        for t in targets:
            rva = (t - img.base).to_bytes(4, "little")
            for k in range(0, len(d) - 3):
                if d[k:k + 4] == rva:
                    hits[t].append((lo + k, f"DATA-RVA4 in {name}", 0))
    return hits


def main():
    args = [a for a in sys.argv[1:] if a != "--nc"]
    nc = "--nc" in sys.argv[1:]
    d = args[0]
    eng = Image(os.path.join(d, ENGINE))
    shell = Image(os.path.join(d, SHELL))
    fails = []

    def expect(name, got, want):
        ok = got == want
        print(f"CHECK {name}: got {got} want {want} {'OK' if ok else 'MISMATCH'}")
        if not ok:
            fails.append(name)

    # NC: 期待値を 1 つだけ変える。 sel 2 の第 2 段は全 15 件が 0 を返すはずで、14 と置くと exit 1 になる。
    want_sel2_zero = 14 if nc else 15
    print("## engine DispatchToEngine: 第 2 段の戻り値 (cf5/d02 = 0 に強制、d04 = rax をそのまま返す)")
    for label, (tva, n), want_zero in (
        ("sel2 table 0x148350", TABLE_SEL2, want_sel2_zero),
        ("sel4 table 0x14838c", TABLE_SEL4, 0),
    ):
        tg = table_targets(eng, eng.base + tva, n)
        zeros = 0
        print(f"### {label} ({n} entries)")
        for k, t in enumerate(tg):
            kind, first, last = classify_case(eng, t)
            zeros += kind == "zero"
            print(f"  idx {k:2d} -> {t:#x} [{kind}] first: {first.mnemonic} {first.op_str} | last: {last.mnemonic} {last.op_str}")
        expect(f"{label} zero-return count", zeros, want_zero)
    tg = table_targets(eng, eng.base + TABLE_TOP[0], TABLE_TOP[1])
    print("### top table 0x14831c (rdx-2 の 13 entry、第 1 段)")
    for k, t in enumerate(tg):
        first = next(eng.cs.disasm(eng.rd(t, 16), t))
        print(f"  idx {k:2d} -> {t:#x}: {first.mnemonic} {first.op_str}")

    print("\n## shell wrapper の呼出し元 (pdata 全関数の命令単位)")
    for name, wrap, want in (("sel2 0x846a80", WRAP_SEL2, 11), ("sel4 0x846ac0", WRAP_SEL4, 12)):
        sites = call_sites(shell, wrap)
        print(f"### {name}: {len(sites)} call sites")
        for va, fs, ins, k in sites:
            edx = next((x for x in reversed(ins[max(0, k - 12):k])
                        if x.op_str.startswith(("edx,", "rdx,"))), None)
            edx_s = f"{edx.mnemonic} {edx.op_str}" if edx else "?"
            print(f"  {va:#x} [fn {fs:#x}] inner(edx)<- {edx_s} | rax: {used_after_call(ins, k)}")
        expect(f"{name} call sites", len(sites), want)

    print("\n## 0x84bd8f の内側 id (0x84bc30 の 0x84bd00 の mask 判定)")
    mv = next(i for i in shell.insns(0x84BD00, 0x84BD10) if i.address == 0x84BD00)
    mem = mv.operands[1].mem
    mask_va = mv.address + mv.size + mem.disp
    mask = shell.rd(mask_va, 1)[0]
    allowed = [k for k in range(8) if (1 << k) & mask]
    print(f"  {mv.mnemonic} {mv.op_str} -> mask byte {mask:#x} @ {mask_va:#x}; esi in 0..7 with bit set: {allowed}")
    print("  (esi=3 は [obj+0x7c8]+0x48e != 0 のとき 0xc に写るため、0x84bd8f には届かない)")
    expect("0x84bd8f inner ids (esi in 0..7 with mask bit)", allowed, [3, 7])

    print("\n## 参照走査 (命令の即値・RIP 相対・データ内 RVA4)")
    refs = all_refs(shell, [TARGET_INNER, TARGET_STR, 0x843D30])
    for t in (0x843D30,):
        print(f"### {t:#x} (sel 4 id 0 の wrapper 0x843d30 の呼出し元)")
        for a, txt, fs in sorted(refs[t]):
            print(f"  {a:#x}: {txt} [fn {fs:#x}]")
    for t, want in ((TARGET_INNER, 0), (TARGET_STR, 6)):
        code_refs = [r for r in refs[t] if not r[1].startswith("DATA")]
        data_refs = [r for r in refs[t] if r[1].startswith("DATA")]
        print(f"### {t:#x}: code {len(code_refs)} / data {len(data_refs)}")
        for a, txt, fs in sorted(code_refs):
            print(f"  {a:#x}: {txt} [fn {fs:#x}]")
        for a, txt, _ in sorted(data_refs):
            print(f"  {a:#x}: {txt}")
        expect(f"{t:#x} code refs", len(code_refs), want)

    print("\nRESULT:", "FAIL " + ", ".join(fails) if fails else "PASS")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
