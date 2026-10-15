#!/usr/bin/env python3
"""PY-160 (#3087): [rbp+0x5b8] の到達定義を CFG 上で求める (実機不要)。

  python3 analysis/py160_reach.py <work/py53/fn.txt>

py88_writes.py は ACC (= [rbp+0x5b8] の読み) を線形順の直前 store で決め、合流があれば ACC?⚠合流 と印を付ける。
本スクリプトは同じ読みの位置について、CFG 上の到達定義 (分岐・合流を越えた全経路の store 集合) を求める。
- 直接 store (mov/and/add/... dword ptr [rbp + 0x5b8], X) は kill + gen。
- 0x104a924 の lea r8,[rbp + 0x5b8] は、続く call 0xc61250 (0x104a92b) がポインタ経由で書く may-gen (kill しない)。
  0xc61250 内の書込みは 0xc6129a の 1 箇所で、0xc62630 の戻り値が非負のときだけ実行される。
- 入口 store は 0x1046d6b (edx を受ける)。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import py88_writes as pw  # noqa: E402

SLOT = "[rbp + 0x5b8]"
ENTRY_STORE = 0x1046D6B
INDIRECT_CALL = 0x104A92B
INDIRECT_LEA = 0x104A924
WRITE_MNEM = {"mov", "and", "or", "add", "sub", "xor", "adc", "sbb", "inc", "dec", "neg", "not", "shl", "shr", "sar"}


def load_fn(path):
    return pw.load(path)


def build(ins, order):
    idx = {a: i for i, a in enumerate(order)}
    leaders = {order[0]}
    for i, a in enumerate(order):
        m, o = ins[a]
        if m.startswith("j"):
            t = int(o, 16)
            if t in idx:
                leaders.add(t)
            if i + 1 < len(order):
                leaders.add(order[i + 1])
        if m == "ret" and i + 1 < len(order):
            leaders.add(order[i + 1])
    lead = sorted(leaders)
    blocks = []
    for k, s in enumerate(lead):
        e = lead[k + 1] if k + 1 < len(lead) else None
        members = []
        i = idx[s]
        while i < len(order) and (e is None or order[i] < e):
            members.append(order[i])
            i += 1
        blocks.append(members)
    bid = {blk[0]: k for k, blk in enumerate(blocks)}
    succ = {k: [] for k in range(len(blocks))}
    for k, blk in enumerate(blocks):
        last = blk[-1]
        m, o = ins[last]
        if m == "ret":
            continue
        if m.startswith("j"):
            t = int(o, 16)
            if t in bid:
                succ[k].append(bid[t])
            if m != "jmp" and k + 1 < len(blocks):
                succ[k].append(k + 1)
            continue
        if k + 1 < len(blocks):
            succ[k].append(k + 1)
    return blocks, succ


def is_slot_write(m, o):
    ops = pw.parse_ops(o)
    return m in WRITE_MNEM and ops and ops[0] == "dword ptr " + SLOT


def is_slot_read(m, o):
    if SLOT not in o:
        return False
    if m == "lea":
        return False
    ops = pw.parse_ops(o)
    if m == "mov" and ops and ops[0] == "dword ptr " + SLOT:
        return False
    return True


def transfer_one(state, a, m, o, record=None):
    if record is not None and is_slot_read(m, o):
        record[a] = frozenset(state)
    if a == INDIRECT_CALL:
        return state | {a}
    if is_slot_write(m, o):
        return frozenset({a})
    return state


def reaching(ins, order):
    blocks, succ = build(ins, order)
    n = len(blocks)
    pred = {k: [] for k in range(n)}
    for k, ss in succ.items():
        for s in ss:
            pred[s].append(k)
    IN = {k: frozenset() for k in range(n)}
    OUT = {k: frozenset() for k in range(n)}
    IN[0] = frozenset({"IN"})
    changed = True
    while changed:
        changed = False
        for k in range(n):
            if k == 0:
                new_in = IN[0]
            else:
                new_in = frozenset().union(*[OUT[p] for p in pred[k]]) if pred[k] else frozenset()
            st = new_in
            for a in blocks[k]:
                m, o = ins[a]
                st = transfer_one(st, a, m, o)
            if new_in != IN[k] or st != OUT[k]:
                IN[k], OUT[k] = new_in, st
                changed = True
    rec = {}
    for k in range(n):
        st = IN[k]
        for a in blocks[k]:
            m, o = ins[a]
            st = transfer_one(st, a, m, o, rec)
    return rec, blocks, succ, IN, OUT


def acc_reads_per_target(path, targets):
    orig = pw.Slicer.mem_read
    log = []

    def hook(self, addr, size, pos, depth):
        r = orig(self, addr, size, pos, depth)
        if addr.replace(" ", "") == "rbp+0x5b8":
            log.append((self.order[pos], r))
        return r

    pw.Slicer.mem_read = hook
    ins, order = pw.load(path)
    s = pw.Slicer(ins, order)
    out = {}
    try:
        for a in targets:
            log.clear()
            m, o = ins[a]
            val = s.ev(pw.parse_ops(o)[1], s.idx[a], 0)
            out[a] = (val, list(log))
    finally:
        pw.Slicer.mem_read = orig
    return out


def fmt(st):
    parts = []
    for d in sorted(st, key=lambda x: (isinstance(x, str), x if not isinstance(x, str) else 0)):
        if d == "IN":
            parts.append("IN(関数入口の値)")
        elif d == INDIRECT_CALL:
            parts.append("IND@0x104a92b(0xc61250 経由)")
        else:
            parts.append(f"{d:#x}")
    return ", ".join(parts)


def set_slot(off):
    global SLOT, INDIRECT_CALL
    SLOT = f"[rbp + 0x{off:x}]"
    INDIRECT_CALL = -1 if off != 0x5B8 else INDIRECT_CALL


def main():
    path = sys.argv[1]
    ins, order = load_fn(path)
    mode = sys.argv[2] if len(sys.argv) > 2 else ""
    if mode == "reach":
        set_slot(int(sys.argv[3], 16))
        rec, _, _, _, _ = reaching(ins, order)
        for a in (int(x, 16) for x in sys.argv[4:]):
            st = rec.get(a)
            print(f"{a:#x}: " + ("未到達/読みなし" if st is None else f"{{{fmt(st)}}}"))
        return
    rec, blocks, succ, IN, OUT = reaching(ins, order)
    if mode == "edges":
        bid = {b[0]: k for k, b in enumerate(blocks)}
        tgt = bid[int(sys.argv[3], 16)]
        for k in sorted(k for k, ss in succ.items() if tgt in ss):
            last = blocks[k][-1]
            print(f"{last:#x} {ins[last][0]} n={len(OUT[k])} {{{fmt(OUT[k])}}}")
        return
    print(f"# blocks={len(blocks)} slot_reads={len(rec)}")
    if mode == "r9d":
        st = rec.get(0x104CAEC)
        print(f"r9d read 0x104caec reach={{{fmt(st) if st is not None else '未到達'}}}")
    writes = pw.default_targets(path)
    per = acc_reads_per_target(path, writes)
    n_acc = 0
    n_ind = 0
    for a in writes:
        val, log = per[a]
        accs = [(r, res) for r, res in log if res == "ACC" or res.startswith("ACC?")]
        if not accs:
            continue
        n_acc += 1
        for r, res in accs:
            st = rec.get(r)
            ind = INDIRECT_CALL in st if st is not None else None
            if ind:
                n_ind += 1
            print(f"write {a:#x} read {r:#x} ({res}) reach={{{fmt(st) if st is not None else '未到達'}}}")
    print(f"# writes with ACC reads = {n_acc}, reads reached by IND = {n_ind}")


if __name__ == "__main__":
    main()
