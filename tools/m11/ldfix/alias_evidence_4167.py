#!/usr/bin/env python3
"""alias_evidence_4167.py — 694c80・c3b340 の LEAK_STORE 2 site の別名判定の機械語証拠 (#4167 / 親 #3225 子 B)。

判定器 audit_frame_store_alias_2211.py は変更しない。この script は、LEAK_STORE になった store の
基底レジスタの値の出どころを機械語から追い、次を出力する:
  - 基底レジスタ R の、store より前の直近の書き込み (CFG の逆向き探索)
  - R が frame の slot [rbp+X] の読み (mov R, [rbp+X]) なら、その slot への全書き込みと読み
  - その slot の値が入り得る経路で、呼び出し先に frame の address が渡ったか (lea rbp/rsp・F 派生の call 引数)
  - frame の address を frame 自身に書く store (mov [rbp+X], rbp) が、読まれる slot か

使い方: python3 alias_evidence_4167.py PE.bin OUT.json
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capstone  # noqa: E402
from ldmach import Machine  # noqa: E402
import audit_frame_store_verdict as v1  # noqa: E402
import audit_frame_store_alias_2211 as a2211  # noqa: E402

TARGETS = [('694c80', 0x695163), ('c3b340', 0xc3b3f5)]
ENTRY_ARGS = ('rcx', 'rdx', 'r8', 'r9')


def ins_str(x):
    return '%x %s %s' % (x.address, x.mnemonic, x.op_str)


def reg_written_by(cs, x, reg):
    ops = x.operands
    if not ops or ops[0].type != capstone.CS_OP_REG or not a2211.writes_dst(x.mnemonic):
        return False
    return a2211.rname(cs, ops[0].reg) == reg


def mem_rbp_disp(cs, x):
    """命令が書くか読むかに関係なく、最初に現れる [rbp+d] / [rsp+d] のオペランドを (base, disp, size)。"""
    out = []
    for op in x.operands:
        if op.type == capstone.CS_OP_MEM and op.mem.base:
            b = a2211.rname(cs, op.mem.base)
            if b in ('rbp', 'rsp') and not op.mem.index:
                out.append((b, op.mem.disp, op.size or 8))
    return out


def analyze(mach, fn, store_addr):
    cs = mach.cs
    seq = mach.disasm_fn(int(fn, 16)) or []
    idx = {x.address: i for i, x in enumerate(seq)}
    j = idx[store_addr]
    st = seq[j]
    base_op = next(op for op in st.operands if op.type == capstone.CS_OP_MEM)
    R = a2211.rname(cs, base_op.mem.base)
    # 基底 R を書く直前の命令 (アドレス順の直前で、R を書く命令) を探す
    defs = []
    for x in seq[:j]:
        if reg_written_by(cs, x, R):
            defs.append(x)
    rec = dict(fn=fn, store=ins_str(st), base=R, prior_defs_of_base=[ins_str(x) for x in defs[-3:]])
    last = defs[-1] if defs else None
    if last is None:
        rec['origin'] = 'NO_DEF_IN_FN (entry)' if R in ENTRY_ARGS else 'UNKNOWN'
        return rec
    rec['last_def'] = ins_str(last)
    if last.mnemonic == 'mov' and last.op_str.startswith(R + ', qword ptr [rbp'):
        slot = mem_rbp_disp(cs, last)[0]
        X = slot[1]
        rec['slot'] = 'rbp%+#x' % X
        writes, reads = [], []
        for x in seq:
            for b, d, s in mem_rbp_disp(cs, x):
                if b != 'rbp' or not (d <= X < d + s):
                    continue
                first = x.operands[0] if x.operands else None
                if first is not None and first.type == capstone.CS_OP_MEM and x.mnemonic not in ('lea',) and a2211.writes_dst(x.mnemonic) and first.mem.disp == d:
                    writes.append(ins_str(x))
                else:
                    reads.append(ins_str(x))
        rec['slot_writes'] = writes
        rec['slot_other_refs'] = reads
        lea_cover = [ins_str(x) for x in seq if x.mnemonic == 'lea' and x.operands[1].type == capstone.CS_OP_MEM
                     and x.operands[1].mem.base and a2211.rname(cs, x.operands[1].mem.base) == 'rbp'
                     and x.operands[1].mem.disp <= X]
        rec['lea_addr_of_frame_at_or_below_slot'] = lea_cover
    rec['origin'] = 'see slot_writes'
    return rec


def main():
    pe, out = sys.argv[1], sys.argv[2]
    mach = Machine(pe)
    res = [analyze(mach, fn, a) for fn, a in TARGETS]
    json.dump(res, open(out, 'w'), indent=1)
    for r in res:
        print(json.dumps(r, ensure_ascii=False))


if __name__ == '__main__':
    main()
