#!/usr/bin/env python3
"""SR-48 #3236: 間接 call の受信 base の ARG (rdx/r8/r9) を呼出元へたどり、THIS の SC 伝播を拡張する (静的・関数間)。

前提: receiver_this_trace.py (SR-43) と同じ PE。本スクリプトはそれを runpy で読み込み、その解析部品 (value・候補・SC 集合) を使う。
追加:
  1. ARG 候補: 候補の所属関数 F の引数レジスタ R (rdx/r8/r9) について、F へ直接 call / 末尾 jmp する呼出元 G ごとに、
     G で R の値を遡る。G の this (rcx の受け取り値そのまま) で G が SC なら SC 証拠。G の引数なら 2 段まで再帰する。
  2. SC 伝播の拡張: 直接 call に加えて末尾 jmp (thunk の tail call) で rcx が this のまま渡される先も SC に加える (不動点)。
  自己検査: 候補の分類 (ARG/THIS/... の件数) は receiver_this_trace.py の strict 分類と一致しなければならない。
            拡張なしの SC 集合は base の 21 関数と一致しなければならない。
判定:
  SC        : 全ての直接呼出元の値が SC の this (引数なら再帰して全て SC)
  SC-mixed  : 一部だけ SC
  非確定    : 上記以外 (呼出元が無い・未解決・SC でない this のみ)。SC でないことの証明はしない。
usage: sr48_arg_this.py <pe> [--tsv out.tsv]
"""
import contextlib
import io
import os
import re
import runpy
import struct
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
PE = sys.argv[1]
TSV = sys.argv[sys.argv.index("--tsv") + 1] if "--tsv" in sys.argv else None
sys.argv = ["receiver_this_trace.py", PE, "--vtable", "0x180a2bf58"]
with contextlib.redirect_stdout(io.StringIO()):
    g = runpy.run_path(os.path.join(HERE, "receiver_this_trace.py"), run_name="rtt")

value, get_fn, func_of, by_func, ins_all = g["value"], g["get_fn"], g["func_of"], g["by_func"], g["ins_all"]
parse_mem, DISPS, MAXLOAD = g["parse_mem"], g["DISPS"], g["MAXLOAD"]
slot_fns, ctor_fns, SC_BASE = g["slot_fns"], g["ctor_fns"], g["SC"]
ARGREG = ("rdx", "r8", "r9")
ADDR = re.compile(r"0x[0-9a-f]+")


def origin_reg(fn, pos, reg, depth=0):
    """origin と同じ遡り。ただし引数の受け取りレジスタ名 (arg:rdx 等) を残す。"""
    if depth > MAXLOAD:
        return ("depth", [])
    kind, info, k = value(fn, pos, reg, True)
    if kind == "entry":
        if info == "rcx":
            return ("this", [])
        if info in ARGREG:
            return ("arg:" + info, [])
        return ("entry-" + str(info), [])
    if kind in ("load", "lea"):
        base, d = info
        root, steps = origin_reg(fn, k, base, depth + 1)
        return (root, steps + [("[+%#x]" if kind == "load" else "+%#x") % d])
    return (kind, [])


def cat_of(root, steps):
    if root == "this" or root.startswith("arg:"):
        pre = "THIS" if root == "this" else "ARG"
        if not steps:
            return pre
        if all(s.startswith("+") for s in steps):
            return pre + "-EMB"
        return pre + "-CHILD"
    return root.upper()


def closure(seed, use_jmp):
    sc = set(seed)
    frontier = list(sc)
    while frontier:
        gf = frontier.pop()
        if gf not in by_func:
            continue
        fn = get_fn(gf)
        for i, ins in enumerate(fn.ins):
            if ins.mnemonic not in ("call", "jmp") or (ins.mnemonic == "jmp" and not use_jmp):
                continue
            if not ADDR.fullmatch(ins.op_str):
                continue
            f = int(ins.op_str, 16)
            if f in sc or func_of(f) != f:
                continue
            if origin_reg(fn, i, "rcx") == ("this", []):
                sc.add(f)
                frontier.append(f)
    return sc


seed = set(slot_fns) | {f for f in ctor_fns if f}
SC_CHECK = closure(seed, False)
SCX = closure(seed, True)
print(f"自己検査: 拡張なし SC {len(SC_CHECK)} 関数 (base {len(SC_BASE)})・一致 {SC_CHECK == set(SC_BASE)}")
print(f"SC 拡張 (末尾 jmp を加える): {len(SCX)} 関数 (差 +{len(SCX) - len(SC_CHECK)})")

rev = defaultdict(list)
for ins in ins_all:
    if ins.mnemonic in ("call", "jmp") and ADDR.fullmatch(ins.op_str):
        rev[int(ins.op_str, 16)].append(ins.address)


def verdict_arg(F, R, depth=0):
    """F の引数 R の値を、直接呼出元 (call / jmp) ごとに判定する。"""
    if depth > 2:
        return ["unk-depth"]
    out = []
    for a in rev.get(F, []):
        G = func_of(a)
        if G is None:
            out.append("unk")
            continue
        fnG = get_fn(G)
        root, steps = origin_reg(fnG, fnG.index[a], R)
        if steps:
            out.append("unk-child")
        elif root == "this":
            out.append("SC" if G in SCX else "this-nonSC")
        elif root.startswith("arg:"):
            out.extend(verdict_arg(G, root[4:], depth + 1))
        else:
            out.append("unk")
    return out or ["nocaller"]


def verdict_this(F):
    out = []
    for a in rev.get(F, []):
        G = func_of(a)
        if G is None:
            out.append("unk")
            continue
        root, steps = origin_reg(get_fn(G), get_fn(G).index[a], "rcx")
        if steps:
            out.append("unk-child")
        elif root == "this":
            out.append("SC" if G in SCX else "this-nonSC")
        else:
            out.append("unk")
    return out or ["nocaller"]


def judge(vs):
    if all(v == "SC" for v in vs):
        return "SC"
    if any(v == "SC" for v in vs):
        return "SC-mixed"
    return "非確定"


rows = []
for ins in ins_all:
    if ins.mnemonic != "call":
        continue
    mm = parse_mem(ins.op_str.strip(), ins)
    if mm is None or mm["disp"] not in DISPS or mm["index"] or mm["rip"] or mm["base"] is None:
        continue
    F = func_of(ins.address)
    if F is None:
        continue
    fn = get_fn(F)
    i = fn.index[ins.address]
    kind, info, k = value(fn, i, mm["base"], True)
    if not (kind == "load" and info[0] not in ("rsp", "rbp")):
        rows.append((ins.address, F, "R-" + kind, "", [], ""))
        continue
    ob, d = info
    root, steps = origin_reg(fn, k, ob)
    steps = steps + ([f"+{d:#x}"] if d else [])
    cat = ("vptr" if d == 0 else "vptr-emb") + ":" + cat_of(root, steps)
    if root.startswith("arg:"):
        vs = verdict_arg(F, root[4:])
    elif root == "this" and not steps:
        vs = verdict_this(F)
    else:
        vs = []
    rows.append((ins.address, F, cat, root + "".join(steps), vs, root))

IMG = g["IMG"]
TAKEN = defaultdict(list)
_fset = {r[1] for r in rows if r[1] is not None}
_data = open(PE, "rb").read()
for s in g["pe"].sections:
    if s.Name.rstrip(b"\0") not in (b".rdata", b".data"):
        continue
    raw = _data[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
    for off in range(0, len(raw) - 7, 8):
        v = struct.unpack_from("<Q", raw, off)[0]
        if v in _fset:
            TAKEN[v].append(IMG + s.VirtualAddress + off)
cnt = Counter(r[2] for r in rows)
print(f"候補 {len(rows)} 件 (disp 0x30/0x38/0x88)")
for k2, n in cnt.most_common():
    print(f"{n:5d}  {k2}")

arg_rows = [r for r in rows if r[2] in ("vptr:ARG", "vptr-emb:ARG")]
argc_rows = [r for r in rows if r[2] == "vptr:ARG-CHILD"]
this_rows = [r for r in rows if r[2] == "vptr:THIS"]
thisc_rows = [r for r in rows if r[2] == "vptr:THIS-CHILD"]

print(f"== ARG 240 件 (直接の引数): 判定 {dict(Counter(judge(r[4]) for r in arg_rows))}")
print(f"   呼出元の値の内訳 {dict(sorted(Counter(v for r in arg_rows for v in set(r[4])).items()))}")
_na = [r for r in arg_rows if r[4] == ["nocaller"]]
print(f"   直接呼出元なし {len(_na)} 件 (関数 {len({r[1] for r in _na})} 個)。うち関数アドレスとしてデータ表に現れる関数 {sum(1 for r in _na if r[1] in TAKEN)} 件")

print(f"== ARG-CHILD {len(argc_rows)} 件 (親の引数が SC か): 判定 {dict(Counter(judge(r[4]) for r in argc_rows))}")
print(f"   親の呼出元の値の内訳 {dict(sorted(Counter(v for r in argc_rows for v in set(r[4])).items()))}")
print(f"== THIS {len(this_rows)} 件: 所属関数 SC (拡張後) {sum(1 for r in this_rows if r[1] in SCX)} 件 (関数 {len({r[1] for r in this_rows if r[1] in SCX})} 個)")
nonsc = [r for r in this_rows if r[1] not in SCX]
print(f"   所属関数が SC でない {len(nonsc)} 件 (関数 {len({r[1] for r in nonsc})} 個)。呼出元の値: {dict(sorted(Counter(v for r in nonsc for v in set(r[4])).items()))}")
print(f"== THIS-CHILD {len(thisc_rows)} 件: 子の型は未確定 (this の子)。所属関数 SC {sum(1 for r in thisc_rows if r[1] in SCX)} 件")

if TSV:
    with open(TSV, "w") as fh:
        fh.write("call_va\tfunc\tcat\tpath\tverdicts\tsc_fn\n")
        for r in rows:
            fh.write(f"{r[0]:#x}\t{r[1]:#x}\t{r[2]}\t{r[3]}\t{';'.join(sorted(set(r[4])))}\t{int(r[1] in SCX)}\n")
