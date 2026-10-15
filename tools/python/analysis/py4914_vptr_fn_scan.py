#!/usr/bin/env python3
"""PY-4914 (#5348): vptr 候補 0xed0bb0 (表 A) を、関数単位で『vptr として格納する』経路の有無を数える (block00031)。

  FL_WIN64_DIR=<展開先> python3 analysis/py4914_vptr_fn_scan.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
検査 (関数先頭は .pdata から取る。線形走査で、レジスタ・スタック slot の定数値を追う):
  - 源: lea (rip / 定数レジスタ + disp)・mov imm・mov reg・add/sub imm/reg・push/pop・
        rip 相対の qword 読出し (読出し値は PE の実バイト)・rsp/rbp 相対 slot への格納と読出し。
  - 格納: 8 byte の mov [mem], reg/imm で、値が候補と一致するもの (vptr の書込み)。
  - 呼出し (call): Win64 の揮発レジスタ (rax,rcx,rdx,r8-r11) と全 slot を捨てる。
  - 関数先頭・分岐先 (ラベル): 値と slot を捨てる (合流の値は追わない)。
陽性対照: 候補 0x13acb88 (vtable 格納 0x44a86e) は検出されなければならない。
出力: 関数ごとの『候補値を生成した箇所』と『候補値の qword 格納』。
限界: メモリ経由の別名 (ポインタ経由の stack 書換え)・関数をまたぐ値 (呼出し先の戻り値は追わない)・
  分岐合流の値は追わない。格納 0 件は、この規則の範囲で 0 件という意味。
期待値と異なれば rc 1 (格納 1 件以上・陽性対照の不検出は rc 2)。
"""
import bisect
import collections
import os
import struct
import sys
import time

import capstone
import pefile

EXT = os.path.join(os.environ["FL_WIN64_DIR"], "extracted")
MAIN = os.path.join(EXT, "block00031_PE.bin")
MASK = (1 << 64) - 1
X86 = capstone.x86
CHUNK = 1 << 16
TARGET_A = 0xED0BB0
TARGET_B = 0xED0C28
CONTROL = 0x13ACB88
CAND = {TARGET_A: "A 0xed0bb0", TARGET_B: "B 0xed0c28", CONTROL: "control 0x13acb88"}
VOLATILE = ("rax", "rcx", "rdx", "r8", "r9", "r10", "r11")

ALIAS = {}
for full, subs in {
    "rax": ("eax", "ax", "al", "ah"), "rbx": ("ebx", "bx", "bl", "bh"),
    "rcx": ("ecx", "cx", "cl", "ch"), "rdx": ("edx", "dx", "dl", "dh"),
    "rsi": ("esi", "si", "sil"), "rdi": ("edi", "di", "dil"),
    "rbp": ("ebp", "bp", "bpl"), "rsp": ("esp", "sp", "spl"),
}.items():
    ALIAS[full] = full
    for s in subs:
        ALIAS[s] = full
for i in range(8, 16):
    ALIAS["r%d" % i] = "r%d" % i
    for s in ("d", "w", "b"):
        ALIAS["r%d%s" % (i, s)] = "r%d" % i


def fam(name):
    return ALIAS.get(name, name)


def text_insns(md, pe, raw):
    base = pe.OPTIONAL_HEADER.ImageBase
    t = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
    start = base + t.VirtualAddress
    n = min(t.Misc_VirtualSize, t.SizeOfRawData)
    data = raw[t.PointerToRawData:t.PointerToRawData + n]
    off = 0
    while off < n:
        end = off
        for ins in md.disasm(data[off:off + CHUNK + 16], start + off):
            if ins.address - start - off + ins.size > CHUNK:
                break
            yield ins
            end = ins.address - start + ins.size
        off = end if end > off else off + 1


def make_reader(pe, raw):
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = []
    for s in pe.sections:
        lo = base + s.VirtualAddress
        secs.append((lo, lo + max(s.Misc_VirtualSize, s.SizeOfRawData), s.PointerToRawData, s.SizeOfRawData))

    def read_qword(va):
        for lo, hi, po, rs in secs:
            if lo <= va and va + 8 <= hi:
                off = va - lo
                if off + 8 > rs:
                    return None
                return struct.unpack_from("<Q", raw, po + off)[0]
        return None

    return read_qword


def fn_starts(pe, raw):
    base = pe.OPTIONAL_HEADER.ImageBase
    p = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".pdata")
    data = raw[p.PointerToRawData:p.PointerToRawData + p.SizeOfRawData]
    starts = set()
    for i in range(0, len(data) - 11, 12):
        b, _e, _u = struct.unpack_from("<III", data, i)
        if b:
            starts.add(base + b)
    return sorted(starts)


def scan(pe, raw, md):
    base = pe.OPTIONAL_HEADER.ImageBase
    t = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
    tlo = base + t.VirtualAddress
    thi = tlo + max(t.Misc_VirtualSize, t.SizeOfRawData)
    read_qword = make_reader(pe, raw)
    starts = fn_starts(pe, raw)
    fn_set = set(starts)

    labels = set()
    for ins in text_insns(md, pe, raw):
        if ins.mnemonic.startswith("j") and ins.operands and ins.operands[0].type == X86.X86_OP_IMM:
            tgt = ins.operands[0].imm & MASK
            if tlo <= tgt < thi:
                labels.add(tgt)

    val, slots = {}, {}
    sp = 0
    bp_keys_ok = True
    cur_fn = None
    stores, produced = [], []
    n_ins = 0

    def kill_slots(key, size=8):
        for k in [k for k in slots if k[0] == key[0] and abs(k[1] - key[1]) < size + 8]:
            del slots[k]

    def mem_key(ins, mem):
        if mem.index != 0 or mem.base == 0 or mem.base == X86.X86_REG_RIP:
            return None
        b = fam(ins.reg_name(mem.base))
        if b == "rsp" and sp is not None:
            return ("sp", sp + mem.disp)
        if b == "rbp" and bp_keys_ok:
            return ("bp", mem.disp)
        return None

    for ins in text_insns(md, pe, raw):
        n_ins += 1
        a = ins.address
        if a in fn_set:
            cur_fn = a
            val.clear()
            slots.clear()
            sp = 0
            bp_keys_ok = True
        elif a in labels:
            val.clear()
            slots.clear()
        ops = ins.operands
        m = ins.mnemonic
        size_ok = lambda o: o.size == 8

        if m.startswith("call"):
            for r in VOLATILE:
                val.pop(r, None)
            slots.clear()
            continue
        if m.startswith("ret") or m == "jmp":
            val.clear()
            slots.clear()
            continue
        if m.startswith("j"):
            continue
        if m == "push" and ops and ops[0].type == X86.X86_OP_REG and sp is not None:
            v = val.get(fam(ins.reg_name(ops[0].reg)))
            sp -= 8
            kill_slots(("sp", sp))
            if v is not None:
                slots[("sp", sp)] = v
            continue
        if m == "pop" and ops and ops[0].type == X86.X86_OP_REG and sp is not None:
            v = slots.get(("sp", sp))
            sp += 8
            d = fam(ins.reg_name(ops[0].reg))
            val.pop(d, None)
            if v is not None and ins.reg_name(ops[0].reg) == d:
                val[d] = v
                produced.append((cur_fn, a, "%s %s" % (m, ins.op_str), v))
            continue

        if m in ("mov", "movabs") and len(ops) == 2 and ops[0].type == X86.X86_OP_MEM:
            mem = ops[0].mem
            v = None
            if ops[1].type == X86.X86_OP_REG and size_ok(ops[0]):
                rn = ins.reg_name(ops[1].reg)
                if rn == fam(rn):
                    v = val.get(rn)
            elif ops[1].type == X86.X86_OP_IMM and size_ok(ops[0]):
                v = ops[1].imm & MASK
            if v is not None and v in CAND and size_ok(ops[0]):
                stores.append((cur_fn, a, "mov %s, %s" % (ins.op_str.split(",")[0], ins.op_str.split(",", 1)[1].strip()), v))
            key = mem_key(ins, mem)
            if key is not None:
                kill_slots(key, ops[0].size)
                if v is None:
                    slots.pop(key, None)
                else:
                    slots[key] = v
            continue

        if ops and ops[0].type == X86.X86_OP_MEM:
            key = mem_key(ins, ops[0].mem)
            if key is not None:
                kill_slots(key, ops[0].size)
            elif ops[0].mem.base != 0 and ops[0].mem.base != X86.X86_REG_RIP:
                bn = fam(ins.reg_name(ops[0].mem.base))
                if bn == "rbp":
                    bp_keys_ok = False
                    for k in [k for k in slots if k[0] == "bp"]:
                        del slots[k]
            continue

        newv = None
        dst = None
        if ops and ops[0].type == X86.X86_OP_REG:
            dst = ins.reg_name(ops[0].reg)
        if dst is not None and len(ops) == 2 and fam(dst) == dst:
            s = ops[1]
            if m == "lea" and s.type == X86.X86_OP_MEM:
                mem = s.mem
                if mem.base == X86.X86_REG_RIP and mem.index == 0:
                    newv = (a + ins.size + mem.disp) & MASK
                elif mem.index == 0 and mem.base != 0 and fam(ins.reg_name(mem.base)) in val:
                    newv = (val[fam(ins.reg_name(mem.base))] + mem.disp) & MASK
            elif m in ("mov", "movabs") and s.type == X86.X86_OP_IMM:
                newv = s.imm & MASK
            elif m in ("mov", "movabs") and s.type == X86.X86_OP_REG and fam(ins.reg_name(s.reg)) != ins.reg_name(s.reg):
                newv = None
            elif m in ("mov", "movabs") and s.type == X86.X86_OP_REG:
                newv = val.get(ins.reg_name(s.reg))
            elif m == "mov" and s.type == X86.X86_OP_MEM and s.size == 8:
                mem = s.mem
                if mem.base == X86.X86_REG_RIP and mem.index == 0:
                    newv = read_qword(a + ins.size + mem.disp)
                else:
                    key = mem_key(ins, mem)
                    if key is not None:
                        newv = slots.get(key)
            elif m in ("add", "sub") and s.type == X86.X86_OP_IMM and dst in val:
                newv = (val[dst] + (s.imm if m == "add" else -s.imm)) & MASK
            elif m in ("add", "sub") and s.type == X86.X86_OP_REG and dst in val:
                sn = ins.reg_name(s.reg)
                if sn == fam(sn) and sn in val:
                    newv = (val[dst] + (val[sn] if m == "add" else -val[sn])) & MASK
        elif dst is not None and m == "mov" and len(ops) == 2 and ops[1].type == X86.X86_OP_IMM:
            newv = ops[1].imm & 0xFFFFFFFF
            dst = fam(dst)

        new_sp = sp
        for r in ins.regs_write:
            rn = ins.reg_name(r)
            f = fam(rn)
            if f == "rsp":
                if m in ("add", "sub") and ops and len(ops) == 2 and ops[1].type == X86.X86_OP_IMM and sp is not None:
                    new_sp = sp + (ops[1].imm if m == "add" else -ops[1].imm)
                else:
                    new_sp = None
                continue
            if f == "rbp" and bp_keys_ok:
                bp_keys_ok = False
                for k in [k for k in slots if k[0] == "bp"]:
                    del slots[k]
            val.pop(f, None)
        if new_sp is None:
            sp = None
            for k in [k for k in slots if k[0] == "sp"]:
                del slots[k]
        else:
            sp = new_sp
        if dst is not None and newv is not None:
            fd = fam(dst)
            val[fd] = newv
            if newv in CAND:
                produced.append((cur_fn, a, "%s %s" % (m, ins.op_str), newv))
    return n_ins, stores, produced, len(starts)


def main():
    t0 = time.time()
    raw = open(MAIN, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    n_ins, stores, produced, n_fn = scan(pe, raw, md)
    sec = time.time() - t0
    print("block00031 insns=%d pdata_functions=%d sec=%.1f" % (n_ins, n_fn, sec))
    by_fn = collections.defaultdict(lambda: collections.Counter())
    for fn, a, op, v in produced:
        by_fn[(v, fn)][a] += 1
    for v in (TARGET_A, TARGET_B, CONTROL):
        fns = sorted({fn for vv, fn in by_fn if vv == v}, key=lambda x: x or 0)
        n_prod = sum(1 for p in produced if p[3] == v)
        n_store = sum(1 for s in stores if s[3] == v)
        print("%s: produced_insns=%d in_functions=%d qword_stores=%d" % (CAND[v], n_prod, len(fns), n_store))
        for fn in fns:
            print("  produced in fn 0x%x: %s" % (fn or 0, ", ".join("0x%x" % x for x in sorted(by_fn[(v, fn)]))))
    for fn, a, op, v in stores:
        print("STORE %s at 0x%x in fn 0x%x: %s" % (CAND[v], a, fn or 0, op))
    ctrl = [s for s in stores if s[3] == CONTROL and s[1] == 0x44A86E]
    a_stores = [s for s in stores if s[3] == TARGET_A]
    if not ctrl:
        print("control FAIL: 0x44a86e の vtable 格納を検出できない")
        return 2
    print("control PASS: 0x44a86e で検出 (%d 件)" % len(ctrl))
    print("A qword stores=%d" % len(a_stores))
    return 0 if not a_stores else 1


if __name__ == "__main__":
    sys.exit(main())
