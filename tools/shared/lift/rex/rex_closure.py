#!/usr/bin/env python3
"""REX Shared Library (win x64 `REX Shared Library.dll` = block24351_PE.bin) の export 閉包を測る (T-SH-11 / #153)。

各 export の stub を辿って実体 RVA を得て、直接 call / 関数外への直接 jmp を BFS で閉包化する。
閉包の関数範囲は .pdata の RUNTIME_FUNCTION で切る (無い先は次の .pdata 先頭までの近似)。
測るもの: 関数数・命令数 (命令開始の和集合)・間接 call/jmp 数・参照する import 名。
間接 call の先は含まない (下限側)。lift はしない。

usage: python3 rex_closure.py [--pe PATH] [--json OUT]   (既定 PE = $FL_WIN64_DIR/extracted/block24351_PE.bin)
"""
import argparse, json, os, struct, sys
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
TEXT = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
TEXT_LO = TEXT.VirtualAddress
TEXT_HI = TEXT.VirtualAddress + TEXT.Misc_VirtualSize
data = pe.get_memory_mapped_image()

exports = {e.name.decode(): e.address for e in pe.DIRECTORY_ENTRY_EXPORT.symbols if e.name}
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
    """rva を含む .pdata 関数範囲 (lo, hi)。無ければ次の .pdata 先頭までの近似。"""
    for b, en in pdata:
        if b <= rva < en:
            return b, en, True
    i = next((k for k, s in enumerate(pd_starts) if s > rva), None)
    hi = pd_starts[i] if i is not None else TEXT_HI
    return rva, hi, False


def resolve_stub(rva):
    """export stub が 1 命令の jmp rel32 なら実体へ辿る (最大 4 段)。"""
    for _ in range(4):
        ins = next(md.disasm(data[rva:rva + 16], IMG + rva, 1), None)
        if ins and ins.mnemonic == "jmp" and ins.operands and ins.operands[0].type == CS_OP_IMM:
            nxt = ins.operands[0].imm - IMG
            if TEXT_LO <= nxt < TEXT_HI:
                rva = nxt
                continue
        break
    return rva


def analyse(lo, hi):
    """関数範囲の命令を読み、(命令 RVA 集合, 直接 call/tail-jmp 先, 間接数, import 集合) を返す。"""
    insns, targets, indirect, imports = [], set(), 0, set()
    code = data[lo:hi]
    for ins in md.disasm(code, IMG + lo):
        insns.append(ins.address - IMG)
        if ins.mnemonic not in ("call", "jmp") or not ins.operands:
            continue
        op = ins.operands[0]
        if op.type == CS_OP_IMM:
            t = op.imm - IMG
            if TEXT_LO <= t < TEXT_HI and not (lo <= t < hi):
                targets.add(t)
            continue
        if op.type == CS_OP_MEM and op.mem.base == X86_REG_RIP:
            slot = ins.address - IMG + ins.size + op.mem.disp
            if slot in iat:
                imports.add(iat[slot])
                continue
        indirect += 1
    return insns, targets, indirect, imports


def closure(entry):
    seen_funcs = {}
    todo = [entry]
    all_insns = set()
    indirect_total = 0
    imports = set()
    while todo:
        rva = todo.pop()
        if rva in seen_funcs:
            continue
        lo, hi, has_pd = func_range(rva)
        insns, targets, ind, imp = analyse(lo, hi)
        seen_funcs[rva] = {"lo": lo, "hi": hi, "pdata": has_pd}
        all_insns.update(insns)
        indirect_total += ind
        imports |= imp
        todo.extend(t for t in targets if t not in seen_funcs)
    return {
        "funcs": len(seen_funcs),
        "insns": len(all_insns),
        "indirect": indirect_total,
        "imports": sorted(imports),
        "func_rvas": sorted(seen_funcs),
        "approx_funcs": sum(1 for v in seen_funcs.values() if not v["pdata"]),
    }


result = {"pe": os.path.basename(pe_path), "image_base": hex(IMG), "exports": {}, "union": {}}
union_fn, union_ins, union_ind, union_imp = set(), set(), 0, set()
for name in sorted(exports):
    stub = exports[name]
    body = resolve_stub(stub)
    c = closure(body)
    result["exports"][name] = {"stub_rva": hex(stub), "body_rva": hex(body), **{k: v for k, v in c.items() if k != "func_rvas"}}
    union_fn |= set(c["func_rvas"])
    union_imp |= set(c["imports"])
    result.setdefault("_funcs", {})[name] = c["func_rvas"]

for name, r in result["exports"].items():
    print("%-22s stub=%s body=%s funcs=%3d insns=%6d indirect=%3d approx=%d imports=%s" % (
        name, r["stub_rva"], r["body_rva"], r["funcs"], r["insns"], r["indirect"], r["approx_funcs"], ",".join(r["imports"]) or "-"))

all_funcs = set()
for v in result.pop("_funcs").values():
    all_funcs |= set(v)
print("UNION funcs=%d imports=%s" % (len(all_funcs), ",".join(sorted(union_imp)) or "-"))
result["union"] = {"funcs": len(all_funcs), "imports": sorted(union_imp)}

if args.json:
    with open(args.json, "w") as f:
        json.dump(result, f, indent=1)
