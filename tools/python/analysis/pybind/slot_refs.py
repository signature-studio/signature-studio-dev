#!/usr/bin/env python3
# PY-80 (#2633): FL PE の .text を走査し、Py_* 束縛 slot を rip 相対で参照する命令を列挙する。
#   束縛関数 (pybind_extract の 0xc395a0 付近) が格納するだけか、呼出し (call [rip+slot] / mov reg,[rip+slot]) まであるかを切り分ける。
#   python3 analysis/pybind/slot_refs.py --pe <block00031_PE.bin> --slot 0x16b84e0 [--slot ...] [--binder-range 0xc39500 0xc3a200]
#   出力: 参照箇所 VA・命令先頭 4 バイト・種別 (store = 束縛関数内の mov [slot],rax / load = 読出し)。
import argparse, struct

OPS = {
    b"\xff\x15": "call [rip]", b"\xff\x25": "jmp [rip]",
    b"\x48\x8b\x05": "mov reg,[rip]", b"\x48\x89\x05": "mov [rip],reg", b"\x48\x8d\x05": "lea (slot 自体の番地)",
    b"\x48\x83\x3d": "cmp qword [rip],imm8", b"\x48\x3b\x05": "cmp reg,[rip]",
}


def sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
    base = struct.unpack_from("<Q", d, e + 24 + 24)[0]
    out = []
    for i in range(nsec):
        o = e + 24 + optsz + 40 * i
        name = d[o:o + 8].rstrip(b"\0").decode("ascii", "replace")
        vsz, va, rawsz, rawoff, _, _, _, _, chars = struct.unpack_from("<IIIIIIHHI", d, o + 8)
        out.append({"name": name, "va": base + va, "vsize": vsz, "raw": rawoff, "rawsize": rawsz, "exec": bool(chars & 0x20000000)})
    return base, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pe", required=True)
    ap.add_argument("--slot", action="append", required=True)
    a = ap.parse_args()
    d = open(a.pe, "rb").read()
    base, secs = sections(d)
    slots = {int(s, 16): s for s in a.slot}
    for sec in secs:
        if not sec["exec"]:
            continue
        raw0, n = sec["raw"], min(sec["rawsize"], sec["vsize"] or sec["rawsize"])
        blob = d[raw0:raw0 + n]
        for i in range(len(blob) - 4):
            disp = struct.unpack_from("<i", blob, i)[0]
            for extra in (0, 1, 4):  # 後続の即値バイト数 (cmp qword [rip],imm8 など)
                end = sec["va"] + i + 4 + extra
                tgt = end + disp
                if tgt in slots:
                    pre = blob[max(0, i - 3):i]
                    kind = next((v for k, v in OPS.items() if pre.endswith(k)), "?")
                    print(f"{slots[tgt]} disp_va=0x{sec['va'] + i:x} opcode={kind} prefix={pre.hex()} extra_imm={extra}")
                    break


if __name__ == "__main__":
    main()
