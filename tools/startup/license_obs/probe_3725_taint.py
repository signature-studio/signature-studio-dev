#!/usr/bin/env python3
"""#3725 (ST-1) 受入 1: g1 (0x14f852c) を指すレジスタの由来を追い、g1 への格納を広く列挙する (読取専用・静的)。

probe_3725_narrow.py は「g1 スロットを読んだ直後 1 命令」しか見ない。本 probe は次を行う:
  - 起点: (a) g1 スロット (0x15e14a8) を qword で読む mov、(b) g1 を rip 相対で指す lea、
    のどちらかでレジスタに &g1 が入った関数を対象にする。
  - 関数内を命令順に線形に走査し、&g1 を保持するレジスタ集合 (taint) を伝播する。
    mov/lea/movzx でのコピーは伝播、それ以外の書込みと caller-saved レジスタの call による破壊で除去する。
  - taint の基底で格納 (mov [reg+disp], src) するものを全件記録する。disp が 0 のものは &g1 そのもの。
  - g1 を rip 相対で直接格納する命令 (mov [rip+G1], ...) を全関数から記録する。
  - &g1 を引数レジスタ (rcx/rdx/r8/r9) に入れたままの call を記録する (呼び先の格納は本 probe の対象外)。

制約 (REPORT に書く): 直線走査で CFG を見ない。分岐の合流や、add/sub で &g1+k になったレジスタは追わない。
呼び先の中の格納は追わない (引数渡しの call として数えるだけ)。よって結果は下限ではなく
「直線走査で見える範囲の列挙」であり、0 件でも g1 に書かれないことの証明にはならない。

usage: python probe_3725_taint.py --write   (要 FL_WIN64_DIR・venv: tools/startup/license_obs/env.sh)
出力: results/probe_3725_taint.json (--write 時)
"""
import json, os, re, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from peidx import Image, rip_target  # noqa: E402

G1 = 0x14f852c
CALLER_SAVED = {'rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'}
ARG_REGS = {'rcx', 'rdx', 'r8', 'r9'}
NO_WRITE = {'cmp', 'test', 'ucomisd', 'comisd', 'ucomiss', 'comiss', 'bt'}
REG64 = ['rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'rbp', 'rsp'] + ['r%d' % i for i in range(8, 16)]
REG32 = ['eax', 'ebx', 'ecx', 'edx', 'esi', 'edi', 'ebp', 'esp'] + ['r%dd' % i for i in range(8, 16)]
TO64 = dict(zip(REG32, REG64))
TO64.update({r: r for r in REG64})
MEM = re.compile(r'(?:(dword|qword|word|byte) )?ptr \[([^\]]*)\]')
BASE = re.compile(r'\b(r[a-z0-9]+|e[a-z]{2}|r\d+d?)\b')


def reg64(op):
    return TO64.get(op.strip())


def base_of(mem_inner):
    # [rax + 0x3500] / [rip + ...] / [rbp + 0x4280]
    for tok in BASE.findall(mem_inner):
        if tok in TO64:
            return TO64[tok]
    return None


def disp_of(mem_inner):
    m = re.search(r'([+-])\s*(0x[0-9a-f]+)', mem_inner)
    if not m:
        return 0
    v = int(m.group(2), 16)
    return v if m.group(1) == '+' else -v


def find_slot(img):
    raw = img.raw
    pat = struct.pack('<Q', G1)
    out = []
    i = raw.find(pat)
    while i != -1:
        for s in img.pe.sections:
            if s.PointerToRawData <= i < s.PointerToRawData + s.SizeOfRawData:
                out.append(img.base + s.VirtualAddress + (i - s.PointerToRawData))
        i = raw.find(pat, i + 1)
    return out


def scan_func(lo, insns, slots):
    taint = set()
    stores, calls, sources = [], [], []
    for ins in insns:
        m = ins.mnemonic
        ops = ins.op_str
        at = ins.address
        if m.startswith('call'):
            if taint & ARG_REGS:
                calls.append({'at': hex(at), 'insn': ops, 'arg_taint': sorted(taint & ARG_REGS)})
            taint -= CALLER_SAVED
            continue
        if ',' not in ops:
            continue
        dst, src = ops.split(', ', 1)
        if m in NO_WRITE:
            continue
        dmem = MEM.match(dst)
        # 格納 (宛先がメモリ)
        if dmem:
            inner = dmem.group(2)
            if rip_target(ins) == G1:
                stores.append({'func': hex(lo), 'at': hex(at), 'insn': ops, 'via': 'rip-direct-g1'})
            b = base_of(inner)
            if b in taint:
                stores.append({'func': hex(lo), 'at': hex(at), 'insn': ops, 'via': 'taint:' + b,
                               'disp': disp_of(inner)})
            continue
        d = reg64(dst)
        if d is None:
            continue
        if dst.strip() not in REG64:
            taint.discard(d)
            continue
        smem = MEM.search(src)
        if m in ('mov', 'movzx', 'movsxd') and smem and rip_target(ins) in slots and 'qword' in src:
            taint.add(d)
            sources.append({'func': hex(lo), 'at': hex(at), 'insn': ops, 'kind': 'g1-slot-load'})
        elif m == 'lea' and rip_target(ins) == G1:
            taint.add(d)
            sources.append({'func': hex(lo), 'at': hex(at), 'insn': ops, 'kind': 'lea-g1'})
        elif m in ('mov', 'movzx', 'movsxd') and reg64(src) is not None and reg64(src) in taint:
            taint.add(d)
        else:
            taint.discard(d)
    return stores, calls, sources


def main():
    img = Image()
    slots = set(find_slot(img))
    all_stores, all_calls, all_sources = [], [], []
    for lo, hi, insns in img.iter_insns():
        L = list(insns)
        st, cl, so = scan_func(lo, L, slots)
        all_stores += st
        all_calls += cl
        all_sources += so
    funcs_with_source = sorted({s['func'] for s in all_sources})
    res = {
        'g1': hex(G1),
        'g1_slots': [hex(x) for x in sorted(slots)],
        'source_funcs': len(funcs_with_source),
        'sources': all_sources,
        'g1_stores': all_stores,
        'call_with_g1_arg': all_calls,
    }
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if '--write' in sys.argv:
        with open(os.path.join(HERE, 'results', 'probe_3725_taint.json'), 'w') as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
            f.write('\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
