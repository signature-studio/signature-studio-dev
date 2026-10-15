#!/usr/bin/env python3
"""ildsp の閉包 (ildsp_vtable.py --seed の JSON) に出る間接 call / jmp の宛先を、スロットの値から分類する。

usage: ildsp_indirect_resolve.py <json> [PE] [--key closure_seed]
  既定 PE: $FL_WIN64_DIR/extracted/block24360_PE.bin (tools/shared/paths.py)
  入力 JSON は ildsp_vtable.py --seed <RVA> --out <json> で作る (既定 key: closure_seed)

分類 (事実のみ。trap 化か静的確定かの判断は tools/shared/lift/ildsp/REPORT_APPENDIX_3346.md):
  IAT : スロットが import directory の IAT 項。宛先は import 名で確定する。
  ptr : スロットが IAT 外。再配置済みポインタの値を VA で出し、その先頭命令を 2 段まで辿る
        (`jmp reg` で終われば宛先は実行時の reg 値)。
  writes : .text と IPPCODE の線形走査 (不正バイトは 1 byte 飛ばす) で、スロットを書く命令の件数
        (メモリが第 1 オペランドの mov 系・rip 相対)。読み出し (call/jmp/mov reg,[slot]) は数えない。
  guard : load config の GuardCF/XFG の check・dispatch pointer と一致する印。
"""
import sys, os, json, argparse, struct
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
from paths import FL_WIN64_DIR
import pefile, capstone

MEM_WRITE = 0x80000000
GUARD_FIELDS = ("GuardCFCheckFunctionPointer", "GuardCFDispatchFunctionPointer",
                "GuardXFGCheckFunctionPointer", "GuardXFGDispatchFunctionPointer")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json")
    ap.add_argument("pe", nargs="?", default=os.path.join(FL_WIN64_DIR, "extracted", "block24360_PE.bin"))
    ap.add_argument("--key", default="closure_seed")
    a = ap.parse_args()
    cl = json.load(open(a.json))[a.key]

    pe = pefile.PE(a.pe, fast_load=True)
    pe.parse_data_directories(directories=[
        pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
        pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_LOAD_CONFIG"],
        pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    img = pe.get_memory_mapped_image()
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = {s.Name.rstrip(b"\0").decode(errors="replace"): s for s in pe.sections}
    iat = {}
    for d in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
        for imp in d.imports:
            iat[imp.address - base] = f"{d.dll.decode()}!{(imp.name or b'').decode() or '#' + str(imp.ordinal)}"
    lc = pe.DIRECTORY_ENTRY_LOAD_CONFIG.struct
    guard = {getattr(lc, k) - base: k for k in GUARD_FIELDS if getattr(lc, k, 0)}
    relocs = {e.rva for b in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []) for e in b.entries if e.type}
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def sweep(sec):
        lo, hi = sec.VirtualAddress, sec.VirtualAddress + sec.Misc_VirtualSize
        off = lo
        while off < hi:
            ins = next(md.disasm(bytes(img[off:off + 16]), off), None)
            if ins is None:
                off += 1
                continue
            off += ins.size
            yield ins

    def rip_target(ins):
        disp = struct.unpack_from("<i", bytes(ins.bytes), len(ins.bytes) - 4)[0]
        return ins.address + ins.size + disp

    slots = {int(s["slot_rva"], 16) for s in cl["indirect_calls"] + cl["indirect_jmps"] if s.get("slot_rva")}
    writes = {k: [] for k in slots}
    code = [s for n, s in secs.items() if n in (".text", "IPPCODE")]
    for sec in code:
        for ins in sweep(sec):
            if "[rip" not in ins.op_str or ins.mnemonic in ("call", "jmp", "lea", "cmp", "test"):
                continue
            if "[rip" not in ins.op_str.split(",")[0]:
                continue
            t = rip_target(ins)
            if t in writes:
                writes[t].append(f"{hex(ins.address)} {ins.mnemonic} {ins.op_str}")

    def slot_value(rva):
        return struct.unpack_from("<Q", img, rva)[0] - base

    def sec_of(rva):
        for n, s in secs.items():
            if s.VirtualAddress <= rva < s.VirtualAddress + s.Misc_VirtualSize:
                return n
        return "-"

    def chain(rva, depth=2):
        ins = next(md.disasm(bytes(img[rva:rva + 16]), rva), None)
        if ins is None:
            return "undecodable"
        s = f"{hex(rva)} {ins.mnemonic} {ins.op_str}"
        if ins.mnemonic == "jmp" and "[rip" in ins.op_str and depth > 0:
            nxt = rip_target(ins)
            return f"{s} -> slot {hex(nxt)} [{hex(slot_value(nxt))} {chain(slot_value(nxt), depth - 1)}]"
        return s

    print(f"# ildsp_indirect_resolve: {os.path.basename(a.pe)} key={a.key} sites={len(cl['indirect_calls']) + len(cl['indirect_jmps'])}")
    counts = {"IAT": 0, "ptr": 0}
    for kind, sites in (("call", cl["indirect_calls"]), ("jmp", cl["indirect_jmps"])):
        for s in sites:
            slot = int(s["slot_rva"], 16)
            if s.get("import") or slot in iat:
                counts["IAT"] += 1
                detail = f"import {iat.get(slot, s.get('import'))}"
                cls = "IAT"
            else:
                counts["ptr"] += 1
                v = slot_value(slot)
                cls = "ptr"
                detail = f"section={sec_of(slot)} reloc={'yes' if slot in relocs else 'no'} target={hex(v)} ({sec_of(v)}) chain: {chain(v)}"
            g = guard.get(slot, "-")
            print(f"{kind} {s['site']} in {s['in_func']} slot={hex(slot)} {cls} guard={g} writes={len(writes[slot])} | {detail}")
    print(f"# summary: IAT={counts['IAT']} ptr={counts['ptr']}")
    for slot in sorted(slots):
        sec = secs[sec_of(slot)]
        writable = bool(sec.Characteristics & MEM_WRITE)
        print(f"# slot {hex(slot)} section={sec_of(slot)} writable={writable} writes_in_code={len(writes[slot])} {writes[slot][:3]}")


if __name__ == "__main__":
    main()
