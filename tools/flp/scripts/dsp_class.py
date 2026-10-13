#!/usr/bin/env python3
"""Eff_Render (vtable slot 7) の直接呼出閉包を静的に走査し、ORACLE.md §3 の関数クラス (A: 四則のみ / B: libm 超越関数経由) を推定する。
usage: dsp_class.py <plugin_x64.dll>...   (stdout に JSON)
数え方:
  - 閉包 = slot7 から `call/jmp rel32` で到達する .text 内の関数 (関数境界は .pdata の RUNTIME_FUNCTION; 到達先が .pdata 外なら除外)
  - x87 = 命令 mnemonic が f* (fld/fstp/fmul/fsin/f2xm1/fyl2x/fpatan/fptan ...)。 超越 x87 = f2xm1 fyl2x fyl2xp1 fpatan fptan fsin fcos fsincos fprem
  - IAT 呼出 = `call [rip+disp]` の解決先が import 名 (msvcrt/ucrt の exp/pow/tan/sin/log/tanh 等)
  - 間接呼出 = `call [reg+disp]` / `call reg` (仮想/関数ポインタ。 framework の SIMD kernel 表経由もここ) → 件数のみ
推定の限界: 間接呼出先 (kernel 表・host) は辿らない。 framework 側の libm 呼出は閉包外 = frontier として別計上 (frontier の中身までは見ない)。"""
import json, struct, sys, collections
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_OP_IMM, X86_REG_RIP

TRANS_X87 = {'f2xm1', 'fyl2x', 'fyl2xp1', 'fpatan', 'fptan', 'fsin', 'fcos', 'fsincos', 'fprem', 'fprem1', 'fscale'}
LIBM = ('exp', 'pow', 'tan', 'sin', 'cos', 'log', 'tanh', 'sqrt', 'atan', 'floor', 'ceil', 'fmod')


def analyse(path):
    d = open(path, 'rb').read()
    pe = pefile.PE(data=d)
    base = pe.OPTIONAL_HEADER.ImageBase
    rd = lambda va, n: d[pe.get_offset_from_rva(va - base):][:n]
    q = lambda va: struct.unpack('<Q', rd(va, 8))[0]
    pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0].get_data()
    funcs = {}
    for i in range(len(pd) // 12):
        b, e, u = struct.unpack_from('<III', pd, 12 * i)
        if b: funcs[base + b] = base + e
    starts = sorted(funcs)
    iat = {}
    for ent in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
        for imp in ent.imports:
            iat[imp.address] = (ent.dll.decode().lower(), (imp.name or b'?').decode())
    ent = [base + e.address for e in pe.DIRECTORY_ENTRY_EXPORT.symbols if e.name == b'CreatePlugInstance'][0]
    md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
    cref = None
    for i in md.disasm(rd(ent, 120), ent):
        if i.mnemonic == 'mov' and 'rcx, qword ptr [rip' in i.op_str and i.address > ent + 0x20:
            cref = i.address + i.size + i.operands[1].mem.disp; break
    vt = q(cref)
    entry = q(vt + 8 * 7)
    seen, work = set(), [entry]
    x87 = collections.Counter(); trans = collections.Counter(); imports = collections.Counter(); ind = 0; insn_n = 0; bytes_n = 0
    sse = collections.Counter()
    while work:
        f = work.pop()
        if f in seen or f not in funcs: continue
        seen.add(f)
        code = rd(f, funcs[f] - f); bytes_n += len(code)
        for i in md.disasm(code, f):
            insn_n += 1
            mn = i.mnemonic
            if mn.startswith('f') and mn not in ('fxsave', 'fxrstor'):
                x87[mn] += 1
                if mn in TRANS_X87: trans[mn] += 1
            if mn in ('sqrtss', 'sqrtps', 'sqrtsd', 'rsqrtss', 'rsqrtps', 'rcpss', 'rcpps', 'divss', 'divps', 'divsd', 'cvtsi2ss', 'cvttss2si', 'roundss', 'maxss', 'minss'):
                sse[mn] += 1
            if mn in ('call', 'jmp') and i.operands:
                o = i.operands[0]
                if o.type == X86_OP_IMM:
                    t = o.imm
                    if t in funcs and mn == 'call': work.append(t)
                    elif t in funcs and mn == 'jmp' and t != f: work.append(t)
                elif o.type == X86_OP_MEM and mn == 'call':
                    if o.mem.base == X86_REG_RIP:
                        a = i.address + i.size + o.mem.disp
                        if a in iat: imports['%s!%s' % iat[a]] += 1
                        else: ind += 1
                    else: ind += 1
                elif mn == 'call': ind += 1
    libm = {k: v for k, v in imports.items() if any(k.split('!')[1].lower().lstrip('_').startswith(m) for m in LIBM)}
    return dict(entry=hex(entry), closureFuncs=len(seen), closureBytes=bytes_n, insns=insn_n, x87=dict(x87), x87Transcendental=dict(trans),
                importCalls=dict(imports), libmImportCalls=libm, indirectCalls=ind, sseNonArith=dict(sse))


if __name__ == '__main__':
    out = {}
    for p in sys.argv[1:]:
        out[p.split('/')[-1]] = analyse(p)
    print(json.dumps(out, indent=1))
