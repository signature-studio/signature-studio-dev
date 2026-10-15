#!/usr/bin/env python3
"""FLEngine PE (block00031_PE.bin) の大域 K (0x16bacf0) への書込み経路を検査する (PY-199 / #3443 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_k_struct_probe.py [深さ(既定 2)]

検査 (書込みの判定は capstone の access 情報。mov 以外の add・xchg・cmpxchg 等も書込みとして数える):
  1. .text 全体の線形走査で、RIP 相対・絶対 disp32 のメモリオペランドが領域 [LO, HI) に当たる命令を列挙する。
     K (4 byte) を覆う書込みは direct_K_writes として数える。
  2. 領域を指す lea (RIP 相対・絶対) と、領域の絶対アドレスの即値 mov を根とし、その直後 WINDOW 命令を
     レジスタの別名追跡で走査する。別名レジスタ経由のメモリアクセスを絶対アドレスに直し、K を覆うものを数える。
  3. 別名が rcx/rdx/r8/r9 で渡る direct call の先を、深さ DEPTH まで同じ方式で追う。
  4. 別名を格納する命令 (`mov [mem], 別名`) と、別名を宛先とする rep movs/stos・memcpy/memmove/memset の
     呼出しを列挙する (bulk copy の宛先が領域かどうか)。
  5. 正の対照: V (0x16bacec) への書込み 3 件 (0xf82b80・0xf82c55・0xf82c5f) と K の読み 2 件 (0xf82a43・0xf82c48) を検出できること。

限界: 別名は同一関数内 (と深さ内の direct call 先) でだけ追う。別名をメモリへ格納した先での再ロードは追わない
(格納の列挙 (4) で所在を示す)。間接 call の先は追わない。
"""
import collections
import os
import sys
import time

import capstone
import numpy as np
import pefile
from capstone import CS_AC_WRITE
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_RIP

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
K = 0x16BACF0
V = 0x16BACEC
LO, HI = 0x16BAAF0, 0x16BAD20
WINDOW = 400
ARGS = ("rcx", "rdx", "r8", "r9")
CALLER = ("rax", "rcx", "rdx", "r8", "r9", "r10", "r11")
MASK = (1 << 64) - 1


def _reg_map():
    m = {}
    for n in ("rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rbp", "rsp"):
        m[n] = n
        m["e" + n[1:]] = n
    for b in "abcd":
        m[b + "l"] = m[b + "h"] = m[b + "x"] = "r" + b + "x"
    for s in ("si", "di", "bp", "sp"):
        m[s] = m[s + "l"] = "r" + s
    for i in range(8, 16):
        for suf in ("", "d", "w", "b"):
            m["r%d%s" % (i, suf)] = "r%d" % i
    return m


REG64 = _reg_map()


def r64(md, reg):
    if not reg:
        return None
    return REG64.get(md.reg_name(reg))


CHUNK = 1 << 20


def byte_refs(raw, secs, base, lo, hi, md):
    out = []
    for s in secs:
        if not s.Characteristics & 0x20000000:
            continue
        data = raw[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
        n = len(data) - 3
        if n <= 0:
            continue
        view = np.ndarray(shape=(n,), dtype="<i4", buffer=data, offset=0, strides=(1,)).astype(np.int64)
        va = base + s.VirtualAddress + np.arange(n, dtype=np.int64)
        for imm in (0, 1, 2, 4, 8):
            tgt = va + 4 + imm + view
            for p in np.nonzero((tgt >= lo) & (tgt < hi))[0]:
                out.append((int(va[p]), imm, int(tgt[p]), "rip"))
        for p in np.nonzero((view >= lo) & (view < hi))[0]:
            out.append((int(va[p]), 0, int(view[p]), "abs"))
    verified = {}
    for p, imm, tgt, kind in out:
        for st in range(p - 14, p - 1):
            if (p, tgt) in verified:
                break
            code = raw_at(raw, secs, base, st, 16)
            for ins in md.disasm(code, st):
                if ins.address + ins.size == p + 4 + imm:
                    for op in ins.operands:
                        if op.type != X86_OP_MEM:
                            continue
                        if kind == "rip" and op.mem.base == X86_REG_RIP and ins.address + ins.size + op.mem.disp == tgt:
                            verified[(p, tgt)] = (ins.address, ins.mnemonic, ins.op_str, bool(op.access & CS_AC_WRITE))
                        if kind == "abs" and op.mem.base == 0 and op.mem.index == 0 and op.mem.disp == tgt:
                            verified[(p, tgt)] = (ins.address, ins.mnemonic, ins.op_str, bool(op.access & CS_AC_WRITE))
                break
    return out, verified


def raw_at(raw, secs, base, va, n):
    rva = va - base
    for s in secs:
        if s.VirtualAddress <= rva < s.VirtualAddress + s.SizeOfRawData:
            off = s.PointerToRawData + rva - s.VirtualAddress
            return raw[off:off + n]
    return b""


def is_copy(name):
    return any(k in name.lower() for k in ("memcpy", "memmove", "memset"))


def frame_reg(raw, secs, base, va):
    pd = [s for s in secs if s.Name.rstrip(b"\0") == b".pdata"]
    n = pd[0].Misc_VirtualSize // 12
    ent = np.frombuffer(raw[pd[0].PointerToRawData:pd[0].PointerToRawData + 12 * n], dtype="<u4").reshape(n, 3)
    rva = va - base
    i = int(np.searchsorted(ent[:, 0], rva, side="right")) - 1
    if i < 0 or not ent[i, 0] <= rva < ent[i, 1]:
        return None
    fr = raw_at(raw, secs, base, base + int(ent[i, 2]), 4)[3] & 0xF
    return {0: "none", 4: "rsp", 5: "rbp"}.get(fr, str(fr))


def main():
    depth_max = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    t0 = time.time()
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = list(pe.sections)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True

    iat = {}
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
        for ent in pe.DIRECTORY_ENTRY_IMPORT:
            for imp in ent.imports:
                if imp.name:
                    iat[imp.address] = imp.name.decode()

    def read_va(va, n):
        rva = va - base
        for s in secs:
            if s.VirtualAddress <= rva < s.VirtualAddress + s.SizeOfRawData:
                off = s.PointerToRawData + rva - s.VirtualAddress
                return raw[off:off + n]
        return b""

    def target_of(ins, op):
        m = op.mem
        if m.base == X86_REG_RIP:
            return (ins.address + ins.size + m.disp) & MASK
        if m.base == 0 and m.index == 0:
            return m.disp & MASK
        return None

    direct = []
    lea_roots = []
    imm_roots = []
    rep_sites = []
    iat_sites = []
    thunks = {}
    call_imm = []
    n_ins = 0
    resync = 0
    for s in secs:
        if not s.Characteristics & 0x20000000:
            continue
        start = base + s.VirtualAddress
        data = raw[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
        off = 0
        while off < len(data):
            sl = data[off:off + CHUNK]
            o_start = off
            for ins in md.disasm(sl, start + off):
                off = ins.address - start + ins.size
                n_ins += 1
                mn = ins.mnemonic
                ops = ins.operands
                for op in ops:
                    if op.type == X86_OP_MEM:
                        tgt = target_of(ins, op)
                        if tgt is None:
                            continue
                        if tgt in iat:
                            iat_sites.append((ins.address, mn, iat[tgt]))
                            if mn == "jmp" and len(ops) == 1:
                                thunks[ins.address] = iat[tgt]
                        if mn == "lea" and LO <= tgt < HI:
                            lea_roots.append((ins.address, r64(md, ops[0].reg), tgt))
                        elif LO <= tgt < HI and mn != "lea":
                            direct.append((ins.address, mn, ins.op_str, bool(op.access & CS_AC_WRITE), tgt, op.size))
                    elif op.type == X86_OP_IMM and mn == "mov" and len(ops) == 2 and ops[0].type == X86_OP_REG:
                        v = op.imm & MASK
                        if LO <= v < HI:
                            imm_roots.append((ins.address, r64(md, ops[0].reg), v))
                if mn.startswith("rep ") and ("movs" in mn or "stos" in mn):
                    rep_sites.append((ins.address, mn))
                if mn == "call" and ops and ops[0].type == X86_OP_IMM:
                    direct.append((ins.address, "call", "", False, None, 0))
                    call_imm.append((ins.address, ops[0].imm & MASK))
            # 復号できないバイトで止まった (チャンク末尾でない) なら 1 バイト進めて再同期する
            if off == o_start or off - o_start + 16 < len(sl):
                resync += 1
                off = max(off, o_start) + 1

    print("scan: insns=%d resync=%d sec=%.1f" % (n_ins, resync, time.time() - t0))
    print("imports named=%d thunks (jmp [IAT])=%d" % (len(iat), len(thunks)))
    for a, nm in sorted(thunks.items()):
        if "mem" in nm.lower():
            print("  mem-named thunk 0x%x -> %s" % (a, nm))
    mem_sites = [(a, thunks[t]) for a, t in call_imm if t in thunks and is_copy(thunks[t])]
    mem_sites += [(a, nm) for a, mn, nm in iat_sites if mn == "call" and is_copy(nm)]
    print("memcpy/memmove/memset call sites=%d: %s" % (
        len(mem_sites), ", ".join("0x%x %s" % s for s in sorted(mem_sites))))

    direct_k_w = [d for d in direct if d[4] is not None and d[3] and d[4] <= K < d[4] + d[5]]
    direct_k_r = [d for d in direct if d[4] is not None and not d[3] and d[4] <= K < d[4] + d[5]]
    print("direct region accesses (RIP/absolute): %d" % sum(1 for d in direct if d[4] is not None))
    print("direct_K_writes=%d direct_K_reads=%d" % (len(direct_k_w), len(direct_k_r)))
    for d in direct_k_w:
        print("  K write 0x%x %s %s -> 0x%x" % (d[0], d[1], d[2], d[4]))
    for d in direct_k_r:
        print("  K read 0x%x %s %s -> 0x%x" % (d[0], d[1], d[2], d[4]))
    v_w = [d for d in direct if d[4] is not None and d[3] and d[4] <= V < d[4] + d[5]]
    print("positive control V writes: %s" % ["0x%x" % d[0] for d in v_w])
    print("region lea roots=%d imm roots=%d rep string sites=%d iat/thunk sites=%d"
          % (len(lea_roots), len(imm_roots), len(rep_sites), len(iat_sites)))

    cand, ver = byte_refs(raw, secs, base, LO, HI, md)
    direct_addrs = {d[0] for d in direct if d[4] is not None}
    ver_ins = {v[0] for v in ver.values()}
    print("byte-level candidates into region=%d verified=%d" % (len(cand), len(ver)))
    missed = sorted(v for v in ver.values() if v[0] not in direct_addrs)
    print("verified refs not in linear sweep=%d" % len(missed))
    for m in missed[:40]:
        print("  missed 0x%x %s %s w=%s" % m)
    kv = sorted((k, v) for k, v in ver.items() if k[1] <= K < k[1] + 4)
    print("verified refs covering K=%d writes=%d" % (len(kv), sum(1 for k, v in kv if v[3])))
    for k, v in kv:
        print("  K ref 0x%x %s %s w=%s" % (v[0], v[1], v[2], v[3]))
    layout = collections.Counter()
    for k, v in ver.items():
        if v[3]:
            layout[k[1]] += 1
    print("region write targets (verified): %s" % ", ".join("0x%x:%d" % (t, c) for t, c in sorted(layout.items())))

    access = []
    indexed = []
    bulk = []
    escapes = []
    stores_ptr = []
    returned = []
    seen = set()

    def track(start_va, alias, depth, origin):
        key = (start_va, tuple(sorted(alias.items())))
        if key in seen:
            return
        seen.add(key)
        code = read_va(start_va, WINDOW * 15)
        n = 0
        for ins in md.disasm(code, start_va):
            n += 1
            if n > WINDOW:
                break
            mn = ins.mnemonic
            ops = ins.operands
            if mn == "lea":
                pass
            else:
                for op in ops:
                    if op.type != X86_OP_MEM:
                        continue
                    b = r64(md, op.mem.base)
                    ix = r64(md, op.mem.index)
                    if op.mem.base == X86_REG_RIP:
                        continue
                    if b in alias and op.mem.index == 0:
                        eff = (alias[b] + op.mem.disp) & MASK
                        access.append((origin, ins.address, mn, ins.op_str, eff, bool(op.access & CS_AC_WRITE), op.size))
                    elif (b in alias or ix in alias):
                        indexed.append((origin, ins.address, mn, ins.op_str))
            if mn.startswith("rep ") and ("movs" in mn or "stos" in mn):
                if "rdi" in alias:
                    bulk.append((origin, ins.address, mn, alias["rdi"]))
            if mn == "call":
                tgt = None
                name = None
                if ops and ops[0].type == X86_OP_IMM:
                    tgt = ops[0].imm & MASK
                    name = thunks.get(tgt)
                elif ops and ops[0].type == X86_OP_MEM:
                    t = target_of(ins, ops[0])
                    name = iat.get(t)
                args = {a: alias[a] for a in ARGS if a in alias}
                if name and is_copy(name):
                    if "rcx" in alias:
                        bulk.append((origin, ins.address, name, alias["rcx"]))
                if args:
                    escapes.append((origin, ins.address, ins.op_str, tgt, name, args))
                    if tgt is not None and depth < depth_max and tgt not in thunks:
                        track(tgt, args, depth + 1, origin)
                for r in CALLER:
                    alias.pop(r, None)
                continue
            if mn in ("ret", "retn"):
                if "rax" in alias:
                    returned.append((origin, ins.address, alias["rax"]))
                break
            if mn == "mov" and len(ops) == 2 and ops[0].type == X86_OP_MEM and ops[1].type == X86_OP_REG:
                src = r64(md, ops[1].reg)
                if src in alias:
                    stores_ptr.append((origin, ins.address, ins.op_str, alias[src]))
            new = {}
            dst = None
            if ops and ops[0].type == X86_OP_REG and ops[0].size == 8:
                dst = r64(md, ops[0].reg)
                if mn == "mov" and len(ops) == 2 and ops[1].type == X86_OP_REG and ops[1].size == 8:
                    s2 = r64(md, ops[1].reg)
                    if s2 in alias:
                        new[dst] = alias[s2]
                elif mn == "mov" and len(ops) == 2 and ops[1].type == X86_OP_IMM:
                    new[dst] = ops[1].imm & MASK
                elif mn == "lea" and len(ops) == 2 and ops[1].type == X86_OP_MEM and ops[1].mem.index == 0:
                    m = ops[1].mem
                    if m.base == X86_REG_RIP:
                        new[dst] = (ins.address + ins.size + m.disp) & MASK
                    elif m.base == 0:
                        new[dst] = m.disp & MASK
                    else:
                        b = r64(md, m.base)
                        if b in alias:
                            new[dst] = (alias[b] + m.disp) & MASK
                elif mn in ("add", "sub") and len(ops) == 2 and ops[1].type == X86_OP_IMM and dst in alias:
                    d = ops[1].imm if mn == "add" else -ops[1].imm
                    new[dst] = (alias[dst] + d) & MASK
            writes = set()
            for rid in ins.regs_write:
                nm = r64(md, rid)
                if nm:
                    writes.add(nm)
            for op in ops:
                if op.type == X86_OP_REG and op.access & CS_AC_WRITE:
                    nm = r64(md, op.reg)
                    if nm:
                        writes.add(nm)
            for w in writes:
                alias.pop(w, None)
            for k, v in new.items():
                alias[k] = v

    def next_va(addr):
        for ins in md.disasm(read_va(addr, 15), addr):
            return addr + ins.size
        return addr + 1

    roots = set(lea_roots)
    byte_roots = set()
    for (p, tgt), v in ver.items():
        if v[1] == "lea" and LO <= tgt < HI:
            byte_roots.add((v[0], REG64.get(v[2].split(",")[0].strip()), tgt))
    print("lea roots (linear sweep)=%d; byte-verified lea=%d (start-address offsets are not used)" % (len(roots), len(byte_roots)))
    for addr, dst, tgt in sorted(roots, key=lambda r: (r[2], r[0])):
        if dst:
            track(next_va(addr), {dst: tgt}, 0, ("lea", addr, dst, tgt))
    for addr, dst, v in imm_roots:
        if dst:
            track(next_va(addr), {dst: v}, 0, ("imm", addr, dst, v))

    def covers_k(eff, size):
        return eff <= K < eff + size

    k_access = [a for a in access if covers_k(a[4], a[6])]
    k_w = [a for a in k_access if a[5]]
    k_r = [a for a in k_access if not a[5]]
    print("alias accesses=%d K-covering reads=%d K-covering writes=%d" % (len(access), len(k_r), len(k_w)))
    for a in k_w:
        print("  K write origin=%s 0x%x %s %s eff=0x%x" % (a[0][:3], a[1], a[2], a[3], a[4]))
    lo_w = [a for a in access if a[5] and LO <= a[4] < HI]
    print("alias writes into region [0x%x,0x%x)=%d" % (LO, HI, len(lo_w)))
    print("alias indexed accesses=%d" % len(indexed))
    print("bulk (rep string with rdi alias / memcpy-memset with rcx alias)=%d" % len(bulk))
    for b in bulk:
        print("  bulk 0x%x %s dst=0x%x origin=%s" % (b[1], b[2], b[3], b[0][:3]))
    print("escapes (alias passed as arg to call)=%d" % len(escapes))
    print("pointer stores (alias stored to memory)=%d" % len(stores_ptr))
    print("returned pointers (alias in rax at ret)=%d region-valued=%d" % (
        len(returned), sum(1 for r in returned if LO <= r[2] < HI)))
    for r in returned:
        if LO <= r[2] < HI:
            print("  returned 0x%x val=0x%x origin=0x%x" % (r[1], r[2], r[0][1]))
    for sp in stores_ptr:
        print("  ptr store 0x%x [%s] val=0x%x origin=%s" % (sp[1], sp[2], sp[3], sp[0][:3]))
    print("roots covering K region: %s" % sorted({a[0][3] for a in k_access}))
    per = collections.defaultdict(list)
    for a in access:
        per[a[0]].append(a)
    print("root summary (addr dst target: accesses min..max offset from target, writes):")
    for r, acc in sorted(per.items(), key=lambda kv: kv[0][3]):
        offs = [a[4] - r[3] for a in acc]
        w = sum(1 for a in acc if a[5])
        print("  lea 0x%x %s -> 0x%x  n=%d w=%d off=[%+d..%+d] tgt_region=%s" % (
            r[1], r[2], r[3], len(acc), w, min(offs), max(offs), LO <= r[3] < HI))
    for sp in stores_ptr:
        if LO <= sp[3] < HI and "rbp" not in sp[2] and "rsp" not in sp[2]:
            print("  region ptr stored to non-stack: 0x%x [%s] val=0x%x" % (sp[1], sp[2], sp[3]))
    for sp in stores_ptr:
        if LO <= sp[3] < HI:
            print("  region ptr store 0x%x [%s] val=0x%x FrameRegister=%s" % (
                sp[1], sp[2], sp[3], frame_reg(raw, secs, base, sp[1])))
    for a in lo_w:
        print("  region write 0x%x %s %s eff=0x%x origin=0x%x" % (a[1], a[2], a[3], a[4], a[0][1]))
    print("region accesses by eff (root origin, insn, w):")
    for a in sorted((a for a in access if LO <= a[4] < HI), key=lambda a: (a[4], a[1])):
        print("  eff=0x%x 0x%x %s %s w=%s root=0x%x" % (a[4], a[1], a[2], a[3], a[5], a[0][1]))
    prov = collections.Counter()
    for a, mn in rep_sites:
        cls = "no-rdi-writer-in-300"
        seq = []
        for ins in md.disasm(read_va(a - 600, 616), a - 600):
            if ins.address >= a:
                break
            seq.append(ins)
        for ins in reversed(seq[-300:]):
            if ins.mnemonic.startswith(("rep", "movs", "stos", "ins", "outs")):
                continue
            if any(r64(md, r) == "rdi" for r in ins.regs_write) or any(
                op.type == X86_OP_REG and op.access & CS_AC_WRITE and r64(md, op.reg) == "rdi" for op in ins.operands
            ):
                ops = ins.operands
                if ins.mnemonic == "lea" and ops[1].type == X86_OP_MEM:
                    m = ops[1].mem
                    if m.base == X86_REG_RIP:
                        t = (ins.address + ins.size + m.disp) & MASK
                        cls = "lea-rip-region" if LO <= t < HI else "lea-rip-other"
                    elif m.base in (capstone.x86.X86_REG_RSP, capstone.x86.X86_REG_RBP):
                        cls = "lea-stack"
                    else:
                        cls = "lea-reg"
                else:
                    cls = "other:" + ins.mnemonic
                break
        prov[cls] += 1
    print("rep string sites by rdi source (300-insn window, string ops skipped): %s" % dict(prov))
    imm = 0
    raw_np = np.frombuffer(raw, dtype=np.uint8)
    for s2 in secs:
        if not s2.Characteristics & 0x20000000:
            continue
        d = raw_np[s2.PointerToRawData:s2.PointerToRawData + s2.SizeOfRawData]
        n = len(d) - 5
        if n <= 0:
            continue
        op_b = d[:n]
        val = np.ndarray(shape=(n,), dtype="<u4", buffer=raw, offset=s2.PointerToRawData + 1, strides=(1,)).astype(np.int64)
        m = ((op_b >= 0xB8) & (op_b <= 0xBF)) & (val >= LO) & (val < HI)
        imm += int(m.sum())
    print("mov r32, imm32 byte candidates with value in region=%d" % imm)
    print("sec=%.1f" % (time.time() - t0))


if __name__ == "__main__":
    main()
