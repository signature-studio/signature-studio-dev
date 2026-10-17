#!/usr/bin/env python3
"""PY-5390 (#5801): mask 0x4 tail 側の未確認呼出し先 5 件の、2 段目 (その直接の呼出し先) の書込み先を判定ごとに集計する (実機不要)。

  python3 analysis/py5801_callees2.py <PE.bin> <work/py4769/r8d_single.tsv> <outdir>

入力: py4769 の TSV (mask 0x4 かつ tail 到達側)。
1 段目 = 名指しの 5 件 (NAMED)。各 1 段目を py381 の walk (有界・分岐の両辺) で辿り、そこに現れる直接 call の呼出し先を 2 段目とする。
2 段目の各関数について、書込み命令を 5b8 / RIP 相対・絶対 (グローバル候補) / 基底レジスタ経由 に分ける。
検算: py381 の verify (capstone と objdump の mnemonic・被演算子の照合) を 1 段目・2 段目の全命令に行う。負の対照は先頭命令の照合を壊す。
出力: <outdir>/l2_by_site.tsv (判定の側ごとに、名指しの 1 段目・その 2 段目の VA と書込み数)・<outdir>/l2_callees.tsv (2 段目の関数ごと)。
"""
import csv
import os
import re
import sys

import capstone

from py381_r8d_callees import (abs_dest, classify, load_objdump_range, load_pe, norm,
                               walk, write_target)

NAMED = (0x605020, 0x414BB0, 0x414DA0, 0x11F16B0, 0x11F22F0)


def canon(mn, ops):
    """capstone と objdump の表記差を消して py381 の norm に渡す。サイズ語・セグメント接頭辞・*1 の省略・+0x0・rep の分け方・即値の 10 進/16 進を揃える。被演算子の意味は変えない。"""
    s = f"{mn} {ops}".lower()
    s = re.sub(r"\b(byte|word|dword|qword|xmmword|ymmword|ptr)\b", "", s)
    s = s.replace("es:", "").replace("ds:", "").replace("*1", "").replace("+0x0]", "]")
    s = re.sub(r"\brep\b", "", s).replace("movsb", "movs")
    s = re.sub(r"\s+", " ", s).strip()
    mn2, _, ops2 = s.partition(" ")
    ops2 = re.sub(r"(?<![0-9a-fx])(\d+)\b", lambda m: f"{int(m.group(1)):#x}", ops2)
    return norm(mn2, ops2)


def check(per, ob, negctl):
    checked = mismatch = 0
    for t in sorted(per):
        ins = per[t][0]
        for a in sorted(ins):
            mn, ops, _ = ins[a]
            checked += 1
            exp = ob.get(a)
            got = canon(mn, ops)
            if negctl and a == min(ins):
                got = got + "x"
            if exp is None or canon(*exp) != got:
                mismatch += 1
    return checked, mismatch


def direct_calls(ins):
    out = []
    for a in sorted(ins):
        mn, ops, _ = ins[a]
        if mn == "call" and re.fullmatch(r"0x[0-9a-f]+", ops.strip()):
            out.append(int(ops, 16))
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    appendix = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--appendix=")), None)
    pe_path, tsv_path, outdir = args[0], args[1], args[2]
    start, raw = load_pe(pe_path)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

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
                    cs.append(int(t, 16))
            sides.append((r["site"], r["side"], r["entry"], cs))

    per1 = {t: walk(md, start, raw, t) for t in NAMED}
    l2 = {}
    for t in NAMED:
        for c in direct_calls(per1[t][0]):
            l2.setdefault(c, set()).add(t)
    per2 = {t: walk(md, start, raw, t) for t in sorted(l2)}

    allv = set()
    for per in (per1, per2):
        for t in per:
            allv |= set(per[t][0])
    ob = load_objdump_range(pe_path, start, allv)
    per_all = {**per1, **per2}
    checked, mismatch = check(per_all, ob, False)
    _, neg = check(per_all, ob, True)

    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "l2_callees.tsv"), "w") as f:
        f.write("callee2\tcalled_by_named\tinsns\tret\tunbounded\tind_calls\tind_jmps\twrites5b8\twrites_abs\twrites_oth\n")
        for t in sorted(per2):
            ins, ret, unb, ind, ind_j = per2[t]
            cnt = {"5b8": 0, "abs": 0, "oth": 0}
            absl = []
            for a in sorted(ins):
                mn, ops, size = ins[a]
                w = write_target(mn, ops)
                if not w:
                    continue
                k = classify(w)
                cnt[k] += 1
                if k == "abs":
                    d = abs_dest(a, mn, ops, size)
                    absl.append(f"{a:#x}->{d:#x}" if d is not None else f"{a:#x}->?")
            by = " ".join(f"{x:#x}" for x in sorted(l2[t]))
            f.write(f"{t:#x}\t{by}\t{len(ins)}\t{'T' if ret else 'F'}\t{'T' if unb else 'F'}\t{ind}\t{ind_j}\t"
                    f"{cnt['5b8']}\t{' '.join(absl) or '-'}\t{cnt['oth']}\n")

    with open(os.path.join(outdir, "l1_writes.tsv"), "w") as f:
        f.write("callee1\tinsns\tret\tunbounded\tind_calls\tind_jmps\twrites5b8\twrites_abs\twrites_oth\n")
        for t in NAMED:
            ins, ret, unb, ind, ind_j = per1[t]
            cnt = {"5b8": 0, "abs": 0, "oth": 0}
            absl = []
            for a in sorted(ins):
                mn, ops, size = ins[a]
                w = write_target(mn, ops)
                if not w:
                    continue
                k = classify(w)
                cnt[k] += 1
                if k == "abs":
                    d = abs_dest(a, mn, ops, size)
                    absl.append(f"{a:#x}->{d:#x}" if d is not None else f"{a:#x}->?")
            f.write(f"{t:#x}\t{len(ins)}\t{'T' if ret else 'F'}\t{'T' if unb else 'F'}\t{ind}\t{ind_j}\t"
                    f"{cnt['5b8']}\t{' '.join(absl) or '-'}\t{cnt['oth']}\n")

    with open(os.path.join(outdir, "l2_by_site.tsv"), "w") as f:
        f.write("site\tside\tnamed_callees\tl2_callees\n")
        for site, side, entry, cs in sides:
            nm = [t for t in NAMED if t in cs]
            l2s = sorted({c for t in nm for c in direct_calls(per1[t][0])})
            f.write(f"{site}\t{side}\t{' '.join(f'{t:#x}' for t in nm) or '-'}\t"
                    f"{' '.join(f'{c:#x}' for c in l2s) or '-'}\n")

    if appendix:
        write_appendix(appendix, sides, per1, per2, l2, (checked, mismatch, neg))
    print(f"named={len(NAMED)} l2={len(per2)} insns_checked={checked} mismatch={mismatch} negctl={neg}")
    return 0 if mismatch == 0 and neg >= 1 else 1


def write_appendix(path, sides, per1, per2, l2, meta):
    """判定ごとの 2 段目の表 (付録 Markdown)。値はすべて解析結果から作る。手で編集しない。"""
    checked, mismatch, neg = meta
    lines = ["# PY-5390 (#5801) 付録: mask 0x4 tail 側の未確認呼出し先 5 件の 2 段目の書込み先", "",
             "> 生成元: `analysis/py5801_callees2.py <PE.bin> <work/py4769/r8d_single.tsv> <outdir> --appendix=<path>` の出力 (解析器が書く。手で編集していない)。",
             "> 再現 (素材 `fl-win64` の `block00031_PE.bin` を `work/py5801/extracted/` に展開してから、`tools/python` で実行): "
             "`python3 analysis/py53_dispatch.py work/py5801/extracted/block00031_PE.bin work/py5801/py53` → "
             "`python3 analysis/py4769_r8d_single.py work/py5801/extracted/block00031_PE.bin work/py5801/py53/fn.txt work/py5801/py4769` → "
             "`python3 analysis/py5801_callees2.py work/py5801/extracted/block00031_PE.bin work/py5801/py4769/r8d_single.tsv work/py5801 --appendix=work/py5801/appendix.md`。",
             f"> 検算: `insns_checked={checked} mismatch={mismatch}`・負の対照 `mismatch={neg}` (先頭命令の照合を壊した)。", "",
             "## 1. 1 段目 (名指しの 5 件) の書込み", "",
             "| 呼出し先 | 命令数 | ret | 未読 | 間接 call | 間接 jmp | `[rbp+0x5b8]` への書込み | グローバル書込み (VA→解決先) | 基底レジスタ経由の書込み |",
             "|---|---|---|---|---|---|---|---|---|"]
    for t in NAMED:
        ins, ret, unb, ind, ind_j = per1[t]
        cnt = {"5b8": 0, "abs": 0, "oth": 0}
        absl = []
        for a in sorted(ins):
            mn, ops, size = ins[a]
            w = write_target(mn, ops)
            if not w:
                continue
            k = classify(w)
            cnt[k] += 1
            if k == "abs":
                d = abs_dest(a, mn, ops, size)
                absl.append(f"{a:#x}→{d:#x}" if d is not None else f"{a:#x}→?")
        lines.append(f"| {t:#x} | {len(ins)} | {'到達' if ret else '未到達'} | {'はい' if unb else 'いいえ'} | {ind} | {ind_j} | "
                     f"{cnt['5b8']} | {' '.join(absl) or '-'} | {cnt['oth']} |")
    lines += ["", "## 2. 2 段目 (1 段目の直接呼出し先) の書込み", "",
              "| 2 段目の呼出し先 | 呼ぶ 1 段目 | 命令数 | ret | 未読 | 間接 call | 間接 jmp | `[rbp+0x5b8]` | グローバル書込み (VA→解決先) | 基底レジスタ経由 |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for t in sorted(per2):
        ins, ret, unb, ind, ind_j = per2[t]
        cnt = {"5b8": 0, "abs": 0, "oth": 0}
        absl = []
        for a in sorted(ins):
            mn, ops, size = ins[a]
            w = write_target(mn, ops)
            if not w:
                continue
            k = classify(w)
            cnt[k] += 1
            if k == "abs":
                d = abs_dest(a, mn, ops, size)
                absl.append(f"{a:#x}→{d:#x}" if d is not None else f"{a:#x}→?")
        by = " ".join(f"{x:#x}" for x in sorted(l2[t]))
        lines.append(f"| {t:#x} | {by} | {len(ins)} | {'到達' if ret else '未到達'} | {'はい' if unb else 'いいえ'} | {ind} | {ind_j} | "
                     f"{cnt['5b8']} | {' '.join(absl) or '-'} | {cnt['oth']} |")
    lines += ["", "## 3. 判定の側ごと (名指しの 1 段目・2 段目の VA)", "",
              "| 判定 | 側 | 名指しの 1 段目 | 2 段目 |", "|---|---|---|---|"]
    for site, side, entry, cs in sides:
        nm = [t for t in NAMED if t in cs]
        l2s = sorted({c for t in nm for c in direct_calls(per1[t][0])})
        if not nm:
            continue
        lines.append(f"| {site} | {side} | {' '.join(f'{t:#x}' for t in nm)} | {' '.join(f'{c:#x}' for c in l2s)} |")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
