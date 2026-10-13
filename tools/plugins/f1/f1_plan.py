#!/usr/bin/env python3
"""f1_plan.py — Eff_Render 単位の差分試験計画 (PLG-F1 #198)。

  python3 f1_plan.py <block> [<block> ...]     → work/f1/<block>/plan.json

1. win_abi.json から Eff_Render VA を得る。
2. Eff_Render から direct call/jmp (rel32) を BFS で辿り、.pdata の関数範囲を全て集める
   (framework 側の関数も含める = plugin_closure.py の frontier を Eff_Render 経路に限って取り込む)。
3. 経路内で `mov reg,[rip+cell]` の cell が「kernel 関数ポインタ変数」の VA を指すものを検出する。
   kernel 表は Balance の初期化関数 (0x5e19f0) と位置非依存ハッシュが一致する関数を当該 DLL から探し、
   kernel_table.py と同じ規則 (`lea reg,[rip+kernel]; mov [rip+var],reg`) で復元する。
4. 変数ごとに候補 2 実装のうち AVX/ymm 命令を含まない方 (SSE 路) を選ぶ。native 参照も同じ実装を
   変数に書き込んで実行するので、CPUID 分岐そのもの (init 本体) は試験範囲外。
5. 計画 JSON: entry / lift ranges / var→kernel / kernel の x87 有無 / 経路の関数数・バイト数。
"""
import json
import os
import struct
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_OP_REG, X86_OP_IMM, X86_REG_RIP

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path.insert(0, os.path.join(ROOT, '..', 'shared'))
from paths import FL_WIN64_DIR  # noqa: E402

WORK = os.path.join(ROOT, 'work')
BAL_INIT_RVA = 0x1e19f0


def load(block):
    fn = 'block%05d_PE.bin' % block
    d = open(os.path.join(FL_WIN64_DIR, 'extracted', fn), 'rb').read()
    pe = pefile.PE(data=d, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0].get_data()
    funcs = {}
    for i in range(len(pd) // 12):
        b, e, u = struct.unpack_from('<III', pd, 12 * i)
        if b and not (u & 1):
            funcs[base + b] = base + e
    return fn, d, pe, base, funcs


def code(pe, base, va, n):
    for s in pe.sections:
        a = base + s.VirtualAddress
        if a <= va < a + s.Misc_VirtualSize:
            return s.get_data()[va - a:va - a + n]
    return b''


def rd64(pe, base, va):
    return struct.unpack('<Q', pe.get_data(va - base, 8))[0]


def find_init(block):
    bal = json.load(open(os.path.join(WORK, 'winfuncs', 'block18983.json')))
    h = next(x[2] for x in bal['funcs'] if x[0] == BAL_INIT_RVA)
    mine = json.load(open(os.path.join(WORK, 'winfuncs', 'block%05d.json' % block)))
    c = [x[0] for x in mine['funcs'] if x[2] == h]
    return c


def kernel_vars(pe, base, funcs, init):
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    regv, assigns = {}, []
    for i in md.disasm(code(pe, base, init, funcs[init] - init), init):
        ops = i.operands
        if i.mnemonic == 'lea' and len(ops) == 2 and ops[0].type == X86_OP_REG and ops[1].type == X86_OP_MEM \
                and ops[1].mem.base == X86_REG_RIP:
            regv[ops[0].reg] = i.address + i.size + ops[1].mem.disp
        elif i.mnemonic == 'mov' and len(ops) == 2 and ops[0].type == X86_OP_MEM and ops[0].mem.base == X86_REG_RIP \
                and ops[1].type == X86_OP_REG and ops[1].reg in regv:
            assigns.append((i.address + i.size + ops[0].mem.disp, regv[ops[1].reg]))
    vars_ = {}
    for v, t in assigns:
        vars_.setdefault(v, [])
        if t not in vars_[v]:
            vars_[v].append(t)
    return vars_


def uses_avx(pe, base, funcs, va):
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    for i in md.disasm(code(pe, base, va, funcs[va] - va), va):
        if i.mnemonic.startswith('v') and i.mnemonic not in ('verr', 'verw'):
            return True
        if 'ymm' in i.op_str:
            return True
    return False


def has_x87(pe, base, funcs, va):
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    return any(i.mnemonic.startswith('f') and i.mnemonic not in ('fxsave', 'fxrstor') and i.mnemonic[:2] != 'fa' or False
               for i in md.disasm(code(pe, base, va, funcs[va] - va), va)) and \
        any(i.mnemonic in ('fld', 'fstp', 'fild', 'fistp', 'fmul', 'fadd', 'fsub', 'fxch', 'fcompp', 'fnclex', 'fldz')
            for i in md.disasm(code(pe, base, va, funcs[va] - va), va))


def bfs(pe, base, funcs, roots):
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    seen, q = {}, list(roots)
    while q:
        f = q.pop()
        if f in seen or f not in funcs:
            continue
        seen[f] = funcs[f] - f
        for i in md.disasm(code(pe, base, f, funcs[f] - f), f):
            if i.mnemonic in ('call', 'jmp') and i.operands and i.operands[0].type == X86_OP_IMM:
                t = i.operands[0].imm
                if t in funcs and not (f <= t < funcs[f]):
                    q.append(t)
    return seen


def plan(block):
    fn, d, pe, base, funcs = load(block)
    abi = {r['file']: r for r in json.load(open(os.path.join(WORK, 'win_abi.json')))}[fn]
    eff = int(abi['impl']['Eff_Render'], 16)
    inits = find_init(block)
    if len(inits) != 1:
        raise SystemExit('block %d: init 候補 %s' % (block, inits))
    init = base + inits[0]
    kv = kernel_vars(pe, base, funcs, init)
    path = bfs(pe, base, funcs, [eff])
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    used = {}
    for f in path:
        for i in md.disasm(code(pe, base, f, funcs[f] - f), f):
            if i.mnemonic == 'mov' and len(i.operands) == 2 and i.operands[1].type == X86_OP_MEM \
                    and i.operands[1].mem.base == X86_REG_RIP and i.operands[0].type == X86_OP_REG:
                cell = i.address + i.size + i.operands[1].mem.disp
                try:
                    v = rd64(pe, base, cell)
                except Exception:
                    continue
                if v in kv:
                    used.setdefault(hex(v), {'cell': hex(cell), 'sites': []})['sites'].append(hex(i.address))
    # kernel 表以外の関数ポインタ変数 (.bss) を指す cell: dsp_ippv2 等の動的束縛 (GetProcAddress 相当の binder が `lea rdx,[var]; lea r8,[name]` で束縛)
    bss = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.bss'][0]
    blo, bhi = base + bss.VirtualAddress, base + bss.VirtualAddress + bss.Misc_VirtualSize
    other = {}
    for f in path:
        for i in md.disasm(code(pe, base, f, funcs[f] - f), f):
            if i.mnemonic == 'mov' and len(i.operands) == 2 and i.operands[1].type == X86_OP_MEM \
                    and i.operands[1].mem.base == X86_REG_RIP and i.operands[0].type == X86_OP_REG:
                cell = i.address + i.size + i.operands[1].mem.disp
                try:
                    v = rd64(pe, base, cell)
                except Exception:
                    continue
                if blo <= v < bhi and v not in kv:
                    other.setdefault(hex(v), {'cell': hex(cell), 'sites': []})['sites'].append(hex(i.address))
    if other:
        want = {int(v, 16): v for v in other}
        for f, e in funcs.items():
            prev = []
            for i in md.disasm(code(pe, base, f, e - f), f):
                if i.mnemonic == 'lea' and len(i.operands) == 2 and i.operands[1].type == X86_OP_MEM \
                        and i.operands[1].mem.base == X86_REG_RIP:
                    tgt = i.address + i.size + i.operands[1].mem.disp
                    if tgt in want:
                        prev = [want[tgt], 3]
                    elif prev and i.operands[0].type == X86_OP_REG and i.op_str.startswith('r8'):
                        raw = pe.get_data(tgt - base, 48)
                        nm = raw.decode('utf-16le', 'ignore').split('\0')[0] if raw[1:2] == b'\0' else raw.split(b'\0')[0].decode('latin1')
                        other[prev[0]]['bound_name'] = nm
                        other[prev[0]]['binder'] = hex(f)
                        prev = []
                if prev:
                    prev[1] -= 1
                    if prev[1] < 0:
                        prev = []
    kern = {}
    for v, u in used.items():
        cands = kv[int(v, 16)]
        sse = [c for c in cands if not uses_avx(pe, base, funcs, c)]
        pick = (sse or cands)[0]
        kern[v] = {'cell': u['cell'], 'sites': u['sites'], 'cands': [hex(c) for c in cands],
                   'picked': hex(pick), 'picked_avx': uses_avx(pe, base, funcs, pick),
                   'picked_x87': has_x87(pe, base, funcs, pick)}
    kpath = bfs(pe, base, funcs, [int(k['picked'], 16) for k in kern.values()])
    allf = dict(path)
    allf.update(kpath)
    ranges = ['0x%x-0x%x' % (f, f + allf[f] - 1) for f in sorted(allf)]
    res = {'block': block, 'name': fn, 'base': hex(base), 'eff_render': hex(eff), 'init': hex(init),
           'kernel_vars_total': len(kv), 'path_funcs': len(path), 'path_bytes': sum(path.values()),
           'kernel_funcs_added': len(set(kpath) - set(path)),
           'total_funcs': len(allf), 'total_bytes': sum(allf.values()),
           'kernels': kern, 'other_ptr_vars': other, 'path': sorted(hex(f) for f in path), 'ranges': ranges}
    od = os.path.join(WORK, 'f1', str(block))
    os.makedirs(od, exist_ok=True)
    json.dump(res, open(os.path.join(od, 'plan.json'), 'w'), indent=1)
    open(os.path.join(od, 'ranges.txt'), 'w').write(','.join(ranges))
    return res


if __name__ == '__main__':
    for b in sys.argv[1:]:
        r = plan(int(b))
        print(b, {k: v for k, v in r.items() if k not in ('path', 'ranges', 'kernels', 'other_ptr_vars')},
              {v: (k['picked'], 'avx' if k['picked_avx'] else 'sse', 'x87' if k['picked_x87'] else '-') for v, k in r['kernels'].items()},
              {v: o.get('bound_name', '?') for v, o in r['other_ptr_vars'].items()})
