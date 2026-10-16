#!/usr/bin/env python3
"""MX-60 (#5498): 0x17b680 / 0x17b460 / livein_passthrough 6 関数 (P1〜P6) の呼出元を、命令デコードで数える。

mx55_callers*.py は `ff /2` の機械語列を byte scan するだけで、直接 E8/E9 は数えない。
本スクリプトは .pdata の各関数を capstone で逆アセンブルし、次を出す:
  1. 直接 call/jmp (E8/E9) の target が対象 VA に一致する命令 (呼出元の関数と VA)。
  2. RIP 相対で対象 VA そのものを参照する命令 (関数ポインタの取得)。
  3. .rdata / .data の 8 byte slot で対象 VA を指すもの (所属 vtable と index)。
  4. `lea/mov [rip+X]` で vtable 先頭 X を参照する箇所 (= コンストラクタ候補)。
  5. `call [reg+disp]` (disp 0xf0 = index 30, 0x100 = index 32) を含む関数と、
     disp 0xf0 の各サイトで xmm2 が呼出し時点で有効か (関数先頭から線形)。
  6. 生バイト E8/E9 rel32 の一致 (逆アセンブル結果との突き合わせ)。
P1〜P6 は「呼出元を探す対象」の関数 (livein_passthrough の関数) であり、呼出し先ではない。

usage: mx60_callers.py <pe>
"""
import re
import struct
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

# キーは全て RVA (ImageBase 0x180000000 からの差)。照合は全て RVA で行う。
TARGETS = {
    0x17B680: 'F_scalar',
    0x17B460: 'F_caller_of_scalar',
    0x198700: 'P1',
    0x1E47C0: 'P2',
    0x1EF4B0: 'P3',
    0x1F36A0: 'P4',
    0x3BEF80: 'P5',
    0x104AEA0: 'P6',
}
PN = sorted((v, k) for k, v in TARGETS.items() if v.startswith('P'))
VTABLES = [0x183976038, 0x1841836A8]


def main(pe_path):
    pe = pefile.PE(pe_path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(pe_path, 'rb').read()
    sec = {s.Name.rstrip(b'\0'): s for s in pe.sections}
    rd = sec[b'.rdata']
    text = [s for s in pe.sections if s.Characteristics & 0x20000000][0]
    t_lo = base + text.VirtualAddress
    t_hi = t_lo + text.Misc_VirtualSize
    rd_lo = base + rd.VirtualAddress
    rd_hi = rd_lo + rd.Misc_VirtualSize
    blob = data[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]

    def rq(va):
        return struct.unpack_from('<Q', data, rd.PointerToRawData + (va - rd_lo))[0]

    ex = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
    ex_sec = [s for s in pe.sections if s.VirtualAddress <= ex.VirtualAddress < s.VirtualAddress + s.Misc_VirtualSize][0]
    ex_off = ex.VirtualAddress - ex_sec.VirtualAddress + ex_sec.PointerToRawData
    funcs = []
    for k in range(ex.Size // 12):
        b, e = struct.unpack_from('<II', data, ex_off + k * 12)[:2]
        funcs.append((base + b, base + e))
    funcs.sort()
    starts = [f[0] for f in funcs]

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True

    print('== vtable slots (.rdata 8 byte 照合) ==')
    for name, T in [('scalar', base + 0x17B680), ('caller', base + 0x17B460)] + [
        (n, base + k) for n, k in PN
    ]:
        for va in range(rd_lo, rd_hi - 7, 8):
            if rq(va) != T:
                continue
            v = va
            while v - 8 >= rd_lo and t_lo <= rq(v - 8) < t_hi:
                v -= 8
            print('  %s %#x in vtable %#x index %d' % (name, T - base, v, (va - v) // 8))

    direct = {t: [] for t in TARGETS}
    rip_vt = {v: [] for v in VTABLES}
    disp_callers = {0xF0: set(), 0x100: set()}
    addr_taken = {}
    for fs, fe in funcs:
        if not (t_lo <= fs < t_hi):
            continue
        for i in md.disasm(blob[fs - t_lo:fe - t_lo], fs):
            if i.mnemonic in ('call', 'jmp') and i.operands and i.operands[0].type == X86_OP_IMM:
                tgt = i.operands[0].imm - base
                if tgt in direct:
                    direct[tgt].append((i.address - base, fs - base, i.mnemonic))
            for op in i.operands:
                if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                    ea = i.address + i.size + op.mem.disp
                    if ea in rip_vt:
                        rip_vt[ea].append((i.address - base, fs - base, i.mnemonic))
                    if ea - base in TARGETS:
                        addr_taken.setdefault(ea - base, []).append((i.address - base, fs - base, i.mnemonic))
            if i.mnemonic == 'call' and i.operands and i.operands[0].type == X86_OP_MEM:
                m = i.operands[0].mem
                if m.base != 0 and m.index == 0 and m.disp in disp_callers:
                    disp_callers[m.disp].add(fs - base)

    print('== 直接 call/jmp (E8/E9) の target 一致 ==')
    for tgt in sorted(TARGETS):
        print('  target %#x (%s): %d 件' % (tgt, TARGETS[tgt], len(direct[tgt])))
        for site, fn, mn in direct[tgt]:
            print('    %#x in fn %#x (%s)' % (site, fn, mn))

    print('== RIP 相対で対象 VA そのものを参照 (関数ポインタの取得) ==')
    for tgt in sorted(TARGETS):
        print('  target %#x (%s): %d 件' % (tgt, TARGETS[tgt], len(addr_taken.get(tgt, []))))
        for site, fn, mn in addr_taken.get(tgt, []):
            print('    %#x in fn %#x (%s)' % (site, fn, mn))

    print('== 生バイト E8/E9 rel32 の一致 (逆アセンブル外の確認) ==')
    e8_raw = {}
    for m in re.finditer(rb'[\xe8\xe9]([\x00-\xff]{4})', blob):
        h = m.start()
        rel = struct.unpack('<i', m.group(1))[0]
        tgt = (t_lo + h + 5 + rel) - base
        if tgt in TARGETS:
            e8_raw.setdefault(tgt, []).append(h)
    for tgt in sorted(TARGETS):
        print('  raw E8/E9 -> %#x: %d 件 %s' % (tgt, len(e8_raw.get(tgt, [])), ' '.join('%#x' % (t_lo + h - base) for h in e8_raw.get(tgt, []))))

    print('== lea/mov [rip+X] で vtable 先頭を参照 ==')
    for vt in VTABLES:
        print('  vtable %#x: %d 件' % (vt - base, len(rip_vt[vt])))
        for site, fn, mn in rip_vt[vt]:
            print('    %#x in fn %#x (%s)' % (site, fn, mn))

    print('== call [reg+disp] の呼出元関数 (disp 0xf0 = index 30, 0x100 = index 32) ==')
    for disp in (0xF0, 0x100):
        print('  disp %#x: 呼出元関数 %d 件' % (disp, len(disp_callers[disp])))
        print('    ' + ' '.join('%#x' % c for c in sorted(disp_callers[disp])))

    print('== .rdata / .data の 8 byte slot で各関数の VA を指すもの ==')
    dt = sec[b'.data']
    d_lo = base + dt.VirtualAddress
    d_hi = d_lo + min(dt.Misc_VirtualSize, dt.SizeOfRawData)
    d_raw = dt.PointerToRawData
    for name, rva in [('F_caller_of_scalar', 0x17B460), ('F_scalar', 0x17B680)] + [
        (n, k) for n, k in PN
    ]:
        T = base + rva
        rd_hits = [va for va in range(rd_lo, rd_hi - 7, 8) if rq(va) == T]
        d_hits = [va for va in range(d_lo, d_hi - 7, 8)
                  if struct.unpack_from('<Q', data, d_raw + (va - d_lo))[0] == T]
        print('  %s %#x: .rdata %d 件 / .data %d 件' % (name, rva, len(rd_hits), len(d_hits)))
        for va in rd_hits:
            v = va
            while v - 8 >= rd_lo and t_lo <= rq(v - 8) < t_hi:
                v -= 8
            print('    .rdata slot %#x vtable %#x index %d' % (va - base, v - base, (va - v) // 8))

    print('== call [reg+0xf0] の各サイトで xmm2 が呼出し時点で有効か (関数先頭から線形) ==')
    ends = {s: e for s, e in funcs}
    for fs_rva in sorted(disp_callers[0xF0]):
        fs = base + fs_rva
        fe = ends[fs]
        live = False
        for i in md.disasm(blob[fs - t_lo:fe - t_lo], fs):
            if i.mnemonic == 'call' and i.operands and i.operands[0].type == X86_OP_MEM \
                    and i.operands[0].mem.disp == 0xF0 and i.operands[0].mem.index == 0:
                print('  fn %#x call site %#x: xmm2_live=%s' % (fs_rva, i.address - base, live))
                live = False
                continue
            if i.mnemonic in ('call', 'ret'):
                live = False
                continue
            _, wr = i.regs_access()
            if any(md.reg_name(r) == 'xmm2' for r in wr):
                live = True
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
