#!/usr/bin/env python3
"""Packer/obfuscation/anti-debug structural indicators for a PE32+. usage: protect_indicators.py <pe>"""
import sys, struct, math, collections, re, bisect
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_OP_REG, X86_OP_IMM
pe = pefile.PE(sys.argv[1]); IMG = pe.OPTIONAL_HEADER.ImageBase
S = {s.Name.rstrip(b'\0').decode(): s for s in pe.sections}
T = S['.text']; TB = T.get_data(); TVA = T.VirtualAddress
pd = S['.pdata'].get_data(); fn = []
for i in range(0, len(pd) - 11, 12):
    b, e, u = struct.unpack_from('<III', pd, i)
    if b and TVA <= b < TVA + len(TB): fn.append((b, e))
fn.sort()
md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
dec = 0; tot = 0; c = collections.Counter(); undec_funcs = 0
for b, e in fn:
    code = TB[b - TVA:e - TVA]; tot += len(code); got = 0
    for i in md.disasm(code, b):
        got += i.size; m = i.mnemonic
        if m == 'jmp' and i.operands and i.operands[0].type == X86_OP_REG: c['jmp_reg'] += 1
        elif m == 'jmp' and i.operands and i.operands[0].type == X86_OP_MEM: c['jmp_mem'] += 1
        elif m == 'call' and i.operands and i.operands[0].type == X86_OP_REG: c['call_reg'] += 1
        elif m == 'call' and i.operands and i.operands[0].type == X86_OP_MEM: c['call_mem'] += 1
        elif m in ('rdtsc', 'rdtscp', 'ud2', 'icebp', 'pushfq', 'popfq', 'int', 'int1', 'syscall', 'sysenter', 'lock'): c[m] += 1
        elif m == 'int3': c['int3_in_func'] += 1
        elif m in ('ret', 'retf'): c['ret'] += 1
        elif m.startswith('cmov') : c['cmov'] += 1
        c['insn'] += 1
    dec += got
    if got < len(code) * 0.95: undec_funcs += 1
print(f"decode coverage by pdata funcs: {dec}/{tot} = {100*dec/tot:.2f}%  funcs<95% decoded: {undec_funcs}/{len(fn)}")
print({k: v for k, v in c.items()})
raw_rdtsc = len(re.findall(rb'\x0f\x31', TB)); raw_int2d = len(re.findall(rb'\xcd\x2d', TB)); raw_syscall = len(re.findall(rb'\x0f\x05', TB))
print(f"raw byte patterns in .text: rdtsc(0f31)={raw_rdtsc} int2d={raw_int2d} syscall(0f05)={raw_syscall} (raw matches include false positives inside operands)")
# entry point
ep = pe.OPTIONAL_HEADER.AddressOfEntryPoint
code = TB[ep - TVA: ep - TVA + 48]
print('EP bytes', code.hex(), '|', '; '.join(f"{i.mnemonic} {i.op_str}" for i in md.disasm(code, ep)))
# TLS callbacks
if hasattr(pe, 'DIRECTORY_ENTRY_TLS'):
    t = pe.DIRECTORY_ENTRY_TLS.struct
    off = t.AddressOfCallBacks - IMG
    cbs = []
    while True:
        v = struct.unpack_from('<Q', pe.get_data(off, 8))[0]
        if not v: break
        cbs.append(hex(v)); off += 8
    print('TLS callbacks', cbs)
# load config: CFG / guard flags
if hasattr(pe, 'DIRECTORY_ENTRY_LOAD_CONFIG'):
    lc = pe.DIRECTORY_ENTRY_LOAD_CONFIG.struct
    print('LoadConfig GuardFlags=0x%x SecurityCookie=%s' % (getattr(lc, 'GuardFlags', 0), hex(lc.SecurityCookie)))
# rich header
try:
    rh = pe.parse_rich_header()
    if rh:
        vals = rh['values']
        print('Rich header entries:', len(vals) // 2, ' (prodid,count) top:', sorted([(vals[i] >> 16, vals[i + 1]) for i in range(0, len(vals), 2)], key=lambda x: -x[1])[:5])
except Exception as e: print('rich: n/a', e)
# overlay
over = pe.get_overlay_data_start_offset()
print('overlay offset:', over, 'file size:', len(pe.__data__))
# header-declared section name sanity
print('section names:', [s.Name.rstrip(b'\0').decode() for s in pe.sections])
