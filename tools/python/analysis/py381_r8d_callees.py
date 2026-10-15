#!/usr/bin/env python3
"""PY-381 (#5295): r8d mask 0x4 の tail 到達側の呼出し先の中身を読む (実機不要)。

  python3 analysis/py381_r8d_callees.py <PE.bin> <work/py4769/r8d_single.tsv> <outdir> [--negctl] [--appendix=<path.md>]

入力: py4769 の TSV。mask 0x4 かつ tail 到達側の calls 列から、直接呼出し先 VA を集める。
各呼出し先 VA から、分岐の両辺を辿る (有界: 4096 命令・ret で止める)。集計:
  writes5b8 : [rbp+0x5b8] への書込み命令の VA (py4769 と同じスロット)
  writes_abs: [rbp+0x5b8] 以外の書込み命令のうち、RIP 相対・絶対アドレスのもの (グローバル候補)
  writes_oth: それ以外のメモリ書込み (レジスタ基底。基底の指す先は静的に決まらない)
  calls     : 直接 call の呼出し先 / indirect call (間接呼出し) の数
  ret       : ret に届くか / unbounded : 上限で打ち切ったか
検算: 辿った全命令について capstone と objdump -D (intel) の (mnemonic, 正規化した被演算子) を照合する。
負の対照 (--negctl): 照合の 1 件を故意に壊し、mismatch が出ることを確かめる。
出力: <outdir>/callees.tsv (呼出し先ごとの 1 行)・<outdir>/sides.tsv (判定の側ごと)・--appendix 指定時は Markdown 表
間接 jmp (レジスタ先・メモリ先) は辿れないため、indirect_jmps 列に数えて明示する (黙って打ち切らない)。
"""
import csv
import os
import re
import subprocess
import sys

import capstone
import pefile

LIMIT = 4096
EXTRA = (0xF8D730, 0xF8D580, 0xF783C0)
WRITE_MN = re.compile(
    r"^(mov|movs[sd]?|movzx|movsx|and|or|add|sub|xor|inc|dec|neg|not|shl|shr|sar|rol|ror|"
    r"set\w*|cmov\w*|xchg|btr|bts|btc|adc|sbb|movups|movaps|movdqu|movdqa|movq|movd|cmpxchg)$"
)
MEM_RE = re.compile(r"\[[^\]]*\]")


def load_pe(path):
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    sec = next(s for s in pe.sections if s.Name.startswith(b".text"))
    with open(path, "rb") as f:
        data = f.read()
    start = base + sec.VirtualAddress
    raw = data[sec.PointerToRawData:sec.PointerToRawData + sec.SizeOfRawData]
    return start, raw


def norm(mn, ops):
    s = f"{mn} {ops}".lower()
    s = s.replace("+0x0]", "]")
    s = re.sub(r"\s*([\[\]+,-])\s*", r"\1", s)
    s = re.sub(r"(?<![0-9a-fx])(\d+)\b", lambda m: f"{int(m.group(1)):#x}", s)
    s = re.sub(r"rip-(0x[0-9a-f]+|\d+)\b", lambda m: f"rip+{(-int(m.group(1), 0)) & 0xffffffff:#x}", s)
    s = re.sub(r"rip\+0xffffffff([0-9a-f]{8})\b", lambda m: f"rip+{int(m.group(1), 16):#x}", s)
    s = re.sub(r"-(0x[0-9a-f]+|\d+)\b", lambda m: f"-{int(m.group(1), 0):#x}", s)
    s = re.sub(r"(e[a-z]{2}),-0x1$", r"\1,0xffffffff", s)
    s = re.sub(r"(?<![-0-9a-fx])(0x[0-9a-f]+)\b", lambda m: f"{int(m.group(1), 0) & 0xffffffff:#x}", s)
    return s.replace(" ", "")


def walk(md, start, raw, entry):
    """capstone で entry から分岐の両辺を辿る。返り値: {va: (mn, ops, size)}, ret, unbounded, indirect_calls, indirect_jmps"""
    seen, stack, ins = set(), [entry], {}
    ret = unbounded = False
    ind = ind_j = 0
    while stack:
        a = stack.pop()
        if a in seen:
            continue
        if len(seen) >= LIMIT:
            unbounded = True
            break
        off = a - start
        if off < 0 or off >= len(raw):
            continue
        i = next(md.disasm(raw[off:off + 16], a), None)
        if i is None:
            continue
        seen.add(a)
        ins[a] = (i.mnemonic, i.op_str, i.size)
        nxt = a + i.size
        mn = i.mnemonic
        if mn == "ret":
            ret = True
            continue
        if mn == "call":
            if re.fullmatch(r"0x[0-9a-f]+", i.op_str.strip()):
                pass
            else:
                ind += 1
            stack.append(nxt)
            continue
        if mn == "jmp":
            if re.fullmatch(r"0x[0-9a-f]+", i.op_str.strip()):
                stack.append(int(i.op_str, 16))
            else:
                ind_j += 1
            continue
        if mn.startswith("j"):
            stack.append(int(i.op_str, 16))
            stack.append(nxt)
            continue
        stack.append(nxt)
    return ins, ret, unbounded, ind, ind_j


def load_objdump_range(pe_path, start, vas):
    """objdump -D の結果から、vas の各 VA の (mn, ops) を引く。範囲は VA の min〜max。"""
    pe = pefile.PE(pe_path, fast_load=True)
    text = next(s for s in pe.sections if s.Name.startswith(b".text"))
    shift = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress - text.PointerToRawData
    out = {}
    for lo, hi in ranges(sorted(vas)):
        txt = subprocess.run(
            ["objdump", "-D", "-b", "binary", "-m", "i386:x86-64", "-M", "intel",
             f"--start-address={lo - shift:#x}", f"--stop-address={hi - shift + 16:#x}", pe_path],
            capture_output=True, text=True, check=True,
        ).stdout
        for ln in txt.splitlines():
            parts = ln.split("\t")
            if len(parts) < 3 or not parts[2].strip():
                continue
            try:
                va = int(parts[0].strip().rstrip(":"), 16) + shift
            except ValueError:
                continue
            mn, _, ops = parts[2].strip().partition(" ")
            ops = ops.split("#", 1)[0].strip()
            if mn == "rex" or mn.startswith("rex."):
                mn, _, ops = ops.partition(" ")
            if (mn.startswith("j") or mn == "call") and re.fullmatch(r"0x[0-9a-f]+", ops):
                ops = f"{int(ops, 16) + shift:#x}"
            out[va] = (mn, ops)
    return out


def ranges(vas, gap=64):
    """VA 列を近いもの同士でまとめ、(lo, hi) の範囲列にする (objdump 呼出し回数を減らすため)。"""
    out = []
    for v in vas:
        if out and v - out[-1][1] <= gap:
            out[-1][1] = max(out[-1][1], v)
        else:
            out.append([v, v])
    return [tuple(x) for x in out]


def write_target(mn, ops):
    if not WRITE_MN.match(mn):
        return None
    first = ops.split(",")[0].strip()
    return first if MEM_RE.search(first) else None


def classify(mem):
    if "0x5b8" in mem.replace(" ", "") and "rbp" in mem.replace(" ", ""):
        return "5b8"
    if "rip" in mem or re.search(r"\[0x[0-9a-f]+\]", mem):
        return "abs"
    return "oth"


def abs_dest(a, mn, ops, size):
    """書込み先の絶対 VA。RIP 相対は命令末尾基準で解決する。解決できなければ None。"""
    m = re.search(r"\[rip ([+-]) (0x[0-9a-f]+)\]", ops)
    if m:
        d = int(m.group(2), 16)
        return (a + size + (d if m.group(1) == "+" else -d)) & 0xFFFFFFFFFFFFFFFF
    m = re.search(r"\[(0x[0-9a-f]+)\]", ops)
    return int(m.group(1), 16) if m else None


def write_appendix(path, sides, per):
    """判定 (側ごと) の表と、呼出し先ごとの表を Markdown で書く。値はすべて per (解析結果) から作る。"""
    lines = ["| 判定 VA | mask | 側 | 呼出し先 (直接) | グローバル書込み命令 VA | 解決先 VA | 間接 call |",
             "|---|---|---|---|---|---|---|"]
    for site, side, entry, cs in sides:
        gva, ind = {}, 0
        for c in cs:
            ins, _, _, ic, _ = per[c]
            ind += ic
            for a in ins:
                mn, ops, size = ins[a]
                w = write_target(mn, ops)
                if w and classify(w) == "abs":
                    gva[a] = abs_dest(a, mn, ops, size)
        dests = sorted({d for d in gva.values() if d is not None})
        lines.append(f"| {site} | 0x4 | {side} | {len(cs)} | {' '.join(f'{a:#x}' for a in sorted(gva)) or '-'} | {' '.join(f'{d:#x}' for d in dests) or '-'} | {ind} |")
    lines += ["", "| 判定 VA | 立ちだけが呼ぶ呼出し先 | 落ちだけが呼ぶ呼出し先 |", "|---|---|---|"]
    by_site = {}
    for site, side, entry, cs in sides:
        by_site.setdefault(site, {})[side] = set(cs)
    for site in sorted(by_site):
        st, fa = by_site[site].get("立ち", set()), by_site[site].get("落ち", set())
        only_st = " ".join(f"{t:#x}" for t in sorted(st - fa)) or "-"
        only_fa = " ".join(f"{t:#x}" for t in sorted(fa - st)) or "-"
        lines.append(f"| {site} | {only_st} | {only_fa} |")
    lines += ["", "| 呼出し先 | 命令数 | ret | 未読 (上限打切) | 間接 call | 間接 jmp | 基底レジスタ経由の書込み命令数 |",
              "|---|---|---|---|---|---|---|"]
    for t in sorted(per):
        ins, ret, unb, ind, ind_j = per[t]
        wo = sum(1 for a in ins if (w := write_target(ins[a][0], ins[a][1])) and classify(w) == "oth")
        lines.append(f"| {t:#x} | {len(ins)} | {'到達' if ret else '未到達'} | {'はい' if unb else 'いいえ'} | {ind} | {ind_j} | {wo} |")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    negctl = "--negctl" in sys.argv
    appendix = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--appendix=")), None)
    pe_path, tsv_path, outdir = args[0], args[1], args[2]
    start, raw = load_pe(pe_path)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    targets = set(EXTRA)
    sides = []
    with open(tsv_path) as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r["mask"] != "0x4" or r["tail"] != "True":
                continue
            cs = []
            for c in r["calls"].split(";"):
                if ":" not in c or c == "-":
                    continue
                t = c.split(":", 1)[1]
                if re.fullmatch(r"0x[0-9a-f]+", t):
                    targets.add(int(t, 16))
                    cs.append(int(t, 16))
            sides.append((r["site"], r["side"], r["entry"], cs))

    rows, mismatch, checked = [], 0, 0
    all_vas = set()
    per = {}
    for t in sorted(targets):
        ins, ret, unb, ind, ind_j = walk(md, start, raw, t)
        per[t] = (ins, ret, unb, ind, ind_j)
        all_vas |= set(ins)
    ob = load_objdump_range(pe_path, start, all_vas)
    for t in sorted(targets):
        ins, ret, unb, ind, ind_j = per[t]
        w5, wa, wo, calls = [], [], [], []
        for a in sorted(ins):
            mn, ops, _ = ins[a]
            checked += 1
            exp = ob.get(a)
            got = norm(mn, ops)
            if negctl and a == min(ins):
                got = got + "x"
            if exp is None or norm(*exp) != got:
                mismatch += 1
            w = write_target(mn, ops)
            if w:
                k = classify(w)
                {"5b8": w5, "abs": wa, "oth": wo}[k].append(f"{a:#x}:{mn} {ops}")
            if mn == "call":
                calls.append(f"{a:#x}:{ops}")
        rows.append([
            f"{t:#x}", len(ins), "T" if ret else "F", "T" if unb else "F", ind, ind_j,
            len(w5), ";".join(w5) or "-", len(wa), ";".join(wa) or "-", len(wo), ";".join(wo[:4]) or "-",
            ";".join(calls) or "-",
        ])

    os.makedirs(outdir, exist_ok=True)
    head = ["callee", "insns", "ret", "unbounded", "indirect_calls", "indirect_jmps", "writes5b8", "writes5b8_va",
            "writes_abs", "writes_abs_va", "writes_oth", "writes_oth_head", "calls"]
    with open(os.path.join(outdir, "callees.tsv"), "w") as f:
        f.write("\t".join(head) + "\n")
        for r in rows:
            f.write("\t".join(str(x) for x in r) + "\n")

    side_rows = []
    for site, side, entry, cs in sides:
        w5 = []
        for c in cs:
            ins = per[c][0]
            for a in sorted(ins):
                mn, ops, _ = ins[a]
                w = write_target(mn, ops)
                if w and classify(w) == "5b8":
                    w5.append(f"{a:#x}")
        side_rows.append((site, side, entry, len(cs), len(w5)))
    with open(os.path.join(outdir, "sides.tsv"), "w") as f:
        f.write("site\tside\tentry\tcallees\twrites5b8_in_callees\n")
        for r in side_rows:
            f.write("\t".join(str(x) for x in r) + "\n")
    if appendix:
        write_appendix(appendix, sides, per)
    print(f"callees={len(targets)} insns_checked={checked} mismatch={mismatch}")
    if negctl:
        print("negctl: 1 件を故意に壊した (mismatch>=1 が期待値)")
        return 0 if mismatch >= 1 else 1
    return 0 if mismatch == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
