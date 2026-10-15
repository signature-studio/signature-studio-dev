#!/usr/bin/env python3
"""PY-203 (#3476): 0x128f9e0 の直接 call (E8) 60 箇所それぞれで、第 2 引数 edx (rdx 族) の出どころを窓内の線形走査で分類する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py203_edx_sites.py > $RUNNER_TEMP/py203/edx_sites.tsv
  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py203_edx_sites.py --ablate merge   (ネガティブコントロール)
  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py203_edx_sites.py --ablate copy    (ネガティブコントロール)

- stdout: TSV (列: call_va, caller_fn, setter_va, setter_asm, class, value_or_source, note)
- stderr: クラス別件数、IMM の即値別件数、ENTRY/AMBIG/UNKNOWN の一覧
- 窓: 所属関数の先頭 (pe_callgraph.function_starts) から呼出し直前まで (線形)。
- setter (W): 窓内で rdx 族 (dl/dx/edx/rdx) を最後に書く命令。書込みの無いものは ENTRY。
- クラス:
    IMM     mov edx, imm (xor edx,edx は値 0 として数える)
    COPY    mov edx, reg。コピー元を同じ規則で再帰的にたどり、出どころを value に記す
    MEM     mov edx, [mem] (movzx/movsx/movsxd の memory 読み、pop を含む)
    ARITH   算術・movzx/movsx (reg)・lea・cdq・mul/div 等
    ENTRY   窓内で edx が書かれず、関数エントリの edx (= 第 2 引数)
    AMBIG   W を迂回して (W, S] の途中へ入る直接 jmp/jcc がある (経路により edx が違い得る)
    UNKNOWN 部分書込み (dl/dx/dh) 等、上記に当たらない
- 合流判定: (W, S] に飛び先があり、飛び元が [W, S) の外にある直接 jmp/jcc を迂回とみなす。
  W が無い (ENTRY) ときは [関数先頭, S] を対象にする。
- call は edx を書かないものとして扱う (規約 3)。ただし W 後の窓内 call 件数は note に記す
  (Win64 ABI では rdx は volatile なので、その件数分だけ値の保持は仮定になる)。
- 間接 jmp (分岐先未解決) が窓内にあれば note に記す。
"""
import argparse
import bisect
import collections
import os
import re
import sys

import capstone
import pefile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pe_callgraph as cg  # noqa: E402

TARGET = 0x128F9E0
EXPECTED = """
0xc4d157:0xc4d0b0 0xc4ebdf:0xc4eac0 0xd16328:0xd16190 0xd1cdb5:0xd1af20 0xd5e753:0xd5e6c0
0xd61608:0xd615a0 0xd627e6:0xd626c0 0xeaa555:0xea9660 0xf5c3a5:0xf5c340 0xf5c3ea:0xf5c340
0xf69a52:0xf699b0 0xf6f396:0xf6f360 0xf6fb17:0xf6f9d0 0xfc820f:0xfc8150 0xfdc518:0xfdc4a0
0x1021826:0x1021670 0x10484cc:0x1046a30 0x111e0fc:0x111da30 0x11857c1:0x11856d0
0x118586f:0x1185840 0x118a275:0x118a1c0 0x118a3f4:0x118a1c0 0x1193bf0:0x1192f80
0x11d29f5:0x11d2950 0x11d6c0c:0x11d55c0 0x11d6d77:0x11d55c0 0x11f6cad:0x11f6c40
0x125369a:0x1253610 0x127d0cc:0x127cea0 0x1289443:0x12875a0 0x128e904:0x128e7b0
0x1296d99:0x1296b10 0x129e876:0x129e850 0x129f0bb:0x129f080 0x12a1b09:0x12a13c0
0x12a1c21:0x12a1be0 0x12a38c5:0x12a3840 0x12a3d74:0x12a3ca0 0x12a4a09:0x12a46b0
0x12a5868:0x12a5240 0x12a72c9:0x12a71f0 0x12a86c9:0x12a85a0 0x12a9a1b:0x12a93b0
0x12a9fe0:0x12a9f00 0x12aa0b9:0x12aa020 0x12ab8e8:0x12ab710 0x12ab934:0x12ab710
0x12abcd6:0x12abc00 0x12acbc1:0x12acb70 0x12c5959:0x12c57c0 0x12c5be9:0x12c57c0
0x12c5ca3:0x12c57c0 0x12c609e:0x12c5f20 0x12c6240:0x12c5f20 0x12e3b29:0x12e3a60
0x12e3b8e:0x12e3a60 0x12e6abe:0x12e6960 0x12e7371:0x12e6cb0 0x12f88a4:0x12f38b0
0x1358569:0x13582c0
"""

GPR = {
    "rax": ("rax", "eax", "ax", "al", "ah"),
    "rbx": ("rbx", "ebx", "bx", "bl", "bh"),
    "rcx": ("rcx", "ecx", "cx", "cl", "ch"),
    "rdx": ("rdx", "edx", "dx", "dl", "dh"),
    "rsi": ("rsi", "esi", "si", "sil"),
    "rdi": ("rdi", "edi", "di", "dil"),
    "rbp": ("rbp", "ebp", "bp", "bpl"),
    "rsp": ("rsp", "esp", "sp", "spl"),
}
for _i in range(8, 16):
    GPR[f"r{_i}"] = (f"r{_i}", f"r{_i}d", f"r{_i}w", f"r{_i}b")
FAM = {n: f for f, ns in GPR.items() for n in ns}
BYTE = {"al", "ah", "bl", "bh", "cl", "ch", "dl", "dh", "sil", "dil", "bpl", "spl"} | {f"r{i}b" for i in range(8, 16)}
PARTIAL = BYTE | {"ax", "bx", "cx", "dx", "si", "di", "bp", "sp"} | {f"r{i}w" for i in range(8, 16)}
ARG = {"rcx": "ecx (第1引数)", "rdx": "edx (第2引数)", "r8": "r8d (第3引数)", "r9": "r9d (第4引数)"}

PREFIX = {"lock", "rep", "repe", "repne", "repz", "repnz", "notrack", "bnd", "data16", "addr32", "xacquire", "xrelease"}
NO_DST = {
    "cmp", "test", "push", "bt", "jmp", "call", "ret", "nop", "int3", "endbr64", "pause", "lfence", "mfence",
    "sfence", "ucomiss", "ucomisd", "comiss", "comisd", "ptest", "fcomi", "fcomip", "fucomi", "fucomip",
    "prefetcht0", "prefetcht1", "prefetcht2", "prefetchnta", "sahf", "clc", "stc", "cld", "std",
}
IMPLICIT = {
    "cdq": ("rdx",), "cqo": ("rdx",), "cdqe": ("rax",), "cwde": ("rax",), "cwd": ("rdx",), "cbw": ("rax",),
    "cpuid": ("rax", "rbx", "rcx", "rdx"), "rdtsc": ("rax", "rdx"), "rdtscp": ("rax", "rcx", "rdx"),
    "xgetbv": ("rax", "rdx"), "rdmsr": ("rax", "rdx"), "rdpmc": ("rax", "rdx"), "cmpxchg16b": ("rax", "rdx"),
    "syscall": ("rax", "rcx", "r11"), "loop": ("rcx",), "leave": ("rsp", "rbp"),
}
STR_OPS = {f"{b}{s}" for b in ("movs", "stos", "lods", "scas", "cmps") for s in "bwdq"}
STR_IMPL = {
    "movs": ("rsi", "rdi", "rcx"), "stos": ("rdi", "rcx"), "lods": ("rax", "rsi", "rcx"),
    "scas": ("rdi", "rcx"), "cmps": ("rsi", "rdi", "rcx"),
}
IMM_RE = re.compile(r"^-?(0x[0-9a-fA-F]+|[0-9]+)$")
MAX_DEPTH = 8

INS = []
ADDR_IDX = {}
FUNCS = []
JTS = []
JT = []
JMP_TO = collections.defaultdict(list)
NB_TGT = []
ABLATE = set()
CS = None
TEXT = b""
TEXT_VA = 0


def va(k):
    return f"0x{INS[k][0]:x}"


def norm(m, op):
    pre = False
    while m.split(" ")[0] in PREFIX:
        pre = pre or m.startswith("rep")
        if " " in m:
            m = m.split(" ", 1)[1]
        else:
            m, _, op = op.partition(" ")
    return m, op, pre


def split_ops(op):
    out, cur, depth = [], "", 0
    for ch in op:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def is_mem(s):
    return "[" in s


def norm_mem(s):
    m = re.search(r"\[.*\]", s)
    return m.group(0).replace(" ", "") if m else s


def writes(m, op):
    """命令が書く rdx 族以外も含む GPR 族の (族, 部分書込みか) の list。"""
    m, op, pre = norm(m, op)
    ops = split_ops(op)
    if m in IMPLICIT:
        return [(f, m == "cwd") for f in IMPLICIT[m]]
    if m in ("mul", "imul", "div", "idiv") and len(ops) == 1:
        if ops[0] in BYTE or "byte ptr" in ops[0]:
            return [("rax", True)]
        return [("rax", False), ("rdx", False)]
    if m in STR_OPS and (pre or "es:[" in op):
        return [(f, False) for f in STR_IMPL[m[:-1]]]
    if m in ("xchg", "xadd"):
        return [(FAM[o], o in PARTIAL) for o in ops if o in FAM]
    if m == "cmpxchg":
        r = [("rax", False)]
        if ops and ops[0] in FAM:
            r.append((FAM[ops[0]], ops[0] in PARTIAL))
        return r
    if m in NO_DST or m.startswith("j"):
        return []
    if ops and ops[0] in FAM:
        return [(FAM[ops[0]], ops[0] in PARTIAL)]
    return []


def last_writer(start, pos, fam):
    for j in range(pos - 1, start - 1, -1):
        for f, part in writes(INS[j][1], INS[j][2]):
            if f == fam:
                return j, part
    return None


def merge_hits(lo, hi, src_lo, src_hi):
    """(lo..hi) の飛び先を持つ直接 jmp/jcc のうち、飛び元が [src_lo, src_hi) の外のもの (src, tgt) の list。"""
    if "merge" in ABLATE:
        return []
    out = []
    for k in range(bisect.bisect_left(JT, lo), len(JT)):
        t, s = JTS[k]
        if t > hi:
            break
        if not (src_lo <= s < src_hi):
            out.append((s, t))
    return out


def desc(r):
    s = f"{r['cls']} {r['value']}"
    if r.get("setter") is not None:
        s += f" @{va(r['setter'])}"
    return s


def imm_text(src, dst):
    v = int(src, 0)
    bits = 64 if dst == "rdx" else 32
    mask = (1 << bits) - 1
    u = v & mask
    signed = u - (1 << bits) if u >= 1 << (bits - 1) else u
    return f"0x{u:x} ({signed})"


def mem_text(src, i):
    mem = norm_mem(src)
    m = re.search(r"rip([+-])(0x[0-9a-fA-F]+|\d+)", mem)
    if m and i + 1 < len(INS):
        disp = int(m.group(2), 0) * (-1 if m.group(1) == "-" else 1)
        mem += f" = VA 0x{INS[i + 1][0] + disp:x}"
    return mem


def last_store(start, pos, mem):
    for j in range(pos - 1, start - 1, -1):
        m, op, _ = norm(INS[j][1], INS[j][2])
        ops = split_ops(op)
        if m.startswith("mov") and len(ops) == 2 and is_mem(ops[0]) and norm_mem(ops[0]) == mem:
            return j
    return None


def classify(start, i, partial, fam, depth):
    _, m, o = INS[i]
    mm, oo, _ = norm(m, o)
    ops = split_ops(oo)
    asm = f"{m} {o}".strip()
    r = {"cls": "", "setter": i, "value": asm, "notes": []}
    if partial:
        r.update(cls="UNKNOWN", value=f"部分書込み ({asm})", notes=["上位ビットは直前値に依存"])
        return r
    if mm in IMPLICIT or mm in STR_OPS or (mm in ("mul", "imul", "div", "idiv") and len(ops) == 1):
        r.update(cls="ARITH", value=f"{asm} (暗黙の書込み)")
        return r
    if mm in ("mov", "movabs") and len(ops) == 2:
        src = ops[1]
        if IMM_RE.match(src):
            r.update(cls="IMM", value=imm_text(src, ops[0]))
            return r
        if src in FAM and src not in PARTIAL:
            sf = FAM[src]
            if "copy" in ABLATE:
                r.update(cls="COPY", value=f"{src} (未追跡: --ablate copy)")
                return r
            sub = resolve(start, i, sf, depth + 1)
            if sub["cls"] in ("AMBIG", "UNKNOWN"):
                r.update(cls=sub["cls"], value=f"copy {src} ← {desc(sub)}", notes=sub["notes"])
            else:
                r.update(cls="COPY", value=f"{src} ← {desc(sub)}", notes=sub["notes"])
            return r
        if src in PARTIAL:
            r.update(cls="ARITH", value=f"{asm} (部分レジスタからの拡張)")
            return r
        if is_mem(src):
            return mem_result(start, i, r, src, "")
    if mm == "xor" and len(ops) == 2 and ops[0] == ops[1]:
        r.update(cls="IMM", value="0x0 (0) (xor 自己)")
        return r
    if mm == "pop":
        r.update(cls="MEM", value="pop (スタック)")
        return r
    if mm in ("movzx", "movsx", "movsxd") and len(ops) == 2 and is_mem(ops[1]):
        return mem_result(start, i, r, ops[1], f" ({mm})")
    r.update(cls="ARITH", value=asm + (" (条件付き書込み)" if mm.startswith("cmov") else ""))
    return r


def mem_result(start, i, r, src, suffix):
    r.update(cls="MEM", value=mem_text(src, i) + suffix)
    if "[rbp" in norm_mem(src):
        j = last_store(start, i, norm_mem(src))
        if j is not None:
            r["notes"].append(f"同スロットへの直前 store: {va(j)} {INS[j][1]} {INS[j][2]}")
    return r


def resolve(start, pos, fam, depth=0):
    """pos の直前での族 fam の値。start は所属関数の先頭 (インデックス)。"""
    if depth > MAX_DEPTH:
        return {"cls": "UNKNOWN", "setter": None, "value": "再帰の深さ上限", "notes": []}
    lw = last_writer(start, pos, fam)
    if lw is None:
        base_lo, src_lo = start, start
        r = {"cls": "ENTRY", "setter": None, "value": f"entry {ARG.get(fam, fam)}", "notes": []}
    else:
        base_lo, src_lo = lw[0] + 1, lw[0]
        r = classify(start, lw[0], lw[1], fam, depth)
    hits = merge_hits(base_lo, pos, src_lo, pos)
    if hits:
        alts = []
        for s, t in hits[:3]:
            if s < start:
                alts.append(f"{va(s)}→{va(t)} (飛び元は窓外)")
            elif depth < 2:
                alts.append(f"{va(s)}→{va(t)} (飛び元の {fam} = {desc(resolve(start, s, fam, depth + 1))})")
            else:
                alts.append(f"{va(s)}→{va(t)}")
        r = {
            "cls": "AMBIG",
            "setter": r["setter"],
            "value": f"経路依存 (主経路 {desc(r)})",
            "notes": r["notes"] + [f"合流 {len(hits)} 件: " + "; ".join(alts)],
        }
    return r


def caller_note(fn, fk):
    cs = cg_sites.get(fn, [])
    js = JMP_TO.get(fk, [])
    if not cs:
        if not js:
            return "直接呼出し 0 件 (間接呼出しのみ・未追跡)"
        return f"直接呼出し 0 件、直接 jmp {len(js)} 件 (間接呼出し未追跡)"
    parts = []
    for c in cs:
        cfn = func_of(c)
        rr = resolve(ADDR_IDX[cfn], ADDR_IDX[c], "rdx")
        parts.append(f"0x{c:x}(in 0x{cfn:x}) edx={desc(rr)}")
    return f"直接呼出し元 {len(cs)} 件 (1 段のみ・さらに上は未追跡): " + "; ".join(parts) + (
        f"; 直接 jmp {len(js)} 件" if js else ""
    )


def func_of(addr):
    return FUNCS[bisect.bisect_right(FUNCS, addr) - 1]


cg_sites = {}


def fresh_fail(fn, site):
    """関数先頭から素直に復号して呼出し直前に届くか。届かなければ失敗 VA を返す (データ島の検出)。"""
    cur = fn
    while cur < site:
        ins1 = next(CS.disasm(TEXT[cur - TEXT_VA:cur - TEXT_VA + 16], cur), None)
        if ins1 is None:
            return cur
        cur += ins1.size
    return None if cur == site else cur


def analyze(site):
    fn = func_of(site)
    s, i = ADDR_IDX[fn], ADDR_IDX[site]
    r = resolve(s, i, "rdx")
    lw = last_writer(s, i, "rdx")
    lo = lw[0] + 1 if lw is not None else s
    ncall = sum(1 for k in range(lo, i) if INS[k][1] == "call")
    nind = sum(1 for k in range(s, i) if INS[k][1] == "jmp" and not INS[k][2].startswith("0x"))
    nb = [t for t in NB_TGT if fn <= t <= site]
    notes = [f"窓 {i - s} 命令"]
    fail = fresh_fail(fn, site)
    if fail is not None:
        notes.append(f"関数先頭からの素直な復号が 0x{fail:x} で失敗 (データ島の疑い。窓は線形走査の再同期結果)")
    if nb:
        notes.append(f"窓内の非境界の飛び先 {len(nb)} 件 (線形走査のずれの疑い): " + ", ".join(f"0x{t:x}" for t in nb[:3]))
    if ncall:
        notes.append(f"W 後の窓内 call {ncall} 件 (ABI 上 rdx は volatile。規約 3 で保持を仮定)")
    if nind:
        notes.append(f"窓内の間接 jmp {nind} 件 (分岐先未解決)")
    notes += r["notes"]
    if r["cls"] == "ENTRY":
        notes.append(caller_note(fn, s))
    return {
        "site": site,
        "fn": fn,
        "setter_va": f"0x{INS[lw[0]][0]:x}" if lw is not None else "-",
        "setter_asm": f"{INS[lw[0]][1]} {INS[lw[0]][2]}".strip() if lw is not None else "-",
        "cls": r["cls"],
        "value": r["value"],
        "note": "; ".join(n for n in notes if n),
    }


def clean(s):
    return str(s).replace("\t", " ").replace("\n", " ")


def main():
    global INS, ADDR_IDX, FUNCS, JTS, JT, ABLATE, CS, TEXT, TEXT_VA, NB_TGT
    ap = argparse.ArgumentParser(description="PY-203: 0x128f9e0 の直接 call 60 箇所の edx 出どころを分類する")
    ap.add_argument("--ablate", action="append", default=[], choices=["merge", "copy"],
                    help="分類ロジックを外す (ネガティブコントロール)")
    args = ap.parse_args()
    ABLATE = set(args.ablate)
    INS = cg.load()
    ADDR_IDX = {a: k for k, (a, _, _) in enumerate(INS)}
    FUNCS = cg.function_starts(INS)
    raw = open(cg.PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    text = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
    TEXT_VA = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress
    TEXT = raw[text.PointerToRawData:text.PointerToRawData + min(text.Misc_VirtualSize, text.SizeOfRawData)]
    CS = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    JTS = []
    NB_TGT = []
    for s, (a, m, o) in enumerate(INS):
        if m.startswith("j") and o.startswith("0x"):
            t = ADDR_IDX.get(int(o, 16))
            if t is None:
                NB_TGT.append(int(o, 16))
                continue
            JTS.append((t, s))
            JMP_TO[t].append(s)
    NB_TGT.sort()
    JTS.sort()
    JT = [t for t, _ in JTS]
    unresolved_jumps = len(NB_TGT)
    for a, m, o in INS:
        if m == "call" and o.startswith("0x"):
            cg_sites.setdefault(int(o, 16), []).append(a)
    sites = sorted(cg_sites.get(TARGET, []))
    expected = {tuple(int(x, 16) for x in p.split(":")) for p in EXPECTED.split()}
    got = {(c, func_of(c)) for c in sites}
    if len(sites) != 60 or got != expected:
        sys.exit(f"直接 call の集合が想定と違う: 件数 {len(sites)}, 差分 {sorted(got ^ expected)}")

    rows = [analyze(c) for c in sites]
    print("\t".join(["call_va", "caller_fn", "setter_va", "setter_asm", "class", "value_or_source", "note"]))
    for w in rows:
        print("\t".join(clean(x) for x in [
            f"0x{w['site']:x}", f"0x{w['fn']:x}", w["setter_va"], w["setter_asm"], w["cls"], w["value"], w["note"],
        ]))

    order = ["IMM", "COPY", "MEM", "ARITH", "ENTRY", "AMBIG", "UNKNOWN"]
    cnt = collections.Counter(w["cls"] for w in rows)
    err = sys.stderr.write
    err(f"ablate={sorted(ABLATE) or 'none'} 直接 call {len(rows)} 箇所 (未解決 jmp 先 {unresolved_jumps} 件)\n")
    err("class counts: " + ", ".join(f"{k}={cnt.get(k, 0)}" for k in order) + "\n")
    imm = collections.defaultdict(list)
    for w in rows:
        if w["cls"] == "IMM":
            imm[w["value"].split(" ")[0]].append(f"0x{w['site']:x}")
    for k in sorted(imm, key=lambda x: (len(x), x)):
        err(f"IMM {k}: {len(imm[k])} 件 {', '.join(imm[k])}\n")
    for k in ("ENTRY", "AMBIG", "UNKNOWN"):
        for w in rows:
            if w["cls"] == k:
                err(f"{k} 0x{w['site']:x} (in 0x{w['fn']:x}): {w['value']} | {w['note']}\n")


if __name__ == "__main__":
    main()
