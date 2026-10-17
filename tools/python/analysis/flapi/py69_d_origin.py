#!/usr/bin/env python3
"""selectOneChannel の前提ゲートの D (cell 0x15F7190) の参照箇所と dword [reg+0x168] の書込み候補を PE から列挙する (PY-82 子 #6015)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/py69_d_origin.py

- (1) cell 0x15F7190 への RIP 相対参照 (store = 代入、load = 読込み) を全 .text から列挙し、前後 6 命令を出す。
- (2) dword [reg+0x168] への書込み候補 (mov store / add / sub / inc / dec) を全 .text から列挙する。
  直前 40 命令内に、同じ基底レジスタへ P (0x15E30F8) を読んでいる命令 (= D の読込み) があれば印を付ける。
- 限界: (2) の由来は「直前 40 命令内で同じレジスタに cell を読んだ」型に限る。関数をまたぐ・ヒープ経由の D は拾わない。
  同定できない書込みは「未確認」とする。
- メモリ: 命令を全件保持せず、流しながら処理する (全 .text で約 500 万命令)。
"""
import collections
import os

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
RAW = open(PE, "rb").read()
PEF = pefile.PE(data=RAW, fast_load=True)
BASE = PEF.OPTIONAL_HEADER.ImageBase
MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
MD.detail = True
RIP = capstone.x86.X86_REG_RIP
CELL = 0x15F7190  # bss。D の実体ポインタ先 (直接の load/store は無い)
P = 0x15E30F8  # .data。PE 値 = CELL。前提ゲートは [[P]+0x168] を見る
CHUNK = 1 << 16
X86_OP_MEM = capstone.x86.X86_OP_MEM
X86_OP_REG = capstone.x86.X86_OP_REG
WRITE_MNEM = ("mov", "add", "sub", "inc", "dec", "and", "or", "xor")


def fo(va):
    rva = va - BASE
    for s in PEF.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            off = rva - s.VirtualAddress
            return None if off >= s.SizeOfRawData else s.PointerToRawData + off
    return None


def stream():
    """全 .text の命令を 1 つずつ返す (保持しない)。"""
    for s in PEF.sections:
        if not s.Characteristics & 0x20000000:
            continue
        start = BASE + s.VirtualAddress
        data = RAW[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
        off = 0
        while off < len(data):
            end = off
            batch = []
            for ins in MD.disasm(data[off:off + CHUNK + 16], start + off):
                if ins.address - start - off + ins.size > CHUNK:
                    break
                end = ins.address - start + ins.size
                batch.append(ins)
            yield from batch
            off = end if end > off else off + 1


def rip_target(ins):
    for op in ins.operands:
        if op.type == X86_OP_MEM and op.mem.base == RIP:
            return ins.address + ins.size + op.mem.disp
    return None


def fmt(ins):
    return f"{ins.address:#x} {ins.mnemonic} {ins.op_str}"


def main():
    v = fo(CELL)
    print(f"== 1. cell {CELL:#x} への RIP 相対参照 (全 .text)")
    print("  cell の PE 値 = " + ("bss(runtime)" if v is None else f"{int.from_bytes(RAW[v:v+8], 'little'):#x}"))

    before = collections.deque(maxlen=40)  # 直前 40 命令 (addr, cell を読んだ dst レジスタ, 表示文字列)
    pending = []  # (ref 行, 残りの後続命令数)
    refs = []
    cands = []
    n = 0
    for ins in stream():
        n += 1
        # 後続 6 命令の文脈を溜める
        for p in pending:
            p[1].append(fmt(ins))
            p[2] -= 1
        pending = [p for p in pending if p[2] > 0]

        t = rip_target(ins)
        if t == CELL:
            kind = "store" if ins.mnemonic == "mov" and ins.operands[0].type == X86_OP_MEM else "load"
            ctx = [x[2] for x in list(before)[-6:]]
            rec = [ins.address, kind, fmt(ins), ctx, [], 6]
            refs.append(rec)
            pending.append([None, rec[4], 6])

        if ins.mnemonic in WRITE_MNEM:
            mem = next((op for op in ins.operands if op.type == X86_OP_MEM), None)
            if mem is not None and mem.mem.disp == 0x168 and mem.mem.index == 0 and mem.mem.base != 0:
                if not (ins.mnemonic == "mov" and ins.operands[0].type != X86_OP_MEM):
                    base = ins.reg_name(mem.mem.base)
                    near = None
                    for y in reversed(before):
                        if y[1] == base:
                            near = y[0]
                            break
                    cands.append((ins.address, fmt(ins), near))
        # 直前の参照 (cell 読込み) を覚えておく: (addr, dst reg)
        dst = None
        if ins.mnemonic == "mov" and ins.operands[0].type == X86_OP_REG and rip_target(ins) == P:
            dst = ins.reg_name(ins.operands[0].reg)
        before.append((ins.address, dst, fmt(ins)))

    print(f"  走査 instructions={n}")
    for addr, kind, line, ctx, post, _ in refs:
        print(f"  [{kind}] {line}")
    print("== 2. 各参照の前後 6 命令 (>> が参照命令)")
    for addr, kind, line, ctx, post, _ in refs:
        print(f"  -- {addr:#x} [{kind}]")
        for c in ctx:
            print(f"       {c}")
        print(f"    >> {line}")
        for c in post:
            print(f"       {c}")
    print("== 3. dword [reg+0x168] への書込み候補 (全 .text)")
    print(f"  件数 = {len(cands)}")
    for addr, line, near in cands:
        tag = f"  <- 同基底の cell 読込み {near:#x}" if near is not None else ""
        print(f"  {line}{tag}")


if __name__ == "__main__":
    main()
