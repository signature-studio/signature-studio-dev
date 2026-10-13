#!/usr/bin/env python3
"""C++ DLL の VEX (AVX/FMA) 命令を含む .pdata 関数を数え、DSP 閉包 (closure_cpp.py) との交差と CPUID 分岐の有無を測る (PLG-F6-2 #545)。
  vex_scan.py <block>   → stdout JSON
定義: VEX 関数 = capstone が `v` で始まる mnemonic (vzeroupper を含む) を 1 つ以上返す .pdata 関数。
      AVX 検出フラグ = `cpuid` と `xgetbv` の両方を含む関数 (MSVC の AVX 可否判定) が書く .data の dword (`mov [rip+d], r32`)。
      guarded = そのフラグを `cmp dword ptr [rip+d], imm` で見る VEX 関数 (VEX 路と SSE 路の分岐を持つ)。 flag_writers = フラグへ書く関数。
      CRT の `__isa_available` (別の dword) とは別物: 実測 (Hardcore) では VEX 関数のどれもそれを見ない。
"""
import collections, json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared'))
from paths import FL_WIN64_DIR
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_OP_IMM, X86_REG_RIP
import closure_cpp as cc

b = int(sys.argv[1])
pe, base, img, ends = cc.load(b)
md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
text = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
vex, cpuid, xgetbv, cmpref, writers = {}, set(), set(), collections.defaultdict(set), collections.defaultdict(set)
for f, e in ends.items():
    n = 0
    for ins in md.disasm(img[f - base:e - base], f):
        if ins.mnemonic.startswith('v'):
            n += 1
        if ins.mnemonic == 'cpuid':
            cpuid.add(f)
        if ins.mnemonic == 'xgetbv':
            xgetbv.add(f)
        if ins.operands and ins.operands[0].type == X86_OP_MEM and ins.operands[0].mem.base == X86_REG_RIP and ins.operands[0].size == 4:
            tgt = ins.address + ins.size + ins.operands[0].mem.disp
            if ins.mnemonic == 'cmp' and ins.operands[1].type == X86_OP_IMM:
                cmpref[tgt].add(f)
            elif ins.mnemonic == 'mov':
                writers[tgt].add(f)
    if n:
        vex[f] = n
det = cpuid & xgetbv                       # AVX 検出関数
flags = {t for t, fs in writers.items() if fs & det}
guarded = {f for f in vex for t in flags if f in cmpref[t]}
out, closure, _, _ = cc.compute(b)
inclos = set(closure)
res = {'block': b, 'vex_funcs': len(vex), 'vex_funcs_in_dsp_closure': len(inclos & set(vex)), 'dsp_closure_funcs': len(closure),
       'avx_detect_funcs': sorted(hex(x) for x in det), 'avx_flags': sorted(hex(t) for t in flags),
       'vex_funcs_guarded_by_avx_flag': len(guarded), 'vex_funcs_unguarded': len(set(vex) - guarded),
       'vex_unguarded_in_dsp_closure': len((set(vex) - guarded) & inclos), 'vex_unguarded_va': sorted(hex(x) for x in set(vex) - guarded)}
print(json.dumps(res, indent=1))
