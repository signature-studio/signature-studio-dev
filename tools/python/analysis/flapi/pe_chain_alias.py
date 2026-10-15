#!/usr/bin/env python3
"""FLEngine PE で、Q 本体 (G → Q スロット → Q) を指すレジスタ・スタック・引数の値を制御フローに沿って追い、
`[Q+disp]` への書込み (別名経由を含む) を列挙する (PY-169 / #3212 受入 1「間接 store を含む」の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_chain_alias.py <G VA(16進)> [disp(16進, 既定 8)]

- seed: `.text` 内の `mov r, [G]` (タグ QS) と `mov r, [Q スロット]` (タグ QO) の直後の位置。
- 追跡: 分岐は両方の飛び先へ (状態 = タグの集合を含めて重複排除)、`jmp` は飛び先へ、`ret`・間接 jmp・
  `int3` で止まる。call では caller-saved のタグを消し、引数レジスタ (rcx/rdx/r8/r9) に Q を載せた直接 call は
  callee の先頭から同じ規則で追う (再帰)。タグが空になった時点で止まる。
- Q の値が (a) グローバルへの格納 (`mov [rip+g], Q`)、(b) 別のメモリへの格納 (`mov [reg+d], Q`)、
  (c) push、(d) 引数に載せた間接 call、に流れた箇所は件数と VA を出す。(a) の格納先 g は、g を読む位置を
  新たな seed にして 2 周目を走らせる。
- 手動の起点 (Q の vptr): Q の vptr は `Q_VPTR` = 0x9764d8。割当連鎖 `0x410320` (`call [this-0x30]`) → `0x40f960` →
  `0x40fb40` (`mov [O], this`) により、this = `[0x976410]` = 0x9764d8 がそのまま vptr になる (根拠は REPORT 付録)。
  vptr の -0x48〜-0x8 の全スロットの関数を rcx = Q の起点として追加する。`EXTRA_ENTRIES` は Q の仮想デストラクタ 0x976dc0 (`[vptr-0x20]`)。
- 追わないもの: 戻り値による Q の受け渡し (call の戻り値の rax は caller-saved として消す)、間接 jmp (ジャンプテーブル)、
  それ以外の間接 call の先の本体。候補は手で逆アセして確定する。

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
"""
import os
import re
import struct
import sys
import time
from collections import deque

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
CHUNK = 1 << 16
CALLER_SAVED = ("rax", "rcx", "rdx", "r8", "r9", "r10", "r11")
ARG_REGS = ("rcx", "rdx", "r8", "r9")
STACK_BASES = ("rsp", "rbp")
Q_VPTR = 0x9764D8
EXTRA_ENTRIES = ((0x976DC0, "rcx"),)
X86 = capstone.x86


def canon(name):
    if name in ("ah", "bh", "ch", "dh"):
        return "r" + name[0] + "x"
    if name in ("al", "bl", "cl", "dl"):
        return "r" + name[0] + "x"
    if name in ("ax", "bx", "cx", "dx"):
        return "r" + name
    if name in ("sil", "dil", "bpl", "spl"):
        return "r" + name[:-1]
    if name in ("si", "di", "bp", "sp"):
        return "r" + name
    if re.fullmatch(r"e(ax|bx|cx|dx|si|di|bp|sp)", name):
        return "r" + name[1:]
    m = re.fullmatch(r"(r\d+)[dwb]", name)
    if m:
        return m.group(1)
    return name


def rip_target(ins, op):
    return ins.address + ins.size + op.mem.disp


def kind_of(ins, src):
    if src.type == X86.X86_OP_IMM:
        return "zero" if src.imm == 0 else f"imm 0x{src.imm & (2**64 - 1):x}"
    if src.type == X86.X86_OP_REG:
        return f"reg {ins.reg_name(src.reg)}"
    return "mem"


class Walker:
    def __init__(self, md, read_va, g_va, q_slot, disp_want):
        self.md = md
        self.read_va = read_va
        self.g_va = g_va
        self.q_slot = q_slot
        self.dw = disp_want
        self.cache = {}
        self.seen = set()
        self.work = deque()
        self.stores = []
        self.loads = []
        self.callees = []
        self.indirect_args = []
        self.copies = {}
        self.heap_copies = []
        self.stk_copies = []
        self.push_q = []
        self.ret_q = []
        self.stops = {}
        self.steps = 0
        self.seed_globals = set()

    def stop(self, why):
        self.stops[why] = self.stops.get(why, 0) + 1

    def decode(self, va):
        if va in self.cache:
            return self.cache[va]
        ins = None
        for n in (16, 8, 4, 2, 1):
            b = self.read_va(va, n)
            if b is None:
                continue
            got = list(self.md.disasm(b, va, 1))
            ins = got[0] if got else None
            break
        self.cache[va] = ins
        return ins

    def run(self):
        while self.work:
            va, tags = self.work.popleft()
            self.walk(va, tags)

    def walk(self, va, tags):
        while tags:
            key = (va, frozenset(tags.items()))
            if key in self.seen:
                return
            self.seen.add(key)
            ins = self.decode(va)
            if ins is None:
                self.stop("undecodable")
                return
            self.steps += 1
            ops = ins.operands
            mn = ins.mnemonic
            nxt = va + ins.size
            if mn == "ret" or mn in ("int3", "hlt", "ud2"):
                if mn == "ret" and tags.get("rax") == ("QO", 0):
                    self.ret_q.append(va)
                self.stop(mn)
                return
            if mn == "jmp":
                if ops and ops[0].type == X86.X86_OP_IMM:
                    va = ops[0].imm
                    continue
                self.stop("indirect_jmp")
                return
            if mn.startswith("j"):
                if ops and ops[0].type == X86.X86_OP_IMM:
                    self.work.append((ops[0].imm, dict(tags)))
                va = nxt
                continue
            if mn == "call":
                if ops and ops[0].type == X86.X86_OP_IMM:
                    for r in ARG_REGS:
                        if tags.get(r) == ("QO", 0):
                            self.callees.append((va, ops[0].imm, r))
                            self.work.append((ops[0].imm, {r: ("QO", 0)}))
                elif any(tags.get(r, ("", 0))[0] == "QO" for r in ARG_REGS):
                    self.indirect_args.append(va)
                for r in CALLER_SAVED:
                    tags.pop(r, None)
                va = nxt
                continue
            if mn == "push" and ops and ops[0].type == X86.X86_OP_REG \
                    and tags.get(canon(ins.reg_name(ops[0].reg))) == ("QO", 0):
                self.push_q.append(va)
            self.step(ins, tags)
            va = nxt
        return

    def step(self, ins, tags):
        ops = ins.operands
        mn = ins.mnemonic
        dw = self.dw
        if mn == "mov" and len(ops) == 2 and ops[0].type == X86.X86_OP_MEM and ops[0].size == 8:
            m = ops[0].mem
            src_qo = ops[1].type == X86.X86_OP_REG and \
                tags.get(canon(ins.reg_name(ops[1].reg))) == ("QO", 0)
            if m.base == X86.X86_REG_RIP and m.index == 0:
                if src_qo:
                    self.copies.setdefault(rip_target(ins, ops[0]), []).append(ins.address)
                return
            if m.base != 0 and m.index == 0:
                b = canon(ins.reg_name(m.base))
                if b in STACK_BASES:
                    key = ("stk", b, m.disp)
                    if src_qo:
                        tags[key] = ("QO", 0)
                        self.stk_copies.append(ins.address)
                    else:
                        tags.pop(key, None)
                    return
                bt = tags.get(b)
                if bt and bt[0] == "QO" and bt[1] + m.disp == dw:
                    self.stores.append((ins.address, f"{ins.mnemonic} {ins.op_str}", kind_of(ins, ops[1])))
                elif src_qo:
                    self.heap_copies.append(ins.address)
                return
        if mn == "mov" and len(ops) == 2 and ops[0].type == X86.X86_OP_REG and ops[0].size == 8 \
                and ops[1].type == X86.X86_OP_MEM:
            dst = canon(ins.reg_name(ops[0].reg))
            m = ops[1].mem
            new = None
            if m.base == X86.X86_REG_RIP and m.index == 0 and ops[1].size == 8:
                t = rip_target(ins, ops[1])
                if t == self.g_va:
                    new = ("QS", 0)
                elif t == self.q_slot or t in self.seed_globals:
                    new = ("QO", 0)
            elif m.base != 0 and m.index == 0:
                b = canon(ins.reg_name(m.base))
                if b in STACK_BASES:
                    new = tags.get(("stk", b, m.disp))
                else:
                    bt = tags.get(b)
                    if bt == ("QS", 0) and m.disp == 0:
                        new = ("QO", 0)
                    elif bt and bt[0] == "QO" and bt[1] + m.disp == dw:
                        new = ("O", 0)
                        self.loads.append((ins.address, f"{ins.mnemonic} {ins.op_str}"))
            tags.pop(dst, None)
            if new is not None:
                tags[dst] = new
            return
        if mn == "lea" and len(ops) == 2 and ops[0].type == X86.X86_OP_REG and ops[1].type == X86.X86_OP_MEM:
            dst = canon(ins.reg_name(ops[0].reg))
            m = ops[1].mem
            new = None
            if m.base != 0 and m.base != X86.X86_REG_RIP and m.index == 0:
                bt = tags.get(canon(ins.reg_name(m.base)))
                if bt and bt[0] == "QO":
                    new = ("QO", bt[1] + m.disp)
            tags.pop(dst, None)
            if new is not None:
                tags[dst] = new
            return
        if mn in ("add", "sub") and len(ops) == 2 and ops[0].type == X86.X86_OP_REG and ops[0].size == 8 \
                and ops[1].type == X86.X86_OP_IMM:
            dst = canon(ins.reg_name(ops[0].reg))
            tg = tags.get(dst)
            if tg and tg[0] == "QO":
                d = ops[1].imm if mn == "add" else -ops[1].imm
                tags[dst] = ("QO", tg[1] + d)
            return
        if mn == "mov" and len(ops) == 2 and ops[0].type == X86.X86_OP_REG and ops[1].type == X86.X86_OP_REG \
                and ops[0].size == 8 and ops[1].size == 8:
            dst = canon(ins.reg_name(ops[0].reg))
            src = canon(ins.reg_name(ops[1].reg))
            t = tags.get(src)
            tags.pop(dst, None)
            if t is not None:
                tags[dst] = t
            return
        if mn in ("cmp", "test"):
            return
        if ops and ops[0].type == X86.X86_OP_REG:
            tags.pop(canon(ins.reg_name(ops[0].reg)), None)


def scan_rip_loads(text, read_text, g_va, q_slot, targets):
    """`mov r, [rip+X]` (8 バイト) の位置を集める。X が G・Q スロット・targets のいずれかのもの。"""
    out = []
    lea_refs = []
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    n_ins = 0
    for st, sz, praw, rsz, _ in text:
        data = read_text(praw, rsz)
        off = 0
        while off < len(data):
            end = off
            for ins in md.disasm(data[off:off + CHUNK + 16], st + off):
                if ins.address - st - off + ins.size > CHUNK:
                    break
                n_ins += 1
                end = ins.address - st + ins.size
                ops = ins.operands
                if len(ops) == 2 and ops[1].type == X86.X86_OP_MEM and ops[1].mem.base == X86.X86_REG_RIP:
                    t = rip_target(ins, ops[1])
                    if ins.mnemonic == "lea" and t in (g_va, q_slot):
                        lea_refs.append((ins.address, t))
                    if ins.mnemonic == "mov" and ops[0].type == X86.X86_OP_REG and ops[0].size == 8 \
                            and ops[1].size == 8 and (t == g_va or t == q_slot or t in targets):
                        out.append((ins.address, ins.reg_name(ops[0].reg), t))
            if end > off:
                off = end
            else:
                off += 1
    return out, lea_refs, n_ins


def main():
    g_va = int(sys.argv[1], 16)
    disp_want = int(sys.argv[2], 16) if len(sys.argv) > 2 else 8
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = [(base + s.VirtualAddress, max(s.Misc_VirtualSize, s.SizeOfRawData),
             s.PointerToRawData, s.SizeOfRawData, s) for s in pe.sections]
    text = [s for s in secs if s[4].Characteristics & 0x20000000]

    def read_va(va, n):
        for st, sz, praw, rsz, _ in secs:
            if st <= va < st + sz:
                off = va - st
                if off + n > rsz:
                    return None
                return raw[praw + off:praw + off + n]
        return None

    def read_text(praw, rsz):
        return raw[praw:praw + rsz]

    q_slot = struct.unpack("<Q", read_va(g_va, 8))[0]
    print(f"G=0x{g_va:x} file_value(Q slot)=0x{q_slot:x} disp=0x{disp_want:x}")
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    t0 = time.time()

    seeds, lea_refs, n_ins = scan_rip_loads(text, read_text, g_va, q_slot, ())
    print(f"scan1 instructions={n_ins} seeds={len(seeds)} lea_refs_to_G_or_Qslot={len(lea_refs)} "
          f"sec={time.time() - t0:.1f}")
    for a, r, t in lea_refs:
        print(f"scan1 lea 0x{a:x} -> 0x{t:x}")

    w = Walker(md, read_va, g_va, q_slot, disp_want)
    for a, r, t in seeds:
        tag = ("QS", 0) if t == g_va else ("QO", 0)
        ins = w.decode(a)
        w.work.append((a + ins.size, {canon(r): tag}))
    if seeds:
        for entry, reg in EXTRA_ENTRIES:
            w.work.append((entry, {reg: ("QO", 0)}))
        for off in range(-0x48, 0, 8):
            b = read_va(Q_VPTR + off, 8)
            ent = struct.unpack("<Q", b)[0] if b else 0
            if any(st <= ent < st + sz for st, sz, _, _, _ in text):
                w.work.append((ent, {"rcx": ("QO", 0)}))
    w.run()
    rounds = 1
    while w.copies and rounds < 3:
        new_targets = set(w.copies) - w.seed_globals
        if not new_targets:
            break
        w.seed_globals |= new_targets
        more, _, _ = scan_rip_loads(text, read_text, g_va, q_slot, new_targets)
        more = [s for s in more if s[2] in new_targets]
        print(f"round{rounds + 1} new_copy_globals={len(new_targets)} seeds={len(more)}")
        for a, r, t in more:
            ins = w.decode(a)
            w.work.append((a + ins.size, {canon(r): ("QO", 0)}))
        w.run()
        rounds += 1

    for a, op, val in sorted(set(w.stores)):
        print(f"store 0x{a:x} {op} ; {val}")
    for a, op in sorted(set(w.loads)):
        print(f"load 0x{a:x} {op}")
    for call_va, target, r in sorted(set(w.callees)):
        print(f"callee-arg 0x{call_va:x} call 0x{target:x} ({r}=Q)")
    for g, sites in sorted(w.copies.items()):
        print(f"copy-to-global 0x{g:x} ; stored at {', '.join(f'0x{s:x}' for s in sorted(set(sites)))}")
    for a in sorted(set(w.heap_copies)):
        print(f"heap-copy 0x{a:x}")
    for a in sorted(set(w.stk_copies)):
        print(f"stack-copy 0x{a:x}")
    for a in sorted(set(w.push_q)):
        print(f"push-Q 0x{a:x}")
    for a in sorted(set(w.indirect_args)):
        print(f"indirect-call-with-Q-arg 0x{a:x}")
    for a in sorted(set(w.ret_q)):
        print(f"ret-with-Q-in-rax 0x{a:x}")
    n_store = len(w.stores)
    n_load = len(w.loads)
    print(f"walk seeds={len(seeds)} states={len(w.seen)} steps={w.steps} rounds={rounds} "
          f"store={n_store} load={n_load} callees={len(w.callees)} copies={len(w.copies)} "
          f"heap_copies={len(w.heap_copies)} stack_copies={len(w.stk_copies)} push_Q={len(w.push_q)} "
          f"indirect_args={len(w.indirect_args)} ret_Q={len(set(w.ret_q))} stops={w.stops} "
          f"sec={time.time() - t0:.1f}")


if __name__ == "__main__":
    main()
