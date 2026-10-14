#!/usr/bin/env python3
# usage: 実行はこのディレクトリ (tools/targets/massivex) から。
#   python3 license/scripts/mx_indirect_refs.py ["work/extracted/VST3/Massive X.vst3"]
"""N6 読み手 5 関数 (#1439 / #1017) への間接参照を 4 系統で全域走査する。

  A. 8B 絶対 VA (vtable・関数ポインタ表): 全セクションの raw バイト列
  B. 4B RVA (image base 相対): 全セクションの raw バイト列
  C. 命令オペランド: RIP 相対 mem の実効先・即値 imm が読み手 VA と一致する命令 (.text 線形走査)
  D. 自己相対 4B (moc/qrc 型テーブル): 4B 位置 p の符号付き値 d に対し p_va + d が読み手 VA と一致

自己検査 (--selftest) は各系統に既知の参照を埋め込み、検出できなければ exit 1 にする。
"""
import struct
import sys

import capstone
import numpy as np
import pefile

READERS = {
    "N6-1 0x180f95e20": 0x180F95E20,
    "N6-2 0x181142370": 0x181142370,
    "N6-3 0x181144570": 0x181144570,
    "N6-4 0x181142640": 0x181142640,
    "N6-5 0x1811453f0": 0x1811453F0,
}
STRINGS = {
    "N6 0x184ffcf87": 0x184FFCF87,
    "N6 0x184ffcfe8": 0x184FFCFE8,
    "N6 0x184ffd03f": 0x184FFD03F,
    "N6 0x184ffd092": 0x184FFD092,
    "N6 0x184ffd0d6": 0x184FFD0D6,
    "N6 0x184ffd131": 0x184FFD131,
    "N5 MXDemoPopup.qml": 0x18415F411,
    "N5 demoExpired": 0x184879407,
    "N5 demoExpiredChanged": 0x1848792B9,
    "N5 subscriptionExpired": 0x18487941A,
}
TARGETS = set(READERS.values()) | set(STRINGS.values())


def scan_data(data, base_va, targets):
    """A/B/D: raw バイト列 (base_va から始まる領域) を走査する。"""
    hits = {"abs8": {t: [] for t in targets}, "rva4": {t: [] for t in targets}, "self4": {t: [] for t in targets}}
    buf = bytes(data)
    # 8B 絶対 (1 バイト単位で走査: 非整列ポインタも拾う)
    for t in targets:
        q = struct.pack("<Q", t)
        i = buf.find(q)
        while i != -1:
            hits["abs8"][t].append(base_va + i)
            i = buf.find(q, i + 1)
    # 4B RVA (image base 相対) と 4B 自己相对
    # 開始 offset k = 0..3 ごとに 4B 配列化し、任意バイト位置を重複なく覆う
    ib = IMAGE_BASE
    for k in range(4):
        arr = np.frombuffer(buf[k: k + (len(buf) - k) // 4 * 4], dtype="<i4")
        off = base_va + k
        for t in targets:
            r = (t - ib) & 0xFFFFFFFF
            idx = np.nonzero(arr.view(np.uint32) == r)[0]
            for j in idx:
                hits["rva4"][t].append(off + int(j) * 4)
            # 自己相対: 位置 p の値 d で p + d == t (d は符号付き)
            p_va = off + np.arange(arr.size, dtype=np.int64) * 4
            cand = p_va + arr.astype(np.int64)
            idx2 = np.nonzero(cand == t)[0]
            for j in idx2:
                hits["self4"][t].append(int(p_va[j]))
    for key in ("rva4", "self4"):
        for t in targets:
            hits[key][t].sort()
    return hits


IMAGE_BASE = 0x180000000


def scan_text(code, text_va, targets):
    """C: 線形逆アセンブルで RIP 相対 mem の実効先・即値が読み手 VA と一致する命令を列挙する。"""
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    hits = {t: [] for t in targets}
    buf = bytes(code)
    pos = 0
    while pos < len(buf):
        end = 0
        for ins in md.disasm(buf[pos:pos + 0x1000], text_va + pos):
            end = ins.address - (text_va + pos) + ins.size
            for op in ins.operands:
                if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                    dst = ins.address + ins.size + op.mem.disp
                    if dst in hits:
                        hits[dst].append((hex(ins.address), ins.mnemonic, "rip"))
                elif op.type == capstone.x86.X86_OP_IMM:
                    imm = op.imm & 0xFFFFFFFFFFFFFFFF
                    if imm in hits:
                        hits[imm].append((hex(ins.address), ins.mnemonic, "imm"))
        pos += end if end else 1
    return hits


def selftest():
    text_va = 0x180001000
    code = bytearray(b"\x90" * 0x10)
    t0 = list(TARGETS)[0]
    code += b"\x48\x8d\x05" + (t0 - (text_va + len(code) + 7)).to_bytes(4, "little", signed=True)  # lea rax,[rip+t0]
    code += b"\x90" * 0x10
    hits = scan_text(bytes(code), text_va, TARGETS)
    ok_c = len(hits[t0]) == 1
    data = bytearray(b"\x00" * 64)
    data[0:8] = struct.pack("<Q", t0)
    data[16:20] = ((t0 - IMAGE_BASE) & 0xFFFFFFFF).to_bytes(4, "little")
    data[32:36] = (t0 - (0x180100000 + 32)).to_bytes(4, "little", signed=True)
    d = scan_data(data, 0x180100000, TARGETS)
    ok_a = len(d["abs8"][t0]) == 1
    ok_b = len(d["rva4"][t0]) == 1
    ok_d = len(d["self4"][t0]) == 1
    print(f"selftest abs8={len(d['abs8'][t0])} rva4={len(d['rva4'][t0])} self4={len(d['self4'][t0])} rip/imm={len(hits[t0])} (期待 1/1/1/1)")
    ud = bytearray(b"\x00" * 64)
    ud[1:5] = ((t0 - IMAGE_BASE) & 0xFFFFFFFF).to_bytes(4, "little")
    ud[33:37] = (t0 - (0x180100000 + 33)).to_bytes(4, "little", signed=True)
    du = scan_data(bytes(ud), 0x180100000, TARGETS)
    ok_u = du["rva4"][t0] == [0x180100000 + 1] and du["self4"][t0] == [0x180100000 + 33]
    print(f"selftest unaligned rva4={[hex(x) for x in du['rva4'][t0]]} self4={[hex(x) for x in du['self4'][t0]]} (期待 offset 1 / 33)")
    ok = ok_a and ok_b and ok_c and ok_d and ok_u
    print("selftest:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "work/extracted/VST3/Massive X.vst3"
    data = open(path, "rb").read()
    pe = pefile.PE(data=data, fast_load=True)
    ib = pe.OPTIONAL_HEADER.ImageBase
    assert ib == IMAGE_BASE, hex(ib)
    total = {k: {t: [] for t in TARGETS} for k in ("abs8", "rva4", "self4", "rip_imm")}
    for s in pe.sections:
        name = s.Name.rstrip(b"\0").decode(errors="replace")
        raw = data[s.PointerToRawData: s.PointerToRawData + s.SizeOfRawData]
        base = ib + s.VirtualAddress
        h = scan_data(raw, base, TARGETS)
        for k in ("abs8", "rva4", "self4"):
            for t in TARGETS:
                total[k][t] += h[k][t]
        print(f"section {name:8s} VA {base:#x} size {len(raw)} : abs8 {sum(len(h['abs8'][t]) for t in TARGETS)} rva4 {sum(len(h['rva4'][t]) for t in TARGETS)} self4 {sum(len(h['self4'][t]) for t in TARGETS)}")
    text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
    t_off, t_va, t_sz = text.PointerToRawData, ib + text.VirtualAddress, text.SizeOfRawData
    th = scan_text(data[t_off: t_off + t_sz], t_va, TARGETS)
    for t in TARGETS:
        total["rip_imm"][t] = th[t]
    for name, t in list(READERS.items()) + [(f"string {k}", v) for k, v in STRINGS.items()]:
        print(f"\n{name}")
        for k in ("abs8", "rva4", "self4"):
            v = total[k][t]
            print(f"  {k}: {len(v)} 件", [hex(x) for x in v[:8]])
        v = total["rip_imm"][t]
        print(f"  rip/imm (命令): {len(v)} 件", v[:8])


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
