#!/usr/bin/env python3
"""PY-204 (#3477): 表セル 0x15e26a0 を読む全箇所から、読んだ値 (= 0x193fa10) の行き先を前向きに追跡して分類する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py204_cell_writes.py [--dump <TSV>] [--method cfg|window]

- 起点: .text を線形走査し、RIP 相対で 0x15e26a0 を読む `mov reg, qword ptr [rip+..]` を全件列挙する (期待 247 件)。
- 追跡 (cfg): 読込直後の reg を値 P+k (k は既知定数) として持ち、分岐は両方・call は戻り先へ進める。
  mov reg,reg / mov reg,[rbp|rsp+d] / lea / add・sub imm で P+k を伝播し、rbp・rsp 基準のフレーム slot に退避した値も追う。
  ret まで (または P を持つ状態が消えるまで) 辿る。P+k を指すメモリ書込みを store として記録する。
- 分類: store 先が P+k+disp で 0x193fa10..0x193fa13 と重なれば HIT、重ならなければ OFF、index レジスタを含めば IDX。
- 検出できないもの (記録して数える): P を引数 (rcx/rdx/r8/r9) や stack 引数で渡す call (passed)、P を ABI 外のレジスタ (rax 等) に残したまま call/jmp する箇所 (passed-other)、P を RIP 以外の
  記憶へ退避する (escape)、間接 jmp (indirect)、STEP_CAP で打ち切った起点 (truncated)。
- --method window: 検算用の別アルゴリズム。起点から線形に 40 命令だけ見て、P を持つ base 経由の書込みを数える
  (分岐・call の戻りを無視する近似)。cfg の HIT/OFF/IDX の集合が window の結果を含むかを確かめる。

検証 (本ファイルの末尾で PASS/FAIL を出す):
  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py204_cell_writes.py --check
終了 0 = 全 PASS。1 件でも FAIL なら終了 1。
"""
import argparse
import os
import sys
from collections import defaultdict

import capstone
import pefile
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_OP_REG

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
RAW = open(PE, "rb").read()
PEF = pefile.PE(data=RAW, fast_load=True)
BASE = PEF.OPTIONAL_HEADER.ImageBase
TEXT = next(s for s in PEF.sections if s.Name.rstrip(b"\0") == b".text")
TEXT_LO = BASE + TEXT.VirtualAddress
TEXT_HI = TEXT_LO + min(TEXT.Misc_VirtualSize, TEXT.SizeOfRawData)
MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
MD.detail = True

CELL = 0x15E26A0
CUR = 0x193FA10
RD = capstone.CS_AC_READ
WR = capstone.CS_AC_WRITE
ARG_REGS = ("rcx", "rdx", "r8", "r9")
CALLER_SAVED = {"rax", "rcx", "rdx", "r8", "r9", "r10", "r11"}
FRAME = ("rbp", "rsp")
STEP_CAP = 200000
WINDOW = 40
KMAX = 0x10000
KILL = True

GPR = {}
for _b in ("a", "b", "c", "d"):
    for _n in (_b + "l", _b + "h", _b + "x", "e" + _b + "x", "r" + _b + "x"):
        GPR[_n] = "r" + _b + "x"
for _b in ("si", "di", "bp", "sp"):
    for _n in (_b, _b + "l", "e" + _b, "r" + _b):
        GPR[_n] = "r" + _b
for _k in range(8, 16):
    for _n in (f"r{_k}", f"r{_k}d", f"r{_k}w", f"r{_k}b"):
        GPR[_n] = f"r{_k}"


def fam(ins, reg_id):
    name = ins.reg_name(reg_id)
    return GPR.get(name, name)


def file_off(va):
    rva = va - BASE
    for s in PEF.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.PointerToRawData + (rva - s.VirtualAddress)
    return None


_cache = {}


def ins_at(va):
    if va not in _cache:
        off = file_off(va)
        _cache[va] = None if off is None else next(MD.disasm(RAW[off:off + 16], va), None)
    return _cache[va]


def mem_parts(ins, op):
    m = op.mem
    base = fam(ins, m.base) if m.base else None
    index = fam(ins, m.index) if m.index else None
    return base, index, m.disp, m.scale


def text(ins):
    return f"{ins.mnemonic} {ins.op_str}".strip()


def rip_loads(target):
    """.text の線形走査で、RIP 相対で target を指すメモリ参照を持つ命令を列挙する (decode 失敗は 1 byte 進める)。"""
    out = []
    va = TEXT_LO
    while va < TEXT_HI:
        off = file_off(va)
        ins = next(MD.disasm(RAW[off:off + 16], va), None)
        if ins is None:
            va += 1
            continue
        for op in ins.operands:
            if op.type == X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                if va + ins.size + op.mem.disp == target:
                    out.append(ins)
        va += ins.size
    return out


def abs_refs(values):
    """.text 全体で、base 無しの絶対 disp・即値として values を持つ命令の VA を列挙する。"""
    out = []
    va = TEXT_LO
    while va < TEXT_HI:
        off = file_off(va)
        ins = next(MD.disasm(RAW[off:off + 16], va), None)
        if ins is None:
            va += 1
            continue
        for op in ins.operands:
            if op.type == X86_OP_MEM and op.mem.base == 0 and op.mem.disp in values:
                out.append(ins.address)
            if op.type == X86_OP_IMM and op.imm in values:
                out.append(ins.address)
        va += ins.size
    return out


def succ(va, st, ev):
    """命令 va を通した後の (次 va, 状態) 列を返す。ev に事象を積む。st は {key: k} (key は reg 名 か ('M', base, d))。"""
    ins = ins_at(va)
    if ins is None:
        ev.add(("undecodable", va, ""))
        return []
    m, ops = ins.mnemonic, ins.operands
    tx = text(ins)
    nxt = va + ins.size
    if m == "ret" or m in ("hlt", "ud2") or m.startswith("int"):
        return []
    if m == "call":
        args = tuple(r for r in ARG_REGS if r in st)
        if args:
            ev.add(("passed", va, ins.op_str, tx, args))
        others = tuple(sorted(k for k in st if isinstance(k, str) and k not in ARG_REGS))
        if others:
            ev.add(("passed-other", va, ins.op_str, tx, others))
        if any(isinstance(k, tuple) and k[1] == "rsp" for k in st):
            ev.add(("passed-stack", va, ins.op_str, tx, ""))
        new = {k: v for k, v in st.items() if k not in CALLER_SAVED and not (isinstance(k, tuple) and k[1] == "rsp")}
        return [(nxt, new)] if new else []
    if m == "jmp":
        if ops and ops[0].type == X86_OP_IMM:
            args = tuple(r for r in ARG_REGS if r in st)
            if args:
                ev.add(("passed", va, ins.op_str, tx + " (tail)", args))
            others = tuple(sorted(k for k in st if isinstance(k, str) and k not in ARG_REGS))
            if others:
                ev.add(("passed-other", va, ins.op_str, tx + " (tail)", others))
            return [(ops[0].imm, st)]
        ev.add(("indirect", va, ins.op_str, tx, ""))
        return []
    if m.startswith("j") or m.startswith("loop"):
        if ops and ops[0].type == X86_OP_IMM:
            return [(ops[0].imm, st), (nxt, st)]
        ev.add(("indirect", va, ins.op_str, tx, ""))
        return [(nxt, st)]

    new = dict(st)
    for op in ops:
        if op.type != X86_OP_MEM or m == "lea":
            continue
        base, index, disp, _ = mem_parts(ins, op)
        tracked = (base in st) or (index in st)
        if op.access & WR:
            if tracked:
                kb = st.get(base) if base in st else None
                ki = st.get(index) if index in st else None
                ev.add(("store", va, tx, base, kb, index, ki, disp, op.size))
            if base in FRAME and index is None and base not in st:
                for k in list(new):
                    if isinstance(k, tuple) and k[1] == base and k[2] < disp + op.size and disp < k[2] + 8:
                        del new[k]
        elif op.access & RD and tracked:
            ev.add(("read", va, tx, base, index, disp, op.size))

    d0 = ops[0] if ops else None
    if m == "mov" and len(ops) == 2 and ops[1].type == X86_OP_REG and ops[1].size == 8 and d0.type == X86_OP_MEM:
        src = fam(ins, ops[1].reg)
        if src in st:
            base, index, disp, _ = mem_parts(ins, d0)
            if base in FRAME and index is None and base not in st:
                new[("M", base, disp)] = st[src]
                ev.add(("spill", va, tx, base, disp))
            else:
                ev.add(("escape", va, tx, base, index, ""))

    if m == "push" and ops and ops[0].type == X86_OP_REG and fam(ins, ops[0].reg) in st:
        ev.add(("escape", va, tx, "push", None, ""))

    rw = {fam(ins, r) for r in ins.regs_write}
    rw |= {fam(ins, op.reg) for op in ops if op.type == X86_OP_REG and op.access & WR}
    if "rsp" in rw:
        for k in list(new):
            if isinstance(k, tuple) and k[1] == "rsp":
                del new[k]

    newval = None
    dst = None
    if d0 is not None and d0.type == X86_OP_REG:
        dst = fam(ins, d0.reg)
        if m == "mov" and len(ops) == 2 and d0.size == 8:
            s1 = ops[1]
            if s1.type == X86_OP_REG and fam(ins, s1.reg) in st:
                newval = st[fam(ins, s1.reg)]
            elif s1.type == X86_OP_MEM and s1.size == 8:
                base, index, disp, _ = mem_parts(ins, s1)
                if index is None and base in FRAME and ("M", base, disp) in st:
                    newval = st[("M", base, disp)]
        elif m == "lea" and len(ops) == 2 and d0.size == 8 and ops[1].type == X86_OP_MEM:
            base, index, disp, _ = mem_parts(ins, ops[1])
            if base in st and index is None:
                newval = st[base] + disp
        elif m in ("add", "sub") and len(ops) == 2 and d0.size == 8 and ops[1].type == X86_OP_IMM and dst in st:
            newval = st[dst] + (ops[1].imm if m == "add" else -ops[1].imm)
    for w in rw:
        if KILL:
            new.pop(w, None)
    if dst is not None and newval is not None and abs(newval) <= KMAX:
        new[dst] = newval
    return [(nxt, new)] if new else []


def cfg_from(start, reg):
    """start の命令から、reg が P (k=0) を持つ状態で cfg を辿る。"""
    ev = set()
    work = [(start, {reg: 0})]
    seen = set()
    steps = 0
    truncated = False
    while work:
        va, st = work.pop()
        if not st:
            continue
        key = (va, frozenset(st.items()))
        if key in seen:
            continue
        seen.add(key)
        steps += 1
        if steps > STEP_CAP:
            truncated = True
            break
        work.extend(succ(va, st, ev))
    return ev, steps, truncated


def cfg_explore(load):
    return cfg_from(load.address + load.size, fam(load, load.operands[0].reg))


def window_explore(load):
    reg = fam(load, load.operands[0].reg)
    ev = set()
    va = load.address + load.size
    for _ in range(WINDOW):
        ins = ins_at(va)
        if ins is None or ins.mnemonic == "ret":
            break
        for op in ins.operands:
            if op.type == X86_OP_MEM and op.access & WR and ins.mnemonic != "lea":
                base, index, disp, _ = mem_parts(ins, op)
                if base == reg and index is None:
                    ev.add(("store", ins.address, text(ins), base, 0, None, None, disp, op.size))
        va += ins.size
    return ev, WINDOW, False


def classify(ev_store):
    _, va, tx, base, kb, index, ki, disp, size = ev_store
    if index is not None or base is None or kb is None:
        return "IDX" if index is not None else "PIDX"
    off = kb + disp
    if off < 4 and off + size > 0:
        return "HIT" if off == 0 and size == 4 else "HIT-PART"
    return "OFF"


def reach_writes(entry, limit=5000):
    """entry から到達できる命令のうち、メモリへ書く命令を列挙する (call は戻り先へ、jcc は両方へ進む)。"""
    seen, work, out = set(), [entry], []
    while work and len(seen) < limit:
        va = work.pop()
        if va in seen:
            continue
        seen.add(va)
        ins = ins_at(va)
        if ins is None:
            continue
        for op in ins.operands:
            if op.type == X86_OP_MEM and op.access & WR and ins.mnemonic != "lea":
                base, index, disp, _ = mem_parts(ins, op)
                out.append((va, text(ins), base, index, disp))
        if ins.mnemonic == "ret":
            continue
        if ins.mnemonic == "jmp" and ins.operands and ins.operands[0].type == X86_OP_IMM:
            work.append(ins.operands[0].imm)
        elif ins.mnemonic.startswith("j"):
            if ins.operands and ins.operands[0].type == X86_OP_IMM:
                work.append(ins.operands[0].imm)
            work.append(va + ins.size)
        else:
            work.append(va + ins.size)
    return out, len(seen)


def rip_target(ins):
    for op in ins.operands:
        if op.type == X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
            return ins.address + ins.size + op.mem.disp
    return None


def run(method="cfg", loads=None):
    res = []
    for ld in (loads if loads is not None else rip_loads(CELL)):
        if method == "cfg":
            ev, steps, trunc = cfg_explore(ld)
        else:
            ev, steps, trunc = window_explore(ld)
        res.append((ld, ev, steps, trunc))
    return res


def stores_of(res):
    """(load VA, store VA, 分類) の集合。"""
    out = set()
    for ld, ev, _, _ in res:
        for e in ev:
            if e[0] == "store":
                out.add((ld.address, e[1], classify(e)))
    return out


def summary(res):
    kinds = defaultdict(set)
    for ld, ev, _, _ in res:
        for e in ev:
            kinds[e[0]].add(ld.address)
    return kinds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", default="cfg", choices=["cfg", "window"])
    ap.add_argument("--dump")
    ap.add_argument("--negctl-nokill", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    global KILL
    if args.negctl_nokill:
        KILL = False
    if args.check:
        return check()
    res = run(args.method)
    print(f"loads={len(res)} method={args.method} kill={KILL} truncated={sum(1 for r in res if r[3])}")
    cls = defaultdict(set)
    for ld, sv, cl in stores_of(res):
        cls[cl].add((hex(sv)))
    for c in sorted(cls):
        print(f"store class {c}: distinct store VA {sorted(cls[c])}")
    for k, v in sorted(summary(res).items()):
        print(f"event {k}: distinct load VA {len(v)}")
    if args.dump:
        with open(args.dump, "w") as f:
            f.write("load\tstore_or_site\tkind\tclass\ttext\n")
            for ld, ev, _, _ in res:
                for e in sorted(ev):
                    f.write("\t".join(str(x) for x in (hex(ld.address), hex(e[1]), e[0],
                                                       classify(e) if e[0] == "store" else "-", e[2])) + "\n")
        print("dump:", args.dump)
    return 0


def check():
    ok = []

    def chk(name, cond, detail=""):
        ok.append(bool(cond))
        print("PASS" if cond else "FAIL", name, detail)

    loads = rip_loads(CELL)
    chk("C0 表セル 0x15e26a0 を RIP 相対で読む命令は 247 件・全て mov reg, qword ptr [rip+..]",
        len(loads) == 247 and all(text(i).startswith("mov r") and ", qword ptr [rip" in text(i) for i in loads),
        str(len(loads)))
    res = run("cfg", loads)
    chk("C1 cfg 追跡は全件 STEP_CAP 内で終わる", not any(r[3] for r in res),
        f"truncated={sum(1 for r in res if r[3])}")
    st = stores_of(res)
    hits = sorted({(hex(sv), cl) for _, sv, cl in st if cl.startswith("HIT")})
    print("  HIT:", hits)
    print("  non-HIT store classes:", sorted({cl for _, _, cl in st if not cl.startswith("HIT")}))
    chk("C2 0x193fa10 への直接書込み (HIT) は 0x12900d7 と 0x12a458d の 2 箇所だけ",
        [h for h, _ in hits] == ["0x12900d7", "0x12a458d"], str(hits))
    chk("C3 HIT は全て 4 byte・offset 0 の完全一致 (分類 HIT)", all(c == "HIT" for _, c in hits))
    chk("C4 P+k の OFF・索引付き IDX の書込みは 0 件", not [1 for _, _, cl in st if cl in ("OFF", "IDX", "PIDX")])
    k = summary(res)
    chk("C5 ABI 引数レジスタ (rcx/rdx/r8/r9) へ P が渡る call は 1 件 (0x12a586d → 0x1182d30)、その callee は先頭で rcx を再ロードして読まない",
        sorted(hex(e[1]) for ld, ev, _, _ in res for e in ev if e[0] == "passed") == ["0x12a586d"])
    chk("C6 escape (P を RIP 相対・非フレームの記憶へ格納) と indirect jmp は 0 件",
        not k.get("escape") and not k.get("indirect"))
    rw, n = reach_writes(0x12A4390)
    bases = sorted({(hex(v), t, b) for v, t, b, _, _ in rw})
    chk("C7 0x12a4390 の到達可能な書込みに P 由来の基底は無い (rdx 基底は heap 配列・rbx/rbp はフレーム)",
        len(rw) == 5 and all(b in ("rbp", "rbx", "rdx") for _, _, b, _, _ in rw), str(bases))
    chk("C8 0x12a44a6 の [rbp+0x40] へ入る値は call 0x409410 の戻り値 (呼出しの並びだけを確認)",
        text(ins_at(0x12A449C)) == "mov ecx, 0x7d8" and text(ins_at(0x12A44A1)) == "call 0x409410"
        and text(ins_at(0x12A44A6)) == "mov qword ptr [rbp + 0x40], rax")
    chk("C9 f8ca50 (ii): tag = [rcx+0x10]>>22 == 0xff のときだけ [P] を読む",
        text(ins_at(0xF8CA97)) == "shr eax, 0x16" and text(ins_at(0xF8CA9A)) == "cmp eax, 0xff"
        and text(ins_at(0xF8CA9F)) == "jne 0xf8caaa" and text(ins_at(0xF8CAA1)).startswith("mov rax, qword ptr [rip")
        and rip_target(ins_at(0xF8CAA1)) == CELL and text(ins_at(0xF8CA5D)) == "shr edx, 0x10"
        and text(ins_at(0xF8CA60)) == "cmp edx, 0xfff" and text(ins_at(0xF8CA66)) == "jne 0xf8ca97")
    pso = [e for ld, ev, _, _ in res for e in ev if e[0] == "passed-other"]
    pso_sites = {e[1] for e in pso}
    pso_tgts = {ins_at(va).operands[0].imm for va in pso_sites}
    chk("C10 ABI 引数外のレジスタ (rax のみ) に P が残ったまま call/jmp する箇所は 107 件 (呼出し先 41 種)",
        len(pso_sites) == 107 and len(pso_tgts) == 41 and all(e[4] == ("rax",) for e in pso),
        f"sites={len(pso_sites)} targets={len(pso_tgts)}")
    cal = {t: cfg_from(t, "rax") for t in sorted(pso_tgts)}
    cal_ev = sum(1 for v in cal.values() for e in v[0] if e[0] != "passed-other")
    cal_po = sum(1 for v in cal.values() for e in v[0] if e[0] == "passed-other")
    cal_trunc = sum(1 for v in cal.values() if v[2])
    chk("C11 rax に P を受ける呼出し先 41 種の内部 (depth 1 の cfg) で P の読込み・書込み・引数渡し・escape・indirect・spill は 0 件 (depth 2 への受渡し passed-other は範囲外)",
        cal_ev == 0 and cal_trunc == 0 and len(cal) == 41,
        f"events_excl_passed_other={cal_ev} passed_other_depth2={cal_po} truncated={cal_trunc} steps={sum(v[1] for v in cal.values())}")
    absr = abs_refs({CELL, CUR})
    chk("C12 絶対アドレス (base 無しの disp・即値) による 0x15e26a0・0x193fa10 の参照は 0 件",
        not absr, str([hex(v) for v in absr][:5]))
    global KILL
    KILL_SAVE = KILL
    KILL = False
    nk = run("cfg", loads)
    KILL = KILL_SAVE
    nk_hits = sorted({hex(sv) for _, sv, cl in stores_of(nk) if cl.startswith("HIT")})
    chk("N1 負制御: レジスタ kill を外すと HIT が 2 件を超える (検出の感度)", len(nk_hits) > 2, f"HIT stores={nk_hits}")
    print(f"{sum(ok)}/{len(ok)} PASS")
    return 0 if all(ok) else 1


if __name__ == "__main__":
    sys.exit(main())
