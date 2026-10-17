#!/usr/bin/env python3
"""selectOneChannel の前提ゲートの D (cell 0x15F7190) の参照箇所と [reg+0x168] への書込み候補 (幅別) を PE から列挙する (PY-82 子 #6015)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/py69_d_origin.py

- (1) cell 0x15F7190 への RIP 相対参照 (store = 代入、load = 読込み) を全 .text から列挙し、前後 6 命令を出す。
- (2) [reg+0x168] への書込み候補 (書込み先がメモリの mov / add / sub / inc / dec 等。幅別に件数を出す) を全 .text から列挙する。
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
X86_OP_IMM = capstone.x86.X86_OP_IMM
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


HELPERS = {0x8683B0: "inc168", 0x868400: "dec168"}  # [reg+0x168] を add / sub する関数 (参照カウント)


def helper_callers():
    """(4) 増減関数 (HELPERS) の呼出し地点ごとに、直前 6 命令内で rcx に入れた値の由来を出す。

    由来: `mov rcx,[C]` (= D) か、`mov rax,[P]` の後の `mov rcx,[rax]` (= [[P]] = D)。どちらも無ければ未確認。
    """
    hist = collections.deque(maxlen=6)  # (addr, op_str, rip 参照先)
    out = []
    for ins in stream():
        if ins.mnemonic == "call" and ins.operands[0].type == X86_OP_IMM and ins.operands[0].imm in HELPERS:
            items = list(hist)
            src = "未確認"
            if any(t == CELL and s.startswith("rcx,") for _, s, t in items):
                src = "[C] (= D)"
            elif any(t == P and s.startswith("rax,") for _, s, t in items) and any(s == "rcx, qword ptr [rax]" for _, s, _ in items):
                src = "[[P]] (= D)"
            out.append((HELPERS[ins.operands[0].imm], ins.address, src))
        hist.append((ins.address, ins.op_str, rip_target(ins)))
    print("== 4. [reg+0x168] の増減関数 (0x8683b0 inc / 0x868400 dec) の呼出し地点と rcx の由来")
    for name, addr, src in out:
        print(f"  {name} call@{addr:#x} rcx = {src}")


def provenance():
    """(5) [reg+0x168] 直接書込みの基底レジスタの由来を線形追跡する (関数内・call で由来を消す近似)。

    状態: "CA" = P (C のアドレス) を読んだ値、"D" = [[P]] (= D)。ret で全消去。
    由来が "D" の書込みだけを出す。0 件は「該当なし」の証拠ではない (引数・戻り値を追わない)。
    """
    st = {}
    rows = []
    cnt = collections.Counter()
    for ins in stream():
        m, ops = ins.mnemonic, ins.operands
        if m == "ret":
            st.clear()
            continue
        if m == "call":
            for r in ("rax", "rcx", "rdx", "r8", "r9", "r10", "r11"):
                st.pop(r, None)
            continue
        if ops and ops[0].type == X86_OP_MEM and m in WRITE_MNEM and ops[0].mem.disp == 0x168 and ops[0].mem.index == 0 and ops[0].mem.base:
            k = st.get(ins.reg_name(ops[0].mem.base), "?")
            cnt[k] += 1
            if k == "D":
                rows.append((ins.address, ins.mnemonic, ins.op_str))
        if not ops or ops[0].type != X86_OP_REG:
            continue
        dst = ins.reg_name(ops[0].reg)
        if m == "mov" and len(ops) == 2:
            t = rip_target(ins)
            if ops[1].type == X86_OP_MEM and t == P:
                st[dst] = "CA"
            elif ops[1].type == X86_OP_MEM and t == CELL:
                st[dst] = "D"
            elif ops[1].type == X86_OP_MEM and ops[1].mem.base and ops[1].mem.disp == 0 and ops[1].mem.index == 0 and st.get(ins.reg_name(ops[1].mem.base)) == "CA":
                st[dst] = "D"
            elif ops[1].type == X86_OP_REG and ins.reg_name(ops[1].reg) in st:
                st[dst] = st[ins.reg_name(ops[1].reg)]
            else:
                st.pop(dst, None)
        else:
            st.pop(dst, None)
    print("== 5. [reg+0x168] 直接書込みの基底の由来 (線形追跡・近似)")
    print(f"  由来別件数 = {dict(cnt)}")
    print(f"  由来 D と判定 = {len(rows)} 件")
    for addr, m, o in rows:
        print(f"  {addr:#x} {m} {o}")


def main():
    helper_callers()
    provenance()
    v = fo(CELL)
    print(f"== 1. cell {CELL:#x} への RIP 相対参照 (全 .text)")
    print("  cell の PE 値 = " + ("bss(runtime)" if v is None else f"{int.from_bytes(RAW[v:v+8], 'little'):#x}"))

    before = collections.deque(maxlen=40)  # 直前 40 命令 (addr, cell を読んだ dst レジスタ, 表示文字列)
    pending = []  # (ref 行, 残りの後続命令数)
    refs = []
    cands = []
    n = 0
    nP = 0
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

        if rip_target(ins) == P:
            nP += 1
        if ins.mnemonic in WRITE_MNEM and ins.operands[0].type == X86_OP_MEM:
            mem = ins.operands[0].mem
            if mem.disp == 0x168 and mem.index == 0 and mem.base != 0:
                base = ins.reg_name(mem.base)
                near = None
                for y in reversed(before):
                    if y[1] == base:
                        near = y[0]
                        break
                cands.append((ins.address, fmt(ins), near, ins.operands[0].size))
        # 直前の参照 (cell 読込み) を覚えておく: (addr, dst reg)
        dst = None
        if ins.mnemonic == "mov" and ins.operands[0].type == X86_OP_REG and rip_target(ins) == P:
            dst = ins.reg_name(ins.operands[0].reg)
        before.append((ins.address, dst, fmt(ins)))

    print(f"  走査 instructions={n}")
    print(f"  P ({P:#x}) を RIP 相対で参照する命令 = {nP}")
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
    print("== 3. [reg+0x168] への書込み (幅別・全 .text)")
    print(f"  件数 = {len(cands)}")
    width = collections.Counter(c[3] for c in cands)
    for size in sorted(width):
        print(f"  幅 {size} byte = {width[size]}")
    for addr, line, near, _ in cands:
        tag = f"  <- 同基底の cell 読込み {near:#x}" if near is not None else ""
        print(f"  {line}{tag}")


if __name__ == "__main__":
    main()
