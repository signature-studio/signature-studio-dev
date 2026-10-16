#!/usr/bin/env python3
"""FLEngine PE で、大域 (絶対 VA) への参照を種類別に列挙する (#5580 / #5205 受入 1 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_global_init_probe.py <大域 VA(16進)> [<大域 VA> ...]
  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_global_init_probe.py <大域 VA(16進)> --near   (±0x40 の RIP 相対参照を番地ごとに数える)
  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_global_init_probe.py <格納位置 VA(16進)> --reloc   (.reloc の DIR64 再配置対象か)
  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_global_init_probe.py <大域 VA(16進)> --base   (既知の定数を基底とする [reg+disp] 書込みを T-0x100..T+8 で列挙)

方式:
- .pdata の関数ごとに、関数先頭から末尾まで逆アセンブルする (関数単位なので線形同期のずれは関数内に限られる)。
- 各命令について、次の 3 種を列挙する。
  rip   : [rip+d] のメモリ参照で、実効アドレスが大域 VA に一致する (load / store / lea を区別)。
  abs   : 変位 (disp) または即値 (imm) が大域 VA に一致する命令 (絶対アドレス参照)。
  lea-alias: `lea r, [rip+d]` で r に大域 VA を載せ、同一関数内の後続で r 経由の書込み ([r+k] = 大域 VA + k)
          を追う (制御フローは無視し、命令の並び順のみ。r が別の値で上書きされたら追跡を止める)。
- 参照の多くは「読むだけ」なので、書込み候補 (store / alias-store / abs-store) を別枠で出す。
- .data / .rdata の 8 バイト値として大域 VA が格納されている位置も列挙する (初期化テーブル・vptr 等)。

件数は上界ではなく、書込み候補の行は手で確認すること (例: cmp・test の即値一致は abs に入る)。
"""
import bisect
import collections
import os
import struct
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
X86 = capstone.x86
STORE_MNEM = {"mov", "movups", "movaps", "movdqu", "movdqa", "movq", "movsd", "movss", "movlps", "movhps",
              "movnti", "stosq", "stosd", "xchg", "add", "sub", "and", "or", "xor", "inc", "dec", "neg", "not",
              "adc", "sbb", "shl", "shr", "sar", "rol", "ror", "setne", "sete", "cmpxchg", "xadd"}
NO_WRITE_MNEM = {"cmp", "test", "push", "call", "jmp", "lea", "prefetcht0", "prefetchnta"}


def writes_mem(ins, op_index):
    """オペランド 0 がメモリで、命令がそれを書き換えるかの粗い判定。"""
    return op_index == 0 and ins.mnemonic not in NO_WRITE_MNEM and ins.mnemonic.split()[0] in STORE_MNEM


def near_scan(raw, base, text, funcs, T, span):
    """T の前後 span バイト以内の RIP 相対メモリ参照を、アドレスごとに load / store で数える。
    構造体の一部として T を含む領域 (base+k) への書込みを拾うための補助。"""
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    cnt = collections.defaultdict(lambda: [0, 0])
    lea_hits = []
    for f0, f1 in funcs:
        fo = f0 - (base + text.VirtualAddress) + text.PointerToRawData
        for ins in md.disasm(raw[fo:fo + (f1 - f0)], f0):
            for i, o in enumerate(ins.operands):
                if o.type != X86.X86_OP_MEM or o.mem.base != X86.X86_REG_RIP:
                    continue
                ea = ins.address + ins.size + o.mem.disp
                if abs(ea - T) > span:
                    continue
                if ins.mnemonic == "lea":
                    lea_hits.append((ea, hex(f0), hex(ins.address), ins.op_str))
                elif writes_mem(ins, i):
                    cnt[ea][1] += 1
                else:
                    cnt[ea][0] += 1
    print("near %x +-%x: rip-lea %d" % (T, span, len(lea_hits)))
    for ea, c in sorted(cnt.items()):
        print("  %x load=%d store=%d%s" % (ea, c[0], c[1], "  <== T" if ea == T else ""))
    for row in lea_hits:
        print("  lea %x fn=%s at=%s %s" % row)


def base_store_scan(raw, base, text, funcs, T, span):
    """レジスタに載せた既知の定数 (lea rip / mov reg, imm) を基底として、[reg+disp] の書込みの実効アドレスが
    T の近傍 (T-span..T+8) に入るものを列挙する。関数内の命令順のみで追い、基底が上書きされたら捨てる。"""
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    rows = []
    for f0, f1 in funcs:
        fo = f0 - (base + text.VirtualAddress) + text.PointerToRawData
        known = {}
        for ins in md.disasm(raw[fo:fo + (f1 - f0)], f0):
            ops = ins.operands
            for i, o in enumerate(ops):
                if o.type != X86.X86_OP_MEM or o.mem.base in (0, X86.X86_REG_RIP) or o.mem.index != 0:
                    continue
                bn = ins.reg_name(o.mem.base)
                if bn in known and writes_mem(ins, i):
                    ea = known[bn] + o.mem.disp
                    if T - span <= ea <= T + 8:
                        rows.append((hex(f0), hex(ins.address), ins.mnemonic, ins.op_str, hex(ea)))
            if ops and ops[0].type == X86.X86_OP_REG:
                dn = ins.reg_name(ops[0].reg)
                if ins.mnemonic == "lea" and len(ops) == 2 and ops[1].type == X86.X86_OP_MEM and ops[1].mem.base == X86.X86_REG_RIP:
                    known[dn] = ins.address + ins.size + ops[1].mem.disp
                elif ins.mnemonic == "mov" and len(ops) == 2 and ops[1].type == X86.X86_OP_IMM:
                    known[dn] = ops[1].imm & 0xffffffffffffffff
                else:
                    known.pop(dn, None)
            if ins.mnemonic in ("call", "ret", "jmp"):
                known.clear()
    print("base-store near %x (-%x..+8): %d" % (T, span, len(rows)))
    for r in rows:
        print("  fn=%s at=%s %s %s ea=%s" % r)


def reloc_check(pe, base, T):
    """T の格納位置が .reloc の DIR64 再配置対象か (ローダが初期値を書くか) を確認する。"""
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    rva = T - base
    hits = [(hex(b.struct.VirtualAddress), e.type) for b in pe.DIRECTORY_ENTRY_BASERELOC for e in b.entries if e.rva == rva]
    print("reloc %x: entries=%s (type 10 = DIR64)" % (T, hits))


def main():
    near = "--near" in sys.argv
    based = "--base" in sys.argv
    reloc = "--reloc" in sys.argv
    targets = [int(a, 16) for a in sys.argv[1:] if not a.startswith("--")]
    if not targets:
        print("usage: pe_global_init_probe.py <VA> [<VA> ...]", file=sys.stderr)
        return 2
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    if reloc:
        for T in targets:
            reloc_check(pe, base, T)
        return 0
    sec = {s.Name.rstrip(b"\0"): s for s in pe.sections}
    print("sections:", " ".join("%s=%x..%x" % (k.decode(), base + s.VirtualAddress, base + s.VirtualAddress + s.Misc_VirtualSize)
                                for k, s in sec.items() if k in (b".text", b".data", b".rdata")))
    text = sec[b".text"]
    pd = raw[sec[b".pdata"].PointerToRawData:sec[b".pdata"].PointerToRawData + sec[b".pdata"].SizeOfRawData]
    funcs = sorted((base + b, base + e) for b, e, _ in (struct.unpack_from("<III", pd, i) for i in range(0, len(pd) - 11, 12)) if b)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    if near:
        for T in targets:
            near_scan(raw, base, text, funcs, T, 0x40)
        return 0
    if based:
        for T in targets:
            base_store_scan(raw, base, text, funcs, T, 0x100)
        return 0

    for T in targets:
        print("== global %x ==" % T)
        rip_load, rip_store, rip_lea, abs_hits, alias_store, alias_lea = [], [], [], [], [], []
        for f0, f1 in funcs:
            fo = f0 - (base + text.VirtualAddress) + text.PointerToRawData
            code = raw[fo:fo + (f1 - f0)]
            alias = {}  # reg name -> disp base (T + ...) の意味は「reg = T」のみ扱う
            for ins in md.disasm(code, f0):
                ops = ins.operands
                mem_ops = [(i, o) for i, o in enumerate(ops) if o.type == X86.X86_OP_MEM]
                for i, o in mem_ops:
                    m = o.mem
                    if m.base == X86.X86_REG_RIP and ins.address + ins.size + m.disp == T:
                        rec = (hex(f0), hex(ins.address), ins.mnemonic, ins.op_str)
                        if ins.mnemonic == "lea":
                            rip_lea.append(rec)
                            alias[ins.reg_name(ops[0].reg)] = 0
                        elif writes_mem(ins, i):
                            rip_store.append(rec)
                        else:
                            rip_load.append(rec)
                    elif m.base == 0 and m.index == 0 and m.disp == T:
                        abs_hits.append((hex(f0), hex(ins.address), ins.mnemonic, ins.op_str))
                    elif m.base != 0 and m.base != X86.X86_REG_RIP and ins.reg_name(m.base) in alias:
                        k = m.disp
                        if writes_mem(ins, i):
                            alias_store.append((hex(f0), hex(ins.address), ins.mnemonic, ins.op_str, "T+%x" % (k + alias[ins.reg_name(m.base)])))
                # 即値・派生の abs 一致
                for o in ops:
                    if o.type == X86.X86_OP_IMM and o.imm == T:
                        abs_hits.append((hex(f0), hex(ins.address), ins.mnemonic, ins.op_str))
                # alias の更新 (r への代入で上書き)
                if ops and ops[0].type == X86.X86_OP_REG:
                    dn = ins.reg_name(ops[0].reg)
                    if ins.mnemonic == "mov" and len(ops) == 2 and ops[1].type == X86.X86_OP_REG and ins.reg_name(ops[1].reg) in alias:
                        alias[dn] = alias[ins.reg_name(ops[1].reg)]
                    elif not (ins.mnemonic == "lea" and any(
                            o.type == X86.X86_OP_MEM and o.mem.base == X86.X86_REG_RIP and ins.address + ins.size + o.mem.disp == T for o in ops)):
                        alias.pop(dn, None)
                if ins.mnemonic in ("call", "ret", "jmp"):
                    alias.clear()

        print("rip load: %d / rip store: %d / rip lea: %d / abs: %d / alias-store: %d" %
              (len(rip_load), len(rip_store), len(rip_lea), len(abs_hits), len(alias_store)))
        for name, rows in (("rip store", rip_store), ("rip lea", rip_lea), ("abs", abs_hits), ("alias store", alias_store)):
            for r in rows:
                print("  %s fn=%s" % (name, " ".join(str(x) for x in r)))

        # 8 バイト値として T が格納される位置 (初期化テーブル・vptr)
        for sname in (b".data", b".rdata"):
            s = sec[sname]
            body = raw[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
            pat = struct.pack("<Q", T)
            j = body.find(pat)
            while j != -1:
                print("  8byte-value in %s at %x" % (sname.decode(), base + s.VirtualAddress + j))
                j = body.find(pat, j + 1)
        print("  rip-load sample:", rip_load[:3])


if __name__ == "__main__":
    sys.exit(main())
