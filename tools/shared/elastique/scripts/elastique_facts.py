#!/usr/bin/env python3
"""élastique (zplane, win elastique_x64.dll) の静的 IPP 節の入口集合を実測する (T-SH-10 / #152).

入力: work/win/elastique_x64.dll (fl-win64 の extracted/block24357_PE.bin, docs/REFERENCES.md [WIN64])
出力: work/elastique/facts.json と標準出力の要約。依存: python3 + capstone (stdlib 以外は capstone のみ)。
"""
import collections
import json
import os
import struct
import sys

from capstone import CS_ARCH_X86, CS_MODE_64, CS_OP_IMM, CS_OP_MEM, Cs
from capstone.x86 import X86_REG_RIP

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED = os.path.normpath(os.path.join(HERE, "..", ".."))
DEFAULT_DLL = os.path.join(SHARED, "work", "win", "elastique_x64.dll")
OUT_DIR = os.path.join(SHARED, "work", "elastique")


def parse_pe(raw):
    e_lfanew = struct.unpack_from("<I", raw, 0x3C)[0]
    assert raw[e_lfanew:e_lfanew + 4] == b"PE\0\0", "not a PE"
    nsec, = struct.unpack_from("<H", raw, e_lfanew + 6)
    optsz, = struct.unpack_from("<H", raw, e_lfanew + 20)
    opt = e_lfanew + 24
    assert struct.unpack_from("<H", raw, opt)[0] == 0x20B, "not PE32+"
    image_base, = struct.unpack_from("<Q", raw, opt + 24)
    dirs = opt + 112
    sections = []
    for i in range(nsec):
        s = opt + optsz + i * 40
        name = raw[s:s + 8].rstrip(b"\0").decode("ascii", "replace")
        vsize, va, rawsz, rawptr = struct.unpack_from("<IIII", raw, s + 8)
        sections.append({"name": name, "va": va, "vsize": vsize, "rawsize": rawsz, "rawptr": rawptr})
    image = bytearray(max(s["va"] + max(s["vsize"], s["rawsize"]) for s in sections))
    for s in sections:
        n = min(s["rawsize"], s["vsize"]) if s["vsize"] else s["rawsize"]
        image[s["va"]:s["va"] + n] = raw[s["rawptr"]:s["rawptr"] + n]
    dd = {}
    for idx, key in ((0, "export"), (1, "import"), (3, "exception")):
        rva, size = struct.unpack_from("<II", raw, dirs + idx * 8)
        dd[key] = (rva, size)
    return image_base, sections, image, dd


def cstr(image, rva):
    end = image.index(b"\0", rva)
    return image[rva:end].decode("ascii", "replace")


def exports(image, dd):
    rva, _ = dd["export"]
    nnames, = struct.unpack_from("<I", image, rva + 24)
    funcs, names, ords = struct.unpack_from("<III", image, rva + 28)
    out = []
    for i in range(nnames):
        nrva, = struct.unpack_from("<I", image, names + 4 * i)
        ordidx, = struct.unpack_from("<H", image, ords + 2 * i)
        frva, = struct.unpack_from("<I", image, funcs + 4 * ordidx)
        out.append((cstr(image, nrva), frva))
    return out


def imports(image, dd):
    rva, _ = dd["import"]
    out = {}
    while True:
        oft, _, _, name, ft = struct.unpack_from("<IIIII", image, rva)
        if oft == 0 and name == 0 and ft == 0:
            break
        dll = cstr(image, name)
        thunk = oft or ft
        names = []
        while True:
            v, = struct.unpack_from("<Q", image, thunk)
            if v == 0:
                break
            if v & (1 << 63):
                names.append("ord%d" % (v & 0xFFFF))
            else:
                names.append(cstr(image, v + 2))
            thunk += 8
        out[dll] = names
        rva += 20
    return out


def pdata_funcs(image, image_base, dd):
    rva, size = dd["exception"]
    out = []
    for i in range(0, size - 11, 12):
        b, e, _ = struct.unpack_from("<III", image, rva + i)
        if b:
            out.append((image_base + b, image_base + e))
    return out


def main():
    dll = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DLL
    raw = open(dll, "rb").read()
    base, sections, image, dd = parse_pe(raw)
    sec = {s["name"]: s for s in sections}

    def rng(name):
        s = sec[name]
        return base + s["va"], base + s["va"] + s["vsize"]

    ipp, txt = rng("IPPCODE"), rng(".text")
    inside = lambda x, r: r[0] <= x < r[1]  # noqa: E731
    funcs = pdata_funcs(image, base, dd)
    imp = imports(image, dd)
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True

    def insns(lo, hi):
        return md.disasm(bytes(image[lo - base:hi - base]), lo)

    entry_sites = collections.Counter()
    callers = set()
    ipp_out = 0
    text_ind = collections.Counter()
    ipp_ind = collections.Counter()
    text_rip_ipp = 0
    ipp_rip_ipp = 0
    for a, b in funcs:
        src_ipp = inside(a, ipp)
        if not (src_ipp or inside(a, txt)):
            continue
        for ins in insns(a, b):
            op0 = ins.operands[0] if ins.operands else None
            if ins.mnemonic in ("call", "jmp") and op0 is not None:
                if op0.type == CS_OP_IMM:
                    t = op0.imm
                    if inside(t, ipp):
                        if not src_ipp:
                            entry_sites[t] += 1
                            callers.add(a)
                    elif src_ipp:
                        ipp_out += 1
                else:
                    (ipp_ind if src_ipp else text_ind)[ins.mnemonic + ("_mem" if op0.type == CS_OP_MEM else "_reg")] += 1
            for op in ins.operands:
                if op.type == CS_OP_MEM and op.mem.base == X86_REG_RIP:
                    t = ins.address + ins.size + op.mem.disp
                    if inside(t, ipp):
                        if src_ipp:
                            ipp_rip_ipp += 1
                        else:
                            text_rip_ipp += 1
    ptrs = 0
    for s in ("IPPCODE", ".rdata", ".data", ".pdata"):
        if s not in sec:
            continue
        v0 = sec[s]["va"]
        for i in range(v0, v0 + sec[s]["vsize"] - 7, 8):
            v, = struct.unpack_from("<Q", image, i)
            if inside(v, ipp):
                ptrs += 1
    callee_sizes = []
    pd_starts = {a: b for a, b in funcs}
    for t in entry_sites:
        if t in pd_starts:
            callee_sizes.append(pd_starts[t] - t)
    callee_sizes.sort()
    ipp_pdata = sum(1 for a, _ in funcs if inside(a, ipp))
    facts = {
        "file": os.path.basename(dll),
        "bytes": len(raw),
        "image_base": hex(base),
        "sections": [{"name": s["name"], "va": hex(s["va"]), "vsize": s["vsize"]} for s in sections],
        "exports": [{"name": n, "rva": hex(r)} for n, r in exports(image, dd)],
        "imports": {k: len(v) for k, v in imp.items()},
        "imports_ws2_32": imp.get("WS2_32.dll", []),
        "pdata_funcs": len(funcs),
        "pdata_in_text": sum(1 for a, _ in funcs if inside(a, txt)),
        "pdata_in_ipp": ipp_pdata,
        "text_to_ipp_call_sites": sum(entry_sites.values()),
        "text_to_ipp_entries_distinct": len(entry_sites),
        "text_to_ipp_entries_with_pdata": len(callee_sizes),
        "text_funcs_calling_ipp": len(callers),
        "text_to_ipp_entry_pdata_size_min_med_max_sum": [
            callee_sizes[0], callee_sizes[len(callee_sizes) // 2], callee_sizes[-1], sum(callee_sizes)
        ] if callee_sizes else [],
        "ipp_to_outside_direct_calls": ipp_out,
        "ipp_indirect": dict(ipp_ind),
        "text_indirect": dict(text_ind),
        "rip_refs_text_to_ipp": text_rip_ipp,
        "rip_refs_ipp_to_ipp": ipp_rip_ipp,
        "abs_8byte_ptrs_into_ipp": ptrs,
        "entry_addresses": [hex(t) for t, _ in entry_sites.most_common()],
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "facts.json"), "w") as f:
        json.dump(facts, f, ensure_ascii=False, indent=1)
    summary = {k: v for k, v in facts.items() if k not in ("entry_addresses", "sections", "exports")}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print("exports:", len(facts["exports"]), [e["name"] for e in facts["exports"]])


if __name__ == "__main__":
    main()
