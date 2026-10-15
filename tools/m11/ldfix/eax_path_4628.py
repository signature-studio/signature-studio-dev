#!/usr/bin/env python3
# eax_path_4628.py: #4628 (LD-228) — F3d 型タグ読み W (movzx eax, word [arg1]) の値が、
# 後続の述語 jcc の入口 (45d381・45f824) まで eax のまま保たれるかを機械語で全経路検査する。
# 規則: 読み込み後の経路を辿り、eax/rax/ax を書く命令 (call を含む) を通ったら汚染とする。
# 出力: 入口に汚染なし経路のみで到達すれば clean、汚染経路でも到達すれば DIRTY。窓外への経路は件数を出す。
# 使い方: python3 tools/m11/ldfix/eax_path_4628.py "$FL_WIN64_DIR/extracted/block00031_PE.bin"
import sys
from collections import deque
import capstone
import pefile

pe = pefile.PE(sys.argv[1], fast_load=True)
BASE = pe.OPTIONAL_HEADER.ImageBase
MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)


def decode(lo, hi):
    return {i.address: i for i in MD.disasm(pe.get_data(lo - BASE, hi - lo), lo)}


def writes_rax(i):
    if i.mnemonic == 'call':
        return True
    if i.mnemonic in ('cmp', 'test', 'push', 'ret', 'nop') or i.mnemonic.startswith('j'):
        return False
    dst = i.op_str.split(',')[0].strip() if i.op_str else ''
    return dst in ('eax', 'rax', 'ax', 'al')


def reach(ins, start, target):
    seen, q, out, hit = set(), deque([(start, 0)]), 0, set()
    while q:
        a, c = q.popleft()
        if (a, c) in seen:
            continue
        seen.add((a, c))
        if a == target:
            hit.add(c)
            continue
        if a not in ins:
            out += 1
            continue
        i = ins[a]
        c2 = 1 if writes_rax(i) else c
        if i.mnemonic == 'ret':
            continue
        if i.mnemonic == 'jmp':
            q.append((int(i.op_str, 16), c2))
            continue
        if i.mnemonic.startswith('j'):
            q.append((int(i.op_str, 16), c2))
            q.append((a + i.size, c2))
            continue
        q.append((a + i.size, c2))
    return hit, out


def check(name, lo, hi, start, target):
    ins = decode(lo, hi)
    hit, out = reach(ins, start, target)
    if not hit:
        verdict = 'UNREACHABLE'
    elif 1 in hit:
        verdict = 'DIRTY (eax 書換え経路あり)'
    else:
        verdict = 'clean (全経路で eax = W のまま)'
    print('%s: 0x%x -> 0x%x: %s' % (name, start, target, verdict))
    if out:
        print('  注意: 窓外への経路 %d 本 (窓 0x%x-0x%x)' % (out, lo, hi))


check('45d0a0', 0x45d0a0, 0x45d700, 0x45d0b9, 0x45d381)
check('45f560', 0x45f560, 0x45fc00, 0x45f570, 0x45f824)
