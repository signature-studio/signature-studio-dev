#!/usr/bin/env python3
"""PY-71 (#2501): VMT のスロットを間接 call する関数の候補を列挙する (実機不要・近似)。

  python3 analysis/py71_slotcallers.py <PE.bin> <VMT VA hex> <slot disp hex>

1. .text を 1 回線形走査し、int3 パディングの直後の命令を関数先頭 fn とみなす (py71_callers.py と同じ近似)。
2. 各関数について次の 2 つを集める。
   - クラス参照: VMT の自己ポインタ (VMT-0xc8) か VMT 自身を、RIP 相対の load/lea で読む、または即値で持つ。
   - スロット呼出し: `call qword ptr [reg + disp]` (disp は引数のスロット位置。base は RIP 以外)。
3. 両方を持つ関数を候補として出す。クラス参照を持つ関数の数と、スロット呼出しの総数も出す。
クラス参照の有無は「その関数がそのクラスの値を扱う」ことの近似であり、呼出し先のオブジェクトが
そのクラスのインスタンスであることは示さない。
"""
import collections
import sys

import capstone
import pefile

X = capstone.x86
path = sys.argv[1]
vmt = int(sys.argv[2], 0)
slot = int(sys.argv[3], 0)

pe = pefile.PE(path, fast_load=True)
data = open(path, "rb").read()
text = next(s for s in pe.sections if s.Name.startswith(b".text"))
tdata = data[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
tbase = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress
classrefs = {vmt, vmt - 0xC8}

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
funcs = collections.OrderedDict()
fn = None
pad = True
off = 0
while off < len(tdata):
    ins = next(md.disasm(tdata[off:off + 15], tbase + off, 1), None)
    if ins is None:
        off += 1
        pad = True
        continue
    off += ins.size
    if ins.mnemonic == "int3":
        pad = True
        continue
    if pad:
        fn = ins.address
        funcs.setdefault(fn, {"ref": False, "calls": []})
        pad = False
    rec = funcs.setdefault(fn, {"ref": False, "calls": []})
    for op in ins.operands:
        if op.type == X.X86_OP_IMM and op.imm in classrefs:
            rec["ref"] = True
        if op.type != X.X86_OP_MEM:
            continue
        if op.mem.base == X.X86_REG_RIP and ins.address + ins.size + op.mem.disp in classrefs:
            rec["ref"] = True
        if (ins.mnemonic == "call" and op.mem.base not in (X.X86_REG_RIP, 0)
                and op.mem.index == 0 and op.mem.disp == slot):
            rec["calls"].append(ins.address)

n_calls = sum(len(r["calls"]) for r in funcs.values())
n_ref = sum(1 for r in funcs.values() if r["ref"])
cands = [(f, r) for f, r in funcs.items() if r["ref"] and r["calls"]]
print(f"# VMT {vmt:#x} slot disp {slot:#x}: 関数 {len(funcs)} 件 / スロット呼出し {n_calls} 件 / クラス参照を持つ関数 {n_ref} 件")
print(f"# クラス参照とスロット呼出しを両方持つ関数: {len(cands)} 件")
for f, r in cands:
    print(f"fn={f:#x} calls=" + " ".join(f"{c:#x}" for c in r["calls"]))
