#!/usr/bin/env python3
# callee_closure_5655.py: #5655 (LD-282) 449550 の呼び先 40f910・4493b0 の閉包 (direct call の推移閉包) を機械語から列挙する。
# 使い方: python3 callee_closure_5655.py <block00031_PE.bin> [深さ上限]
# 出力: 関数ごとの direct call / indirect call / RIP 相対 store 先 (セクション名つき) / フラグ
#       (VA 0x15cb0c4・0x15cb024、.data) への参照 / rsp・rbp 基底の store 数 / ポインタ経由の store。
# 限界: 関数末尾は int3 パディングまたは 0x1000 バイトで区切る近似。間接 store の先は解決しない。
import sys
import capstone
import pefile

ROOTS = [0x40f910, 0x4493b0]
FLAGS = {0x15cb0c4, 0x15cb024}  # 絶対 VA (.data)。issue の 0x11cb0c4 は RVA 表記で、VA は ImageBase 0x400000 を足した 0x15cb0c4
DEPTH = int(sys.argv[2]) if len(sys.argv) > 2 else 6

pe = pefile.PE(sys.argv[1], fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
secs = [(base + s.VirtualAddress, base + s.VirtualAddress + s.Misc_VirtualSize,
         s.Name.rstrip(b'\0').decode()) for s in pe.sections]
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
X86 = capstone.x86


def sec(va):
    for lo, hi, n in secs:
        if lo <= va < hi:
            return n
    return '?'


def body(va):
    out = []
    for i in md.disasm(pe.get_data(va - base, 0x8000), va):
        if i.mnemonic == 'int3':
            break
        out.append(i)
    return out


def is_store(i):
    return i.mnemonic in ('mov', 'movzx', 'movsx', 'movsxd', 'add', 'sub', 'or', 'and', 'xor',
                          'lock xadd', 'xadd', 'xchg', 'inc', 'dec', 'neg', 'not', 'cmpxchg') \
        and i.operands and i.operands[0].type == X86.X86_OP_MEM


seen = {}
queue = [(r, 0) for r in ROOTS]
while queue:
    fn, d = queue.pop(0)
    if fn in seen:
        continue
    ins = body(fn)
    direct = [i.operands[0].imm for i in ins
              if i.mnemonic == 'call' and i.operands and i.operands[0].type == X86.X86_OP_IMM]
    indirect = [i.op_str for i in ins
                if i.mnemonic == 'call' and not (i.operands and i.operands[0].type == X86.X86_OP_IMM)]
    stores, flag_hits, frame_st, ptr_st = [], [], 0, []
    for i in ins:
        for op in i.operands:
            if op.type == X86.X86_OP_MEM and op.mem.base == X86.X86_REG_RIP:
                t = i.address + i.size + op.mem.disp
                if t in FLAGS:
                    flag_hits.append(hex(i.address))
        if not is_store(i):
            continue
        m = i.operands[0].mem
        if m.base == X86.X86_REG_RIP:
            t = i.address + i.size + m.disp
            stores.append((hex(i.address), hex(t), sec(t)))
        elif m.base in (X86.X86_REG_RSP, X86.X86_REG_RBP):
            frame_st += 1
        else:
            ptr_st.append((hex(i.address), i.mnemonic, i.op_str))
    seen[fn] = (direct, indirect, stores, flag_hits, (frame_st, ptr_st), d)
    if d < DEPTH:
        for c in direct:
            if c not in seen:
                queue.append((c, d + 1))

for fn, (direct, indirect, stores, flag_hits, (frame_st, ptr_st), d) in sorted(seen.items()):
    print('== %s depth=%d direct=%s indirect=%s' % (hex(fn), d,
          [hex(c) for c in direct], indirect or 'none'))
    print('   RIP-global store: %s' % (stores or 'none'))
    print('   issue-flag refs: %s   frame(rsp/rbp) stores: %d   pointer stores: %s'
          % (flag_hits or 'none', frame_st, ptr_st or 'none'))
