#!/usr/bin/env python3
"""ILWASAPI2ASIO_x64.dll の ILWasapiToAsioDriver vtable を RTTI から復元し、
IASIO 各スロットの先頭命令を逆アセンブルして FL が期待する driver 面 (sample type,
buffer size 範囲, latency, sample rate 等) を実測する。出力: stdout (JSON は --json)。"""
import sys, struct, json, os
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared"))
from paths import FL_WIN64_DIR

PATH = sys.argv[1] if len(sys.argv) > 1 else \
    os.path.join(FL_WIN64_DIR, "extracted", "block00001_PE.bin")
pe = pefile.PE(PATH)
data = pe.get_memory_mapped_image()
base = pe.OPTIONAL_HEADER.ImageBase
md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = False

IASIO = ["QueryInterface", "AddRef", "Release", "init", "getDriverName", "getDriverVersion",
         "getErrorMessage", "start", "stop", "getChannels", "getLatencies", "getBufferSize",
         "canSampleRate", "getSampleRate", "setSampleRate", "getClockSources", "setClockSource",
         "getSamplePosition", "getChannelInfo", "createBuffers", "disposeBuffers",
         "controlPanel", "future", "outputReady"]

def find_vtable(name):
    needle = name.encode() + b"\0"
    td_name = data.find(needle)
    td = td_name - 16  # TypeDescriptor: vptr(8) spare(8) name
    rva_td = td
    # COL: signature=1, offset, cdOffset, typeDescriptorRVA (+12)
    res = []
    i = 0
    pat = struct.pack("<I", rva_td)
    while True:
        i = data.find(pat, i)
        if i < 0:
            break
        col = i - 12
        if col >= 0 and struct.unpack_from("<I", data, col)[0] == 1:
            col_va = base + col
            # vtable qword pointing at COL
            p = struct.pack("<Q", col_va)
            j = 0
            while True:
                j = data.find(p, j)
                if j < 0:
                    break
                res.append((col, j + 8, struct.unpack_from("<I", data, col + 4)[0]))
                j += 8
        i += 4
    return res

def va2off(va):
    return va - base

def read_vt(off, n=40):
    out = []
    for k in range(n):
        q = struct.unpack_from("<Q", data, off + 8 * k)[0]
        if not (base <= q < base + len(data)):
            break
        out.append(q)
    return out

def dis(va, nbytes=0x120, maxins=60):
    code = data[va2off(va): va2off(va) + nbytes]
    lines = []
    for ins in md.disasm(code, va):
        lines.append(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}")
        if ins.mnemonic == "ret" or len(lines) >= maxins:
            break
    return lines

if __name__ == "__main__":
    for nm in [".?AVILWasapiToAsioDriver@@", ".?AVWASAPIWrapper@@"]:
        for col, vt, off in find_vtable(nm):
            slots = read_vt(vt)
            print(f"== {nm} vtable@{base+vt:#x} (COL off={off}) slots={len(slots)}")
            if "Asio" in nm:
                for k, q in enumerate(slots):
                    print(f"  [{k:2}] {q:#x} {IASIO[k] if k < len(IASIO) else '?'}")
                if "--dis" in sys.argv:
                    for k in (4, 5, 9, 10, 11, 12, 13, 14, 15, 17, 18, 19, 22):
                        if k < len(slots):
                            print(f"-- slot {k} {IASIO[k] if k<len(IASIO) else '?'} @ {slots[k]:#x}")
                            print("\n".join(dis(slots[k])))
