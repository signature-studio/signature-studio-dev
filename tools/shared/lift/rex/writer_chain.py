#!/usr/bin/env python3
"""REX の .data 書込箇所と、DllMain からの到達可否を静的に測る (T-SH-129 / #4833)。

(1) .text 全関数 (.pdata) を走査し、RIP 相対の memory 書込先が .data 範囲に入る命令を全て列挙する。
(2) DllMain (AddressOfEntryPoint) を根に、rex_closure.py と同じ規則 (直接 call/tail-jmp・.pdata 範囲・
    IAT 解決) で閉包を取り、(1) の書込命令のうち閉包に含まれるものを「到達」とする。
(3) 閉包の import 名と、DllMain 閉包の movnti 件数を出す。
間接 call/jmp の先は含まない (下限側)。lift はしない。

usage: python3 writer_chain.py [--pe PATH] [--json OUT]   (既定 PE = $FL_WIN64_DIR/extracted/block24351_PE.bin)
"""
import argparse, json, os, struct
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_IMM, CS_OP_MEM
from capstone.x86 import X86_REG_RIP

ap = argparse.ArgumentParser()
ap.add_argument("--pe", default=None)
ap.add_argument("--json", default=None)
args = ap.parse_args()
pe_path = args.pe or os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block24351_PE.bin")

pe = pefile.PE(pe_path, fast_load=False)
IMG = pe.OPTIONAL_HEADER.ImageBase
ENTRY = pe.OPTIONAL_HEADER.AddressOfEntryPoint
TEXT = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
TEXT_LO, TEXT_HI = TEXT.VirtualAddress, TEXT.VirtualAddress + TEXT.Misc_VirtualSize
DATA = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".data")
DATA_LO, DATA_HI = DATA.VirtualAddress, DATA.VirtualAddress + DATA.Misc_VirtualSize
data = pe.get_memory_mapped_image()

iat = {}
for d in pe.DIRECTORY_ENTRY_IMPORT:
    for imp in d.imports:
        iat[imp.address - IMG] = "%s!%s" % (d.dll.decode(), imp.name.decode() if imp.name else "ord%d" % imp.ordinal)

pdata = []
for s in pe.sections:
    if s.Name.rstrip(b"\0") == b".pdata":
        raw = s.get_data()
        for i in range(0, len(raw) - 11, 12):
            b, en, _ = struct.unpack_from("<III", raw, i)
            if b:
                pdata.append((b, en))
pdata.sort()
pd_starts = [b for b, _ in pdata]

md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True


def func_range(rva):
    for b, en in pdata:
        if b <= rva < en:
            return b, en
    i = next((k for k, s in enumerate(pd_starts) if s > rva), None)
    return rva, (pd_starts[i] if i is not None else TEXT_HI)


def analyse(lo, hi):
    """(命令 RVA 集合, 直接 call/tail-jmp 先, import 集合, movnti 数, .data 書込命令 [(RVA, 先 RVA)])。"""
    insns, targets, imports, movnti, writes = set(), set(), set(), 0, []
    for ins in md.disasm(data[lo:hi], IMG + lo):
        rva = ins.address - IMG
        insns.add(rva)
        if ins.mnemonic.startswith("movnt"):
            movnti += 1
        if ins.mnemonic in ("call", "jmp") and ins.operands:
            op = ins.operands[0]
            if op.type == CS_OP_IMM:
                t = op.imm - IMG
                if TEXT_LO <= t < TEXT_HI and not (lo <= t < hi):
                    targets.add(t)
            elif op.type == CS_OP_MEM and op.mem.base == X86_REG_RIP:
                slot = rva + ins.size + op.mem.disp
                if slot in iat:
                    imports.add(iat[slot])
        if ins.mnemonic == "mov" and len(ins.operands) == 2 and ins.operands[0].type == CS_OP_MEM:
            m = ins.operands[0].mem
            if m.base == X86_REG_RIP:
                t = rva + ins.size + m.disp
                if DATA_LO <= t < DATA_HI:
                    writes.append((rva, t))
    return insns, targets, imports, movnti, writes


def reach(entry):
    """入口から命令単位で到達可能な命令だけを数える (.pdata 範囲の未到達部分は含めない)。

    fallthrough・jcc・直接 jmp を辿り、直接 call の先と範囲外の tail jmp の先は次の入口にする。
    間接 jmp/call の先は辿らない (数だけ数える)。範囲は .pdata 関数 (無ければ次の .pdata 先頭まで)。
    """
    lo0, hi0 = func_range(entry)
    dec = {}
    for lo_, hi_ in [(lo0, hi0)]:
        for ins in md.disasm(data[lo_:hi_], IMG + lo_):
            dec[ins.address - IMG] = ins
    work, seen_ins, nexts = [entry], set(), set()
    imports, movnti, writes, indirect = set(), 0, [], 0
    while work:
        a = work.pop()
        if a in seen_ins or a not in dec:
            continue
        seen_ins.add(a)
        ins = dec[a]
        m = ins.mnemonic
        if m.startswith("movnt"):
            movnti += 1
        if m == "mov" and len(ins.operands) == 2 and ins.operands[0].type == CS_OP_MEM and ins.operands[0].mem.base == X86_REG_RIP:
            t = a + ins.size + ins.operands[0].mem.disp
            if DATA_LO <= t < DATA_HI:
                writes.append((a, t))
        nxt = a + ins.size
        if m == "ret" or m == "int3":
            continue
        if m in ("call", "jmp") and ins.operands:
            op = ins.operands[0]
            if op.type == CS_OP_IMM:
                t = op.imm - IMG
                if lo0 <= t < hi0 and t in dec:
                    if m == "jmp":
                        work.append(t)
                        continue
                    nexts.add(t)
                elif TEXT_LO <= t < TEXT_HI:
                    nexts.add(t)
                    if m == "jmp":
                        continue
            elif op.type == CS_OP_MEM and op.mem.base == X86_REG_RIP:
                slot = a + ins.size + op.mem.disp
                if slot in iat:
                    imports.add(iat[slot])
                else:
                    indirect += 1
                if m == "jmp":
                    continue
            else:
                indirect += 1
                if m == "jmp":
                    continue
            if m == "call":
                work.append(nxt)
                continue
        if m.startswith("j") and m != "jmp":
            if ins.operands and ins.operands[0].type == CS_OP_IMM:
                t = ins.operands[0].imm - IMG
                if lo0 <= t < hi0:
                    work.append(t)
            work.append(nxt)
            continue
        work.append(nxt)
    return {"entry": entry, "insns": len(seen_ins), "imports": imports, "movnti": movnti,
            "writes": writes, "indirect": indirect, "nexts": nexts}


def closure(entry):
    seen = set()
    todo = [entry]
    insns_all, imports, movnti, writes, indirect = 0, set(), 0, [], 0
    while todo:
        e = todo.pop()
        if e in seen:
            continue
        seen.add(e)
        r = reach(e)
        insns_all += r["insns"]
        imports |= r["imports"]
        movnti += r["movnti"]
        writes += r["writes"]
        indirect += r["indirect"]
        todo.extend(t for t in r["nexts"] if t not in seen)
    return {"funcs": sorted(seen), "insns": insns_all, "imports": sorted(imports),
            "movnti": movnti, "writes": writes, "indirect": indirect}


# (1) 全 .text 関数の .data 書込箇所
all_writes = []
for b in sorted(set(pd_starts)):
    lo, hi = func_range(b)
    all_writes += analyse(lo, hi)[4]
all_writes = sorted(set(all_writes))

# (2) DllMain 閉包
dm = closure(ENTRY)
dm_w = sorted(set(dm["writes"]))

out = {
    "pe": os.path.basename(pe_path),
    "entry": hex(ENTRY),
    "data_range": [hex(DATA_LO), hex(DATA_HI)],
    "data_write_sites_all_text": [[hex(a), hex(t)] for a, t in all_writes],
    "dllmain": {"funcs": len(dm["funcs"]), "insns": dm["insns"], "imports": len(dm["imports"]),
                "movnti": dm["movnti"], "data_write_sites": [[hex(a), hex(t)] for a, t in dm_w]},
}
print("entry %s  .data %s..%s" % (hex(ENTRY), hex(DATA_LO), hex(DATA_HI)))
print("all .text .data write sites: %d" % len(all_writes))
for a, t in all_writes:
    print("   site 0x%x -> 0x%x" % (a, t))
print("DllMain closure: funcs=%d insns=%d imports=%d movnti=%d" % (len(dm["funcs"]), dm["insns"], len(dm["imports"]), dm["movnti"]))
print("DllMain closure .data write sites: %s" % (", ".join("0x%x->0x%x" % w for w in dm_w) or "none"))
print("DllMain closure imports: %s" % ",".join(dm["imports"]))

if args.json:
    with open(args.json, "w") as f:
        json.dump(out, f, indent=1)
