#!/usr/bin/env python3
"""selectOneChannel の 2 つのゲート (前提 0xd5af58・後段 0xd82c6a) の呼出し先と判定条件を PE から再現する (PY-248 / #3767)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/py248_gate_chain.py

- 出すもの: (1) 2 ゲートの連鎖の起点 (RIP 相対の解決)、(2) X+8 (O) の生成箇所とクラス参照、
  (3) O の VMT (クラス名・+0x48/+0x88/+0x98 の関数)、(4) 各関数の逆アセンブル (RIP 先の値付き)、
  (5) 選択フラグ F1・F2・Z へのバイト書込み箇所 (セル読込み直後の同一レジスタへの store の全 .text 走査)。
- 値は PE ファイル上の初期値。`bss` の値は実行時にしか決まらない (本スクリプトは書込み箇所だけを出す)。
展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import os
import re
import struct
import time

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
RAW = open(PE, "rb").read()
PEF = pefile.PE(data=RAW, fast_load=True)
BASE = PEF.OPTIONAL_HEADER.ImageBase
MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
MD.detail = True
RIP = capstone.x86.X86_REG_RIP
CHUNK = 1 << 16


def fo(va):
    rva = va - BASE
    for s in PEF.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            off = rva - s.VirtualAddress
            return None if off >= s.SizeOfRawData else s.PointerToRawData + off
    return None


def qword(va):
    f = fo(va)
    return None if f is None else struct.unpack("<Q", RAW[f:f + 8])[0]


def insns(va, n):
    f = fo(va)
    return list(MD.disasm(RAW[f:f + n * 16], va))[:n]


def rip_target(ins):
    for op in ins.operands:
        if op.type == capstone.x86.X86_OP_MEM and op.mem.base == RIP:
            return ins.address + ins.size + op.mem.disp
    return None


def show_val(va):
    v = qword(va)
    return "bss(runtime)" if v is None else f"{v:#x}"


def disasm_annot(va, n):
    for ins in insns(va, n):
        t = rip_target(ins)
        note = f"  ; [rip] -> {t:#x} = {show_val(t)}" if t is not None else ""
        print(f"  {ins.address:#x} {ins.mnemonic} {ins.op_str}{note}")


def main():
    print("== 1. 2 ゲートの起点 (RIP 相対の解決)")
    pre = insns(0xD5AF44, 1)[0]
    post = insns(0xD82C6A, 1)[0]
    s_pre, s_post = rip_target(pre), rip_target(post)
    print(f"  前提 {pre.address:#x} mov rax,[rip] -> cell S = {s_pre:#x} (PE 値 {show_val(s_pre)})")
    print(f"  後段 {post.address:#x} mov rax,[rip] -> cell S = {s_post:#x} (同じ cell: {s_pre == s_post})")
    for name, va in (("前提", 0xD5AF58), ("後段", 0xD82C7E)):
        c = insns(va, 1)[0]
        print(f"  {name} {c.address:#x} {c.mnemonic} {c.op_str}")
    print("  連鎖 (前提・後段とも同じ): X1=[S] -> X2=[X1] -> O=[X2+8] -> vt=[O] -> call [vt+slot]")
    print(f"  X1 = [S] の PE 値 = {show_val(s_pre)}。X2 = [X1] は実行時に 0x976aad で埋まる (下の 3)")

    print("== 2. O (X2+8) の生成箇所とクラス参照")
    for va in (0x1263559, 0x126412D):
        ins = insns(va, 1)[0]
        cref = rip_target(ins)
        print(f"  {va:#x} mov rcx,[rip] -> class ref global {cref:#x} (PE 値 {show_val(cref)})")
    vmt = qword(0x125B0F8)
    print(f"  VMT = {vmt:#x} (生成は 0x410320 -> [VMT-0x30]=0x40f960 -> 0x40fb66 `mov [rsi],rdi` で vptr = VMT)")
    name = RAW[fo(vmt + 0xE6):fo(vmt + 0xE6) + 15]
    print(f"  VMT+0xe6 の短文字列 = {name[1:1 + name[0]]!r} (長さ {name[0]})")
    print(f"  VMT-0x80 (instance size) = {struct.unpack('<I', RAW[fo(vmt - 0x80):fo(vmt - 0x80) + 4])[0]:#x}")

    print("== 3. VMT のスロット (前提 +0x98・後段 +0x88・共通の判定 +0x48)")
    for slot in (0x48, 0x88, 0x98):
        print(f"  VMT+{slot:#x} = {qword(vmt + slot):#x}")

    print("== 4. 逆アセンブル (RIP 先の値付き)")
    for label, va, n in (("+0x48 (Z の読み)", qword(vmt + 0x48), 3),
                         ("+0x88 後段 (= !F1 && !F2 && !vt48)", qword(vmt + 0x88), 22),
                         ("+0x98 前提 (= 後段 && D+0x168 <= 0)", qword(vmt + 0x98), 22)):
        print(f"  -- {label} @ {va:#x}")
        disasm_annot(va, n)

    print("== 5. 選択フラグのバイト書込み (セル読込み直後の同一レジスタへの store)")
    cells = {"F1": 0x15E04A8, "F2": 0x15E0FF0, "Z": 0x15E1890}
    tgt_name = {v: k for k, v in cells.items()}
    print(f"  セル: F1={show_val(0x15E04A8)} F2={show_val(0x15E0FF0)} Z={show_val(0x15E1890)} (PE 値。指す先は bss/.text)")
    t0 = time.time()
    n_ins = 0
    found = []
    for s in PEF.sections:
        if not s.Characteristics & 0x20000000:
            continue
        start = BASE + s.VirtualAddress
        data = RAW[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
        off = 0
        while off < len(data):
            end = off
            ins_list = []
            for ins in MD.disasm(data[off:off + CHUNK + 16], start + off):
                if ins.address - start - off + ins.size > CHUNK:
                    break
                n_ins += 1
                end = ins.address - start + ins.size
                ins_list.append(ins)
            for i, ins in enumerate(ins_list):
                if ins.mnemonic == "mov" and len(ins.operands) == 2 and ins.operands[1].type == capstone.x86.X86_OP_MEM \
                        and ins.operands[1].mem.base == RIP:
                    t = ins.address + ins.size + ins.operands[1].mem.disp
                    if t not in tgt_name or ins.operands[0].type != capstone.x86.X86_OP_REG:
                        continue
                    reg = ins.reg_name(ins.operands[0].reg)
                    for y in ins_list[i + 1:i + 6]:
                        if y.mnemonic in ("call", "jmp") or y.mnemonic.startswith("j"):
                            break
                        if y.mnemonic == "mov" and y.op_str.startswith(f"byte ptr [{reg}], "):
                            row = (tgt_name[t], y.address, y.op_str)
                            if row not in found:
                                found.append(row)
                            break
            off = end if end > off else off + 1
    for k in cells:
        rows = [f for f in found if f[0] == k]
        print(f"  {k}: store {len(rows)} 件")
        for _, a, op in rows:
            print(f"    {a:#x} {op}")
    print(f"  走査 instructions={n_ins} sec={time.time() - t0:.1f}")
    print("  注: 1 レジスタ・直後 5 命令の型に限る。別レジスタへ写した後の書込みは拾わない。Z の setter は VMT+0x60 (0x1262970) にもある。")


if __name__ == "__main__":
    main()
