#!/usr/bin/env python3
"""MX-61 (#5656): 関数入口の xmm2 (呼出元の値) が、経路上で読まれるかを見る。

forward に経路を辿る (jmp/jcc を追う・ret で止める)。入口の xmm2 がまだ上書きされていない状態を
「entry」とし、次の 3 つを記録する:
  read:  entry の xmm2 を読む命令 (capstone の regs_read に xmm2 を含む)
  pass:  entry の xmm2 が残ったまま call する箇所 (引数として渡りうる)。直接 call の callee は DEPTH 段まで同じ判定をする
  write: xmm2 を上書きする命令 (以降の経路は entry でなくなる)。call は Win64 の揮発レジスタとして
         xmm2 を上書きするものとみなす
範囲外 (pdata 不正・間接 call/jmp) は unknown に数える。

usage: mx61_entry_xmm2_paths.py <pe> <entry_rva_hex> [<entry_rva_hex> ...]
"""
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM

BUDGET = 6000
DEPTH = 2


def main(pe_path, entries):
    pe = pefile.PE(pe_path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(pe_path, 'rb').read()
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True

    def off(rva):
        for s in pe.sections:
            if s.VirtualAddress <= rva < s.VirtualAddress + s.Misc_VirtualSize:
                return s.PointerToRawData + rva - s.VirtualAddress
        return None

    def analyze(rva, depth, seen):
        res = {'read': [], 'pass': [], 'unknown': [], 'truncated': False}
        o = off(rva)
        if o is None:
            res['unknown'].append(('no section', hex(base + rva)))
            return res
        cache = {}

        def insn_at(r):
            if r in cache:
                return cache[r]
            oo = off(r)
            ins = None
            if oo is not None:
                for i in md.disasm(data[oo:oo + 16], base + r):
                    ins = i
                    break
            cache[r] = ins
            return ins

        work = [(rva, True)]
        state = {}
        budget = BUDGET
        while work:
            r, entry = work.pop()
            key = (r, entry)
            if key in state:
                continue
            state[key] = True
            while True:
                budget -= 1
                if budget <= 0:
                    res['truncated'] = True
                    break
                ins = insn_at(r)
                if ins is None:
                    res['unknown'].append(('undecodable', hex(base + r)))
                    break
                rr = [md.reg_name(x) for x in ins.regs_read]
                ww = [md.reg_name(x) for x in ins.regs_write]
                a = base + r
                if entry and 'xmm2' in rr and ins.mnemonic not in ('call',):
                    res['read'].append((hex(a), ins.mnemonic, ins.op_str))
                nxt = r + ins.size
                m = ins.mnemonic
                if m.startswith('call'):
                    if entry:
                        tgt = ins.operands[0] if ins.operands else None
                        if tgt is not None and tgt.type == X86_OP_IMM:
                            t = tgt.imm - base
                            if t in seen:
                                res['pass'].append((hex(a), hex(tgt.imm), 'recursive'))
                            elif depth > 0:
                                sub = analyze(t, depth - 1, seen | {t})
                                res['pass'].append((hex(a), hex(tgt.imm), 'callee read=%d unknown=%d' % (len(sub['read']), len(sub['unknown']))))
                                if sub['read']:
                                    res['read'].append((hex(a), 'call->' + hex(tgt.imm), sub['read'][0][0]))
                                if sub['unknown'] or sub['truncated']:
                                    res['unknown'].append(('callee unresolved', hex(a), hex(tgt.imm)))
                            else:
                                res['unknown'].append(('depth-limit', hex(a), hex(tgt.imm)))
                        else:
                            res['pass'].append((hex(a), ins.op_str, 'indirect'))
                    # Win64: call clobbers xmm2 (volatile)
                    entry = False
                    r = nxt
                    continue
                if m == 'int3' and entry:
                    res['unknown'].append(('entry is padding int3', hex(a)))
                    break
                if m in ('ret', 'retn', 'int3', 'ud2'):
                    break
                if m == 'jmp':
                    tgt = ins.operands[0]
                    if tgt.type == X86_OP_IMM:
                        t = tgt.imm - base
                        if off(t) is not None:
                            r = t
                            continue
                    res['unknown'].append(('indirect jmp', hex(a)))
                    break
                if m.startswith('j'):
                    tgt = ins.operands[0]
                    if tgt.type == X86_OP_IMM:
                        t = tgt.imm - base
                        work.append((t, entry))
                if 'xmm2' in ww and m != 'vzeroupper':
                    entry = False
                r = nxt
        return res

    for e in entries:
        rva = int(e, 16) - base
        res = analyze(rva, DEPTH, {rva})
        print('== entry %s (RVA %s)' % (hex(base + rva), hex(rva)))
        print('  read (entry xmm2 を読む命令): %d' % len(res['read']))
        for x in res['read'][:20]:
            print('    ', x)
        print('  pass (entry xmm2 が残ったまま call): %d' % len(res['pass']))
        for x in res['pass'][:20]:
            print('    ', x)
        print('  unknown: %d' % len(res['unknown']))
        for x in res['unknown'][:10]:
            print('    ', x)
        print('  budget 超過: %s' % res['truncated'])


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2:])
