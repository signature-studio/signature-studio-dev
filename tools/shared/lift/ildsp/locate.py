#!/usr/bin/env python3
"""GeneralPitchShifter vtable の slot 4 (RVA 0x1aa3a0) または slot 5 (RVA 0x1aa470) の機械語と範囲を PE から切り出す (依存: pefile・capstone)。
usage: locate.py <block24360_PE.bin> <outdir> [slot]   (slot 既定 4・4 か 5)
  <outdir>/fn.bin       元の機械語 (RVA の begin から pefile で読む)
  <outdir>/ranges.json  {"image_base", "vtable_rva", "slot", "begin", "end", "range", "insns", "fn_name", "ret"}
  ret: 戻り値 (eax) を差分テストで比べるか。slot 4 は void (0)、slot 5 は `return 0` (1)。
検算 (fail で exit 1): vtable (RVA 0x3dfcf8) の該当 slot の値 = begin (VA)、命令数、最後が ret、直接 call/jmp 0、間接 call/jmp 0。"""
import json, os, struct, sys
import capstone, pefile

VTABLE_RVA = 0x3DFCF8
# slot: (begin RVA, 範囲のバイト数, 命令数, 戻り値を比べるか)
SLOTS = {4: (0x1AA3A0, 0xCC, 42, 0), 5: (0x1AA470, 3, 2, 1)}

def main():
    pe_path, outdir = sys.argv[1], sys.argv[2]
    slot = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    BEGIN, LEN, NINS, RET = SLOTS[slot]
    os.makedirs(outdir, exist_ok=True)
    pe = pefile.PE(pe_path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    slot_va, = struct.unpack("<Q", pe.get_data(VTABLE_RVA + 8 * slot, 8))
    assert slot_va == base + BEGIN, f"slot {slot} = {slot_va:#x} != {base + BEGIN:#x}"
    fn = pe.get_data(BEGIN, LEN)
    ins = list(capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64).disasm(fn, base + BEGIN))
    assert len(ins) == NINS and ins[-1].mnemonic == "ret", (len(ins), ins[-1].mnemonic)
    assert not [i for i in ins if i.mnemonic in ("call", "jmp")], "direct/indirect call or jmp in range"
    for i in ins:
        if i.mnemonic.startswith("j"):
            t = int(i.op_str, 16)
            assert base + BEGIN <= t < base + BEGIN + LEN, f"jcc {i.address:#x} leaves range"
    open(os.path.join(outdir, "fn.bin"), "wb").write(fn)
    rng = {"image_base": base, "vtable_rva": VTABLE_RVA, "slot": slot, "begin": base + BEGIN, "end": base + BEGIN + LEN,
           "range": f"{base + BEGIN:#x}-{base + BEGIN + LEN:#x}", "insns": len(ins), "fn_name": f"function_{base + BEGIN:x}",
           "ret": RET}
    json.dump(rng, open(os.path.join(outdir, "ranges.json"), "w"), indent=1)
    print(f"[locate] vtable {VTABLE_RVA:#x} slot {slot} -> {base + BEGIN:#x} ({LEN} B, {len(ins)} insns) range {rng['range']} name {rng['fn_name']} ret {RET}")

if __name__ == "__main__":
    main()
