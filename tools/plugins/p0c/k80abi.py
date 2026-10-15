#!/usr/bin/env python3
"""k80abi.py — kernel 80 実装の win64 slot 読みを機械語から抽出する (P0c-2 検証の入力)。

  python3 k80abi.py [OUT.json]   (既定: work/k80abi.json)

win64 slot 規約:
  slot1..4 = rcx / rdx / r8 / r9 (整数) または xmm0..xmm3 (浮動小数; 同一 slot の型は
  呼出側の宣言で決まる) — RetDec の define 引数順と同じ並び。
  slot5+   = stack ([rbp+K] / [rsp+K] の read-before-write)。

検出は read-before-write (RMW 命令 dec/add 等は read+write 両方に計上)。
xmm4..15 は callee-saved (win64) なので slot に数えない。
**ゼロ化イディオムの除外** (CAB-253): `xorps xmmN, xmmN` / `pxor` / `xor r32, r32` /
`subsd xmmN, xmmN` は同一レジスタの read+write だが、引数の read ではない (レジスタを 0 に
する write)。capstone はこれらの src を read と付けるため、read-before-write の仮引数検出で
false positive になっていた (0x5df610 の xmm0 / 0x5e05b0 の edx / 0x5e1210 の xmm2 等)。
**機械語観測リスト**: helper (`__asm_*`) 対応の xmm レジスタ付き命令を (mnemonic, regist
operand の位置) で出力する。k80_argfix.py の [C] パターン (placeholder ↔ xmm slot の
機械語主導対話) の入力。
**scaled_index**: index レジスタに scale ≥ 2 のメモリ参照がある = ポインタ引数を
添字アクセスする kernel (0x5e0d80 等)。nat 実行時に負の添字 → OOB  read → SIGSEGV になる
ため、k80_diff.py が fp scalar 引数を非負に制限する (ドメイン制約) 判定に使う。
出力: {VA: {gpr_slots, xmm_slots, stack_args, floats, xmm_insns, scaled_index}} —
k80_argfix.py / kernel_diff の入力。
"""
import collections
import json
import os
import struct
import sys

import pefile
import capstone.x86 as x86
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_OP_REG

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import FL_WIN64_DIR  # noqa: E402
GORD = ['rcx', 'rdx', 'r8', 'r9']   # win64 整数引数 slot 順
PE = os.path.join(FL_WIN64_DIR, 'extracted', 'block18983_PE.bin')

GPR = {}
for name, canon in [('RCX', 'rcx'), ('ECX', 'rcx'), ('CX', 'rcx'), ('CL', 'rcx'),
                    ('RDX', 'rdx'), ('EDX', 'rdx'), ('DX', 'rdx'), ('DL', 'rdx'),
                    ('R8', 'r8'), ('R8D', 'r8'), ('R8W', 'r8'), ('R8B', 'r8'),
                    ('R9', 'r9'), ('R9D', 'r9'), ('R9W', 'r9'), ('R9B', 'r9')]:
    GPR[getattr(x86, 'X86_REG_' + name)] = canon
COPYREG = {}
for _nm, _cn in [('RAX', 'rax'), ('RBX', 'rbx'), ('RSI', 'rsi'), ('RDI', 'rdi'),
                 ('R10', 'r10'), ('R11', 'r11'), ('R12', 'r12'), ('R13', 'r13'),
                 ('R14', 'r14'), ('R15', 'r15'), ('RBP', 'rbp')]:
    COPYREG[getattr(x86, 'X86_REG_' + _nm)] = _cn
COPYREG.update(GPR)
for _k in [k for k, v in COPYREG.items() if k in
           (x86.X86_REG_ECX, x86.X86_REG_CX, x86.X86_REG_CL, x86.X86_REG_EDX, x86.X86_REG_DX,
            x86.X86_REG_DL, x86.X86_REG_R8D, x86.X86_REG_R8W, x86.X86_REG_R8B,
            x86.X86_REG_R9D, x86.X86_REG_R9W, x86.X86_REG_R9B)]:
    del COPYREG[_k]
XMM = {}
for i in range(16):
    for suf in ['', 'D', 'Q', 'W', 'B', 'H']:
        try:
            XMM[getattr(x86, 'X86_REG_XMM%d%s' % (i, suf))] = 'xmm%d' % i
        except AttributeError:
            pass


RAXF = {x86.X86_REG_RAX, x86.X86_REG_EAX, x86.X86_REG_AX, x86.X86_REG_AL, x86.X86_REG_AH}


def xmm_read_width(m):
    """xmm 入力 (read-before-write) の読み幅 (bit)。scalar double (*sd: addsd・sqrtsd 等) は 64、scalar single (*ss) は 32 (#3641)。
    cvt 系は変換元の幅で決める: cvtsd2ss・cvtsd2si・cvttsd2si は 64、cvtss2sd・cvtss2si は 32。
    cvtsi2sd・cvtsi2ss は xmm が宛先 (源は GPR) なので従来どおり 32。"""
    if m.startswith('cvt'):
        return 64 if 'sd2' in m else 32
    if m.endswith('sd') or m.startswith(('movq', 'movsd', 'movapd', 'movupd')):
        return 64
    return 32


def ret_slot_of(MD, td, tva, va, fend):
    """戻り値の機械語 slot (#3513)。rax だけ書き xmm0 を書かない → 'rax'。
    xmm0 だけ書き rax を書かず、メモリへの store を持たない (純粋なスカラ結果) → 'xmm0'。
    rax も xmm0 も書かない → 'none' (戻り値を書かない: buffer 出力の kernel など)。
    それ以外 (両方を書く・xmm0 を書いて store を持つ) は 'unknown' (fail-closed)。
    RetDec IR の ret は xmm0 を表さないため、'xmm0' の戻り値は IR 側で判定できない (REPORT_APPENDIX_I §22)。"""
    rax_w = x0_w = store = False
    for i in MD.disasm(td[va - tva:fend - tva], va):
        for o in i.operands:
            if o.type == X86_OP_REG and o.access & 2:
                rax_w |= o.reg in RAXF
                x0_w |= XMM.get(o.reg) == 'xmm0'
            elif o.type == X86_OP_MEM and o.access & 2:
                store = True
    if os.environ.get('K80_NO_RETSLOT') == '1':
        return 'unknown'
    if rax_w and not x0_w:
        return 'rax'
    if x0_w and not rax_w and not store:
        return 'xmm0'
    if not rax_w and not x0_w:
        return 'none'
    return 'unknown'


def load_pe(path):
    pe = pefile.PE(data=open(path, 'rb').read(), fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0].get_data()
    F = {}
    for k in range(len(pd) // 12):
        b, e, u = struct.unpack_from('<III', pd, 12 * k)
        if b and not u & 1:
            F[base + b] = base + e
    tva = [base + s.VirtualAddress for s in pe.sections if s.Name.rstrip(b'\0') == b'.text'][0]
    td = [s.get_data()[:s.Misc_VirtualSize] for s in pe.sections if s.Name.rstrip(b'\0') == b'.text'][0]
    return base, F, tva, td


def scan_function(MD, td, tva, va, fend):
    gpr_arg, xmm_arg = [], []
    gpr_deref = set()
    gpr_base = set()
    gpr_derived = set()
    gpr_idx = set()
    gpr_w, xmm_w = set(), set()
    xmm_width = {}                                         # xmmN -> 32/64 (初回 read 命令から)
    stack_reads = []                                       # (entry_rsp 相対 offset, insn)
    stack_written = set()
    xmm_insns = []                                         # (mnemonic, [(op idx, reg name)])
    scaled_index = False
    clip_index = False                                     # movsx/movzx [base+idx*scale>=2] (負添字 OOB 対策)
    ptr_struct = []                                        # 二重 deref される gpr 引数 slot (0x5e05b0/0x5e02b0)
    sub_rsp = 0
    push_n = 0
    rbp_established = False
    frame_fixed = 0                                        # rbp = entry_rsp - frame_fixed (mov rbp,rsp 時点)
    for i in MD.disasm(td[va - tva:fend - tva], va):
        m = i.mnemonic
        if m == 'push':
            push_n += 1
            continue
        if m == 'pop':
            push_n -= 1
            continue
        if m == 'sub' and i.operands[0].type == X86_OP_REG and i.operands[0].reg == x86.X86_REG_RSP:
            sub_rsp += i.operands[1].imm
        if m == 'add' and i.operands[0].type == X86_OP_REG and i.operands[0].reg == x86.X86_REG_RSP:
            sub_rsp -= i.operands[1].imm
        if m == 'mov' and not rbp_established and len(i.operands) == 2 \
                and i.operands[0].type == X86_OP_REG and i.operands[0].reg == x86.X86_REG_RBP \
                and i.operands[1].type == X86_OP_REG and i.operands[1].reg == x86.X86_REG_RSP:
            rbp_established = True
            frame_fixed = 8 * push_n + sub_rsp
        # 二重 deref 検出: (a) `mov r64, qword ptr [<gpr slot> + 0/8]` (0x5e02b0)
        #                 (b) `mov rX, rY; movsq` の 16B struct コピー (0x5e05b0)
        if m == 'mov' and i.operands[0].type == X86_OP_REG and i.operands[0].size == 8 \
                and len(i.operands) == 2 and i.operands[1].type == X86_OP_MEM \
                and i.operands[1].mem.base in COPYREG and i.operands[1].mem.scale == 1 \
                and i.operands[1].mem.disp in (0, 8) and not i.operands[1].mem.index:
            b = COPYREG[i.operands[1].mem.base]
            if b in GORD and b not in ptr_struct:
                ptr_struct.append(b)
        if m in ('movsx', 'movzx'):
            for o in i.operands:
                if o.type == X86_OP_MEM and o.mem.scale >= 2 and o.mem.index != 0:
                    clip_index = True                       # 添字アクセス: 負の fp 引数 → OOB read
        reads, writes = [], []
        for oi, o in enumerate(i.operands):
            if o.type == X86_OP_REG:
                if o.access & 2:
                    writes.append(o.reg)
                if o.access & 1:
                    reads.append(o.reg)
            elif o.type == X86_OP_MEM:
                if o.mem.base != 0:
                    reads.append(o.mem.base)
                if o.mem.index != 0:
                    reads.append(o.mem.index)
                if o.mem.scale >= 2:
                    scaled_index = True
                if o.mem.base in COPYREG:
                    gpr_deref.add(COPYREG[o.mem.base])
                    # 既に write 済みの引数 reg (0x5e0630: `mov r8, rdx` 後の [r8]) は入力値の deref
                    # ではない。コピー逆伝播の種 (gpr_derived) にのみ入れ、引数 base には数えない (#277)
                    if COPYREG[o.mem.base] in gpr_w and os.environ.get('K80_NO_WRITTEN_BASE') != '1':
                        gpr_derived.add(COPYREG[o.mem.base])
                    else:
                        gpr_base.add(COPYREG[o.mem.base])
                if o.mem.index in COPYREG:
                    gpr_deref.add(COPYREG[o.mem.index])
                    if o.mem.base in COPYREG:
                        gpr_idx.add(COPYREG[o.mem.index])
                if (o.mem.base == x86.X86_REG_RBP and rbp_established) or o.mem.base == x86.X86_REG_RSP:
                    rel = (o.mem.disp - frame_fixed) if o.mem.base == x86.X86_REG_RBP \
                        else (o.mem.disp - 8 * push_n - sub_rsp)
                    if (o.access & 2) and not (o.access & 1) and os.environ.get('K80_NO_STACKW') != '1':
                        stack_written.add(rel)              # 先に書いた home slot の読み戻しは引数ではない
                    if o.access & 1 and rel not in stack_written:   # mem が読み替数のときだけ arg 候補
                        stack_reads.append((rel, i))
        # ゼロ化イディオム (xorps r,r / pxor r,r / xor r,r / subsd r,r): 同一レジスタの
        # read は引数ではない (0 にする write)。read set から除外する (CAB-253)。
        if len(i.operands) == 2 and i.operands[0].type == X86_OP_REG \
                and i.operands[1].type == X86_OP_REG \
                and i.operands[0].reg == i.operands[1].reg \
                and m in ('xorps', 'xorpd', 'pxor', 'xor', 'subsd', 'subss', 'subps'):
            reads = [r for r in reads if r != i.operands[0].reg]
        # helper 対応 xmm 命令の観測 (operand 位置 → レジスタ名)
        regops = [(oi, XMM[o.reg]) for oi, o in enumerate(i.operands)
                  if o.type == X86_OP_REG and o.reg in XMM]
        if regops and (m.startswith('mov') or m.startswith('cvt') or m.startswith('shuf')
                       or m.startswith('unpck') or m.startswith('com') or m.startswith('ucom')
                       or m.startswith('p') or m.endswith('ss') or m.endswith('sd')
                       or m.endswith('ps') or m.endswith('pd')):
            xmm_insns.append((m, regops))
        for r in reads:
            if r in GPR and GPR[r] not in gpr_w and GPR[r] not in gpr_arg:
                gpr_arg.append(GPR[r])
        for r in writes:
            if r in GPR:
                gpr_w.add(GPR[r])
        # movlps/movlpd/movhps/movhpd xmm, mem は片側 64bit のみ load する。capstone は dest を
        # read|write と付けるが、残り半分は引数値ではない (0x5dee90 の xmm0/xmm2 が偽の引数になる, #277)
        if m in ('movlps', 'movlpd', 'movhps', 'movhpd') and len(i.operands) == 2 \
                and i.operands[0].type == X86_OP_REG and i.operands[1].type == X86_OP_MEM \
                and os.environ.get('K80_NO_PARTIAL_LOAD') != '1':
            reads = [r for r in reads if r != i.operands[0].reg]
        for r in reads:
            if r in XMM:
                xn = XMM[r]
                if int(xn[3:]) < 4 and xn not in xmm_w and xn not in xmm_arg:
                    xmm_arg.append(xn)
                    xmm_width[xn] = xmm_read_width(m)
        for r in writes:
            if r in XMM:
                xmm_w.add(XMM[r])
    # reg-reg copy (mov rA, rB) による base/idx/used 伝播 (copy 経由の deref を吸収)
    copies = []
    for i in MD.disasm(td[va - tva:fend - tva], va):
        if i.mnemonic == 'mov' and len(i.operands) == 2 and \
                i.operands[0].type == X86_OP_REG and i.operands[1].type == X86_OP_REG and \
                i.operands[0].reg in COPYREG and i.operands[1].reg in COPYREG:
            copies.append((COPYREG[i.operands[0].reg], COPYREG[i.operands[1].reg]))
    # copy 逆向き伝播 (mov dst, src で dst が base なら src の値も base として
    # 使われ得る — 顺方向は shr 等の変換を挟むため伝播しない)
    direct_base = set(gpr_base)
    for _ in range(8):
        ch = False
        for dst, src in copies:
            if (dst in gpr_base or dst in gpr_derived) and src not in gpr_base:
                gpr_base.add(src)
                ch = True
            if dst in gpr_idx and src not in gpr_idx:
                gpr_idx.add(src)
                ch = True
        if not ch:
            break
    # index として使われる reg (0x5e02b0 の r8: `lea [rcx+r8*4]`) がコピー伝播だけで base 扱いに
    # なったものは個数/添字引数であってポインタではない (#277)
    # 全 kernel に適用すると index と pointer を兼ねる reg (0x5de390 の rcx 等) を落として crash が増える
    # ため、ptr_struct を持つ kernel (record{ptr,ptr} 経由で書く) に限定する。
    if ptr_struct and os.environ.get('K80_NO_IDX_NOT_BASE') != '1':
        gpr_base -= {r for r in gpr_idx if r in GORD and r not in direct_base and r not in ptr_struct}
    # stack args: entry_rsp 相対 offset ≥ 8 (retaddr の上) を read-before-write で
    seen = {}
    for off, ins in stack_reads:
        if off < 8:
            continue
        mn = ins.mnemonic
        isfp = (mn.startswith('fld') or mn.startswith('fild') or mn.endswith('ss') or mn.endswith('sd')) \
            and not mn.startswith('cvtsi')
        w = 32
        if isfp:
            if mn.endswith('sd') or mn.startswith('fld') and 'qword' in ins.op_str:
                w = 64
            op = ins.operands[0] if ins.operands else None
            if op is not None and getattr(op, 'size', 0) in (4, 8) and not mn.startswith('fld'):
                w = op.size * 8
            # cvtss2sd xmm, dword [m] / cvtsd2ss xmm, qword [m]: 幅はニーモニック末尾ではなく
            # メモリオペランドの大きさ (0x5e09f0 の stack 引数は 32bit float, #277)
            if os.environ.get('K80_NO_MEMW') != '1' and not mn.startswith('fld'):
                mo = [o for o in ins.operands if o.type == X86_OP_MEM and getattr(o, 'size', 0) in (4, 8)]
                if mo:
                    w = mo[0].size * 8
        if off not in seen:
            seen[off] = (isfp, w, ins.mnemonic, ins.op_str)
    # movsq (16B struct コピー) からの二重 deref: 直前 4 命令の `mov rX, <gpr slot>`
    ins_list = list(MD.disasm(td[va - tva:fend - tva], va))
    for k, i in enumerate(ins_list):
        if i.mnemonic == 'movsq':
            for j in range(max(0, k - 4), k):
                p = ins_list[j]
                if p.mnemonic == 'mov' and len(p.operands) == 2 \
                        and p.operands[0].type == X86_OP_REG and p.operands[1].type == X86_OP_REG \
                        and p.operands[1].reg in COPYREG:
                    b = COPYREG[p.operands[1].reg]
                    if b in GORD and b not in ptr_struct:
                        ptr_struct.append(b)
    return gpr_arg, xmm_arg, sorted(gpr_deref), sorted(gpr_base), sorted(gpr_idx), xmm_width, seen, \
        xmm_insns, scaled_index, clip_index, ptr_struct


def main():
    outp = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'work', 'k80abi.json')
    cl = json.load(open(os.path.join(HERE, 'work', 'f80_classes.json')))
    vas = sorted(int(r['va'], 16) for r in cl['kernels'])
    base, F, tva, td = load_pe(PE)
    MD = Cs(CS_ARCH_X86, CS_MODE_64)
    MD.detail = True
    out = {}
    for va in vas:
        g, x, gd, gb, gx, xw, st, xins, sci, cli, ps = scan_function(MD, td, tva, va, F[va])
        out[hex(va)] = {'gpr_slots': g, 'gpr_base': gb, 'gpr_idx': gx, 'xmm_slots': x, 'xmm_width': xw,
                        'stack': [{'off': k, 'fp': v[0], 'width': v[1], 'insn': v[2]}
                                  for k, v in sorted(st.items())],
                        'xmm_insns': [[m, regops] for m, regops in xins],
                        'scaled_index': sci, 'clip_index': cli, 'ptr_struct': ps,
                        'ret_slot': ret_slot_of(MD, td, tva, va, F[va])}
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    json.dump(out, open(outp, 'w'), indent=1)
    print('[k80abi] kernels=%d -> %s' % (len(out), outp))
    slots = collections.Counter(v['ret_slot'] for v in out.values())
    print('  ret_slot=%s xmm0=%s' % (dict(slots), [k for k in sorted(out) if out[k]['ret_slot'] == 'xmm0']))
    for va in ('0x5de3e0', '0x5de820', '0x5dfbe0', '0x5e03f0', '0x5dfa40'):
        a = out[va]
        print(' ', va, 'gpr=%s xmm=%s(w=%s) stack=%s' % (
            a['gpr_slots'], a['xmm_slots'], a['xmm_width'],
            [(x['off'], 'fp%d' % x['width'] if x['fp'] else 'i%d' % x['width']) for x in a['stack']]))


if __name__ == '__main__':
    main()
