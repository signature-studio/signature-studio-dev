#!/usr/bin/env python3
"""triage_ld111.py — #2396 (LD-111): audit_lsf_disp の SUSPECT (VA:argN:c) を機械語から突合する (audit とは別算法)。

audit_lsf_disp は CFG 不動点の記号実行 (mov の load 値だけ)。本スクリプトは関数の線形 disasm を 1 回なめる単純な追跡で、
reg / frame slot を `argN + off` として持ち、`argN + c` を実効アドレスに持つ**全てのメモリオペランド**を列挙する
(mov 以外の命令・文字列転送 movs の暗黙オペランドを含む)。ラベル (分岐先) では reg の追跡を捨てる (frame の home は残す)。

  LSF     機械語に argN+c を読み、その値を非 frame のメモリへ書く命令がある (文字列転送 movs、または `mov r,[..]` の r を `mov [m],r` で書く)
          → IR の `load (argN+c)` → store は機械語にある操作で、audit の列挙漏れ (誤検出)
  READ    argN+c を読む命令はあるが、その値は非 frame のメモリへ書かれない (他の用途) → IR の store 値は機械語の値と別物 (wrong-value, 41a670 型)
  NONE    argN+c を実効アドレスとする命令が無い → 同上 (wrong-value)

使い方: python3 triage_ld111.py IMAGE.bin 'CONFIG_GLOB' VA:ARG:C [VA:ARG:C ...] [--pe PE]    (例 41a670:1:8  6677a0:2:36)
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ldmach import Machine, norm_reg  # noqa: E402
from ldmach_img import ImageMachine  # noqa: E402
import capstone  # noqa: E402

REG_NAMES = {'rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'rbp', 'rsp', 'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15',
             'eax', 'ebx', 'ecx', 'edx', 'esi', 'edi', 'r8d', 'r9d', 'r10d', 'r11d', 'r12d', 'r13d', 'r14d', 'r15d'}
ARGREG = {'rcx': 1, 'rdx': 2, 'r8': 3, 'r9': 4}
VOLATILE = ('rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11')


def linear(mach, va):
    ent = mach.fns.get(va)
    data = mach.read(ent[0], ent[1])
    return list(mach.cs.disasm(data, va))


def sweep(mach, va):
    """[(addr, text, kind, n, off, size)] kind = 'R'|'W'。(n, off) = 実効アドレスが argN+off のメモリアクセス。"""
    cs = mach.cs
    ins = linear(mach, va)
    targets = set()
    for i in ins:
        if (i.mnemonic == 'jmp' or i.mnemonic.startswith('j')) and i.operands and i.operands[0].type == capstone.CS_OP_IMM:
            targets.add(i.operands[0].imm)
    reg = {r: (n, 0) for r, n in ARGREG.items()}
    slot = {}
    out = []

    def val(base):
        return reg.get(norm_reg(cs, base)) if base else None

    for i in ins:
        if i.address in targets:
            reg.clear()
        mn, ops = i.mnemonic, i.operands
        acc = []
        if mn.startswith('movs') and len(ops) == 2 and all(o.type == capstone.CS_OP_MEM for o in ops) and not any(p in (0xf2, 0xf3) for p in i.prefix):
            w = ops[1].size
            for r, k in (('rsi', 'R'), ('rdi', 'W')):
                if r in reg:
                    acc.append((k, reg[r][0], reg[r][1], w))
            for r in ('rsi', 'rdi'):
                if r in reg:
                    reg[r] = (reg[r][0], reg[r][1] + w)
            out += [(i.address, '%s %s' % (mn, i.op_str)) + a for a in acc]
            continue
        for mi, o in enumerate(ops):
            if o.type != capstone.CS_OP_MEM or mn == 'lea' or o.mem.index or not o.mem.base:
                continue
            bn = norm_reg(cs, o.mem.base)
            if bn in ('rbp', 'rsp') or cs.reg_name(o.mem.base) == 'rip':
                continue
            v = val(o.mem.base)
            if v:
                is_w = (mi == 0 and mn not in ('cmp', 'test', 'bt')) or mn in ('xchg',)
                out.append((i.address, '%s %s' % (mn, i.op_str), 'W' if is_w else 'R', v[0], v[1] + o.mem.disp, o.size))
        new = None
        dest = None
        if mn == 'mov' and len(ops) == 2 and ops[0].type == capstone.CS_OP_REG:
            dest = norm_reg(cs, ops[0].reg)
            if ops[1].type == capstone.CS_OP_REG and ops[0].size == 8 and ops[1].size == 8:
                new = reg.get(norm_reg(cs, ops[1].reg))
            elif ops[1].type == capstone.CS_OP_MEM and not ops[1].mem.index and ops[1].mem.base and ops[0].size == 8:
                bn = norm_reg(cs, ops[1].mem.base)
                if bn in ('rbp', 'rsp'):
                    new = slot.get((bn, ops[1].mem.disp))
        elif mn == 'mov' and len(ops) == 2 and ops[0].type == capstone.CS_OP_MEM and ops[1].type == capstone.CS_OP_REG and not ops[0].mem.index and ops[0].mem.base:
            bn = norm_reg(cs, ops[0].mem.base)
            if bn in ('rbp', 'rsp'):
                v = reg.get(norm_reg(cs, ops[1].reg))
                if v and ops[0].size == 8:
                    slot[(bn, ops[0].mem.disp)] = v
                else:
                    slot.pop((bn, ops[0].mem.disp), None)
        elif mn == 'lea' and len(ops) == 2 and ops[1].type == capstone.CS_OP_MEM and not ops[1].mem.index and ops[1].mem.base:
            dest = norm_reg(cs, ops[0].reg)
            v = val(ops[1].mem.base)
            new = (v[0], v[1] + ops[1].mem.disp) if v else None
        if mn == 'call':
            for r in VOLATILE:
                reg.pop(r, None)
        else:
            try:
                wr = i.regs_access()[1]
            except Exception:
                wr = ()
            for rid in wr:
                r = norm_reg(cs, rid)
                if r:
                    reg.pop(r, None)
        if dest and new:
            reg[dest] = new
    return out


def stored_after(mach, va, addr):
    """`mov r,[..]` (addr) の r が、r を壊す/分岐/call/ret に当たる前に `mov [非 frame],r (またはそのコピー)` で書かれるか。"""
    cs = mach.cs
    ins = linear(mach, va)
    k = next(j for j, i in enumerate(ins) if i.address == addr)
    live = {norm_reg(cs, ins[k].operands[0].reg)}
    for i in ins[k + 1:]:
        mn, ops = i.mnemonic, i.operands
        if mn in ('call', 'ret', 'retn') or mn.startswith('j'):
            return False
        if mn == 'mov' and len(ops) == 2 and ops[0].type == capstone.CS_OP_MEM and ops[1].type == capstone.CS_OP_REG \
                and norm_reg(cs, ops[1].reg) in live and ops[0].mem.base:
            if norm_reg(cs, ops[0].mem.base) not in ('rbp', 'rsp'):
                return True
        if mn == 'mov' and len(ops) == 2 and ops[0].type == capstone.CS_OP_REG and ops[1].type == capstone.CS_OP_REG \
                and norm_reg(cs, ops[1].reg) in live and ops[0].size == 8:
            live.add(norm_reg(cs, ops[0].reg))
            continue
        try:
            wr = {norm_reg(cs, r) for r in i.regs_access()[1]}
        except Exception:
            wr = set()
        live -= wr
        if not live:
            return False
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('image')
    ap.add_argument('cfg')
    ap.add_argument('targets', nargs='+')
    ap.add_argument('--pe')
    a = ap.parse_args()
    mach = Machine(a.pe) if a.pe else ImageMachine(a.image, a.cfg)
    for t in a.targets:
        va_s, n_s, c_s = t.split(':')
        va, n, c = int(va_s, 16), int(n_s), int(c_s)
        acc = [x for x in sweep(mach, va) if x[3] == n and x[4] == c]
        rows = []
        for (ad, txt, k, _n, _off, w) in acc:
            if k == 'R' and txt.startswith('movs'):
                st = True
            elif k == 'R' and txt.startswith('mov ') and txt.split(',')[0].split()[1] in REG_NAMES:
                st = stored_after(mach, va, ad)
            else:
                st = False
            rows.append((ad, txt, k, w, st))
        verdict = 'LSF' if any(r[2] == 'R' and r[4] for r in rows) else ('READ' if any(r[2] == 'R' for r in rows) else 'NONE')
        print('%s arg%d+%d: %s' % (va_s, n, c, verdict))
        for (ad, txt, k, w, st) in rows:
            print('   %x  %s  %s (%dB)%s' % (ad, k, txt, w, '  → 値を非 frame メモリへ store' if (k == 'R' and st) else ('  (書き込み)' if k == 'W' else '')))


if __name__ == '__main__':
    main()
