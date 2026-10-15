#!/usr/bin/env python3
"""#3574: strict 証拠表の行 255・270・271 の判定材料を出す (判定はしない。SSA の同一性は人が確かめる)。

- 行 270・271: jcc (脱出 T) の前の機械語の間接 call (`call qword ptr [reg+N]`) と、IR の帰属ブロック B・
  ループ先頭 L・脱出先 T の終端・preds を出す。IR に入口判定 (B から L へ入る条件分岐) が無いことを見る。
- 行 255: 入口判定 (機械語の最初の jle) と jg の間の call の遷移先と、その書込み先 (メモリ書込みの宛先)。
  直接 call は再帰的に辿り、負の対照として既知の書込み (1060d20 の [rbx+0x48]) が検出されることを示す。
使い方: LD_M11_PE=<block00031_PE.bin> python3 judge_3574.py <IR.ll> <evidence.tsv>
"""
import csv
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'ldfix'))
from ldmach import Machine  # noqa: E402
from capstone.x86 import X86_OP_MEM  # noqa: E402

ROWS = (255, 270, 271)
WRITE_MNEM = {'mov', 'add', 'sub', 'and', 'or', 'xor', 'adc', 'sbb', 'inc', 'dec', 'neg', 'not',
              'shl', 'shr', 'sar', 'rol', 'ror', 'xchg', 'movsd', 'movss', 'movq', 'movd'}


def fn_body(text, name):
    m = re.search(r'^define [^@\n]*@%s\(' % re.escape(name), text, re.M)
    end = text.index('\n}', m.end()) + 2
    return text[m.start():end]


def ir_blocks(body):
    blocks, cur = {}, None
    for ln in body.split('\n'):
        m = re.match(r'^([A-Za-z0-9_.]+):', ln)
        if m:
            cur = m.group(1)
            blocks[cur] = []
        elif cur is not None:
            blocks[cur].append(ln)
    return blocks


def ir_preds(blocks, name):
    return [bn for bn, lines in blocks.items() if any(('label %' + name) in x for x in lines)]


def writes(cs, ins):
    """メモリを宛先 (operand 0) とする命令: (addr, mnem, base, disp)。"""
    out = []
    for x in ins:
        if x.mnemonic not in WRITE_MNEM or not x.operands:
            continue
        op = x.operands[0]
        if op.type == X86_OP_MEM:
            out.append((x.address, x.mnemonic, cs.reg_name(op.mem.base), op.mem.disp))
    return out


def direct_callees(ins):
    return [(x.address, int(x.op_str, 16)) for x in ins
            if x.mnemonic == 'call' and x.op_str.startswith('0x')]


def closure_writes(m, va, depth=0, seen=None):
    seen = set() if seen is None else seen
    if va in seen or depth > 4:
        return []
    seen.add(va)
    ins = m.disasm_fn(va) or []
    res = [(va, w) for w in writes(m.cs, ins)]
    for _, callee in direct_callees(ins):
        res += closure_writes(m, callee, depth + 1, seen)
    return res


def slot_info(m, pef, ins, call_addr):
    """間接 call の直前の `mov reg, [rip+X]` を見て、スロットの VA・所属セクション・静的な値を出す。"""
    base = pef.OPTIONAL_HEADER.ImageBase
    prev = [x for x in ins if x.address < call_addr][-1]
    if '[rip' not in prev.op_str:
        return 'slot 未特定 (直前: %s %s)' % (prev.mnemonic, prev.op_str)
    disp = int(re.search(r'\[rip \+ (0x[0-9a-f]+)\]', prev.op_str).group(1), 16)
    slot = prev.address + prev.size + disp
    sec = next((s.Name.rstrip(b'\0').decode() for s in pef.sections
                if base + s.VirtualAddress <= slot < base + s.VirtualAddress + s.Misc_VirtualSize), '?')
    try:
        val = struct.unpack('<Q', pef.get_data(slot - base, 8))[0]
        st = '静的な値 0x%x' % val
    except Exception:
        st = '静的な値なし'
    return 'slot 0x%x (%s・%s)' % (slot, sec, st)


def main():
    import pefile
    ir, tsv = sys.argv[1], sys.argv[2]
    m = Machine(os.environ['LD_M11_PE'])
    pef = pefile.PE(os.environ['LD_M11_PE'], fast_load=True)
    text = open(ir, errors='replace').read()
    rows = list(csv.DictReader(open(tsv), delimiter='\t'))
    for i in ROWS[1:]:
        r = rows[i - 1]
        va = int(r['fn'][len('function_'):], 16)
        jcc = int(r['jcc'], 16)
        ins = m.disasm_fn(va)
        k = next(j for j, x in enumerate(ins) if x.address == jcc)
        print('=' * 100)
        print('#%d %s jcc=%s %s -> T=%s L=%s B=%s' % (i, r['fn'], r['jcc'], r['mnemonic'], r['target'], r['loop_head'], r['block']))
        print('-- MACH 直前 8 命令 ～ jcc 後 1 命令')
        for x in ins[max(0, k - 8):k + 2]:
            print('  %x: %s %s%s' % (x.address, x.mnemonic, x.op_str, '  <== jcc' if x.address == jcc else ''))
        print('-- MACH jcc より前の call (間接は [ ] を含む)')
        n_ind = 0
        for x in ins[:k]:
            if x.mnemonic == 'call':
                ind = '[' in x.op_str
                n_ind += ind
                print('  %x: call %s%s' % (x.address, x.op_str, '  (間接)' if ind else ''))
        print('  間接 call %d 件' % n_ind)
        body = fn_body(text, r['fn'])
        blocks = ir_blocks(body)
        B = 'dec_label_pc_' + r['block'].replace('dec_label_pc_', '')
        L = 'dec_label_pc_%s' % r['loop_head']
        T = 'dec_label_pc_%s' % r['target']
        print('-- IR B (%s) 全行' % B)
        for x in blocks.get(B, []):
            if x.strip():
                print('   ' + x)
        print('-- IR 終端 B: %s' % [x for x in blocks.get(B, []) if x.strip()][-1].strip())
        print('-- IR preds(L) = %s' % ir_preds(blocks, L))
        print('-- IR preds(T) = %s' % ir_preds(blocks, T))
        print('-- IR T の全行 (先頭 6)')
        for x in [y for y in blocks.get(T, []) if y.strip()][:6]:
            print('   ' + x)
    print('=' * 100)
    print('#255 %s 入口判定と jg の間の呼出し' % rows[254]['fn'])
    r = rows[254]
    va = int(r['fn'][len('function_'):], 16)
    ins = m.disasm_fn(va)
    jg = int(r['jcc'], 16)
    jle = next(x for x in ins if x.mnemonic == 'jle' and x.address < jg)
    print('-- MACH 入口判定: %x: %s %s (jle の前は cmp)' % (jle.address, jle.mnemonic, jle.op_str))
    for x in ins:
        if jle.address < x.address < jg and x.mnemonic == 'call':
            tag = '(間接)' if '[' in x.op_str else ''
            print('-- call %x: %s %s %s' % (x.address, x.mnemonic, x.op_str, tag))
            if '[' in x.op_str:
                print('     遷移先: %s' % slot_info(m, pef, ins, x.address))
            else:
                callee = int(x.op_str, 16)
                cw = closure_writes(m, callee)
                print('     到達可能な書込み (直接 call を再帰): %d 件' % len(cw))
                for fva, (a, mn, base, disp) in cw:
                    print('       in %x: %x %s [%s + 0x%x]' % (fva, a, mn, base, disp))
    print('-- 負の対照: 1060d20 の [rbx+0x48] 書込み (既知) が検出されること')
    known = [w for w in closure_writes(m, 0x1060d20) if w[1][3] == 0x48]
    print('   disp=0x48 の書込み %d 件 (期待 2)' % len(known))
    print('-- 判定対象のオフセット 0x14 ([arg1+20]) への書込み (到達可能な全関数):')
    hits = [w for w in closure_writes(m, 0x1060d20) if w[1][3] == 0x14]
    print('   %d 件' % len(hits))


if __name__ == '__main__':
    main()
