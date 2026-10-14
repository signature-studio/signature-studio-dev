#!/usr/bin/env python3
"""xmm0_origin.py FN_VA [--dsm PATH] [--end VA]
ICALL-79 (#2674): RetDec の dsm (work/rt_freshair-core/before.0.drc.dsm) から FN_VA の機械語を読み、
capstone で線形に復号して、xmm0 を書く命令・call・ret を列挙する。
各命令に dsm 上の区分を付ける: `fn` = `; function:` 区分、`data` = `; data inside code section` 区分。
`data` 区分の命令は RetDec が data と判定したため IR (after.0.restored.ll) に載らない候補。
範囲は FN_VA から次の `; function:` ラベルの直前まで (--end で上書き可)。"""
import sys, re, bisect
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

HEX = re.compile(r'^(0x[0-9a-f]+):\s+([0-9a-f ]+?)\s*[|\t]')


def load_dsm(path):
    mem, sect = {}, []
    for line in open(path, errors='replace'):
        m = HEX.match(line)
        if m:
            base = int(m.group(1), 16)
            for i, tok in enumerate(m.group(2).split()):
                mem[base + i] = int(tok, 16)
            continue
        if line.startswith('; function:'):
            m = re.search(r'at (0x[0-9a-f]+) -- (0x[0-9a-f]+)', line)
            sect.append((int(m.group(1), 16), 'fn'))
        elif line.startswith('; data inside code section'):
            m = re.search(r'at (0x[0-9a-f]+) --', line)
            sect.append((int(m.group(1), 16), 'data'))
    return mem, sorted(sect)


def scan(mem, sect, starts, md, fn, end, depth, seen):
    code = bytes(mem.get(a, 0xcc) for a in range(fn, end))
    print(f'# {"  " * depth}{hex(fn)} .. {hex(end)} ({end - fn} B)')
    callees = []
    for ins in md.disasm(code, fn):
        j = bisect.bisect_right(starts, ins.address) - 1
        sec = sect[j][1] if j >= 0 else 'fn'
        w = [ins.reg_name(r) for r in ins.regs_access()[1]] if ins.regs_access() else []
        mark = []
        if 'xmm0' in w:
            mark.append('WRITE xmm0')
        if ins.mnemonic in ('call', 'ret'):
            mark.append(ins.mnemonic)
        if ins.mnemonic in ('call', 'jmp') and ins.operands and ins.operands[0].type == 2:
            callees.append(ins.operands[0].imm)
        if mark:
            print(f'{"  " * depth}{ins.address:#x} [{sec:4}] {ins.mnemonic:8} {ins.op_str:<32} {" ".join(mark)}')
    if depth >= MAX_DEPTH:
        return
    for t in callees:
        if t in seen or t not in starts:
            continue
        seen.add(t)
        nxt = [s for s, k in sect if s > t and k == 'fn']
        scan(mem, sect, starts, md, t, nxt[0] if nxt else t + 0x400, depth + 1, seen)


MAX_DEPTH = 0


def main():
    global MAX_DEPTH
    fn = int(sys.argv[1], 16)
    dsm = sys.argv[sys.argv.index('--dsm') + 1] if '--dsm' in sys.argv else None
    if dsm is None:
        import os
        dsm = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'work', 'rt_freshair-core', 'before.0.drc.dsm')
    MAX_DEPTH = int(sys.argv[sys.argv.index('--depth') + 1]) if '--depth' in sys.argv else 0
    mem, sect = load_dsm(dsm)
    starts = [s for s, _ in sect]
    end = int(sys.argv[sys.argv.index('--end') + 1], 16) if '--end' in sys.argv else None
    if end is None:
        nxt = [s for s, k in sect if s > fn and k == 'fn']
        end = nxt[0] if nxt else fn + 0x400
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    print(f'# dsm={dsm}')
    scan(mem, sect, starts, md, fn, end, 0, {fn})


if __name__ == '__main__':
    main()
