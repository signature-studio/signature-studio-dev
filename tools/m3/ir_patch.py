#!/usr/bin/env python3
# M3-2: RetDec (LLVM 12 系) 吐き出し .ll を「wasm 再コンパイル可能形へ」機械変換する
#       M3 本パイプラインの中核 (M2 tools/m2/ir_normalize.py の継承 + M3 追加パス)。
#
# python3 ir_patch.py IN.ll OUT.ll [--select f1,f2,...] [--report OUT.json] [--keep-all]
#
# 変換ステージ (REPORT.md にこの番号で数える):
#   [A1] target datalayout を wasm32 互換へ差し替え
#   [A2] 型付きポインタ → opaque `ptr` 統一
#   [A3] ポインタ間 bitcast (no-op) の除去
#   [A4] `zext (i32 xor (i32 A, i32 A) to i64)` → 0 (RetDec のアドレス identity)
#   [A5] %wide-string 等の名前付き定数参照破損 → zeroinitializer
#   [A6] ptrtoint 幅不整合 (to i32) を to i64 へ
#   [A7] !insn.addr / !range メタデータ・uselistorder の除去 (後段パッチの安定化)
#   [A8] 算術 constexpr (LLVM 17+ 廃止組, 定数のみ) の値畳み込み
#   [A9] 残存 constexpr (シンボル参照組) の検出・計上 — count-only。
#        命令化 lift は未実装で, 残存が 0 でない .ll は LLVM 24 (emsdk clang)
#        でコンパイル不可 (中規模 mm closure IR の現ブロッカー)。
#   [B1] 「store 無し alloca への load」(未初期化スタック読み, M2 既知課題 (e))
#        を値 0 の xor 型化で決定論化
#   [B2] declare/define の重複・signature 衝突の除去 = 実測 (衝突数を記録)
#   [C1] --select 指定関数から call-graph 閉包選別 (抽出済み関数のみ再 compile)
#        選別外への参照は declare として残す → gen_imports.py の stub 自動生成へ

import argparse
import json
import re
import sys

DATALAYOUT_WASM = ('target datalayout = "e-m:e-p:32:32-p10:8:8-p20:8:8-i64:64-i128:128'
                   '-f128:64-n32:64-S128-ni:1:10:20"')


def stage(tag, msg):
    print(f"[ir_patch]   [{tag}] {msg}", file=sys.stderr)


def fold_const_ops(text):
    """`op (iN a, iN b)` で a/b が両方整数定数のものを値に畳む。zext/trunc/sext も含む。
    LLVM 17+ では arithmetic constexpr が廃止されたため, RetDec 産の constexpr 残りを
    数値に畳んで残す。シンボル参照 (ptrtoint @sym 等) を含む場合は畳まない (= 後段へ)。"""
    OPS = {
        "xor": lambda a, b: a ^ b, "and": lambda a, b: a & b,
        "or": lambda a, b: a | b, "add": lambda a, b: a + b,
        "sub": lambda a, b: a - b, "mul": lambda a, b: a * b,
        "shl": lambda a, b: a << (b % 64), "lshr": lambda a, b: a >> (b % 64),
        "ashr": lambda a, b: a >> (b % 64),
        "udiv": lambda a, b: a // b if b else 0,
        "srem": lambda a, b: (abs(a) % abs(b)) * (1 if a >= 0 else -1) if b else 0,
    }
    n = 0
    for name, f in OPS.items():
        pos = 0
        while True:
            idx = text.find(f"{name} (i", pos)
            if idx < 0:
                break
            open_idx = text.find("(", idx)
            depth = 0
            j = open_idx
            L = len(text)
            while j < L:
                c = text[j]
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if j >= L:
                break
            inner = text[open_idx + 1:j]
            parts, cdepth, cur = [], 0, []
            for c in inner:
                if c == "," and cdepth == 0:
                    parts.append("".join(cur))
                    cur = []
                    continue
                if c == "(":
                    cdepth += 1
                elif c == ")":
                    cdepth -= 1
                cur.append(c)
            parts.append("".join(cur))
            done = False
            if len(parts) == 2:
                a = re.sub(r"^[iif]\d+ ", "", parts[0].strip())
                b = re.sub(r"^[iif]\d+ ", "", parts[1].strip())
                if a.lstrip("-").isdigit() and b.lstrip("-").isdigit():
                    av, bv = int(a), int(b)
                    val = f(av, bv)
                    text = text[:idx] + str(val) + text[j + 1:]
                    pos = max(idx - 80, 0)
                    n += 1
                    done = True
            if not done:
                pos = j + 1
    # 単項型換算 (zext/trunc/sext): `op (iN K to iM)`
    for w in ("zext", "trunc", "sext"):
        pos = 0
        while True:
            idx = text.find(f"{w} (i", pos)
            if idx < 0:
                break
            open_idx = text.find("(", idx)
            depth = 0
            j = open_idx
            L = len(text)
            while j < L:
                c = text[j]
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if j >= L:
                break
            inner = text[open_idx + 1:j]
            m = re.fullmatch(r"([iif]\d+)\s+(-?\d+)\s+to\s+([iif]\d+)", inner.strip())
            if m:
                k = int(m.group(2))
                tid = int(m.group(3)[1:])
                v = k & ((1 << tid) - 1)
                text = text[:idx] + str(v) + text[j + 1:]
                pos = max(idx - 80, 0)
                n += 1
                continue
            pos = j + 1
    return text, n


def fold_xor_identity(text):
    """`xor (iN A, iN B)` で A==B な二項を 0 に畳む (括弧バランス追跡スキャン)。"""
    n = 0
    pos = 0
    while True:
        idx = text.find("xor (i", pos)
        if idx < 0:
            break
        open_idx = text.find("(", idx)
        if open_idx < 0:
            break
        depth = 0
        j = open_idx
        L = len(text)
        while j < L:
            c = text[j]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j >= L:
            pos = idx + 1
            continue
        inner = text[open_idx + 1:j]
        parts = []
        cdepth = 0
        cur = []
        for c in inner:
            if c == "," and cdepth == 0:
                parts.append("".join(cur))
                cur = []
                continue
            if c == "(":
                cdepth += 1
            elif c == ")":
                cdepth -= 1
            cur.append(c)
        parts.append("".join(cur))
        if len(parts) == 2:
            a, b = (x.strip() for x in parts)
            va = re.sub(r"^(?:[iif]\d+|ptr)\s+", "", a).strip()
            vb = re.sub(r"^(?:[iif]\d+|ptr)\s+", "", b).strip()
            if va and va == vb:
                text = text[:idx] + "0" + text[j + 1:]
                pos = max(idx - 60, 0)
                n += 1
                continue
        pos = j + 1
    return text, n


def normalize(text):
    # [A1] datalayout
    n = len(re.findall(r'(?m)^target datalayout = "', text))
    text = re.sub(r'(?m)^target datalayout = ".*"$', DATALAYOUT_WASM, text)
    stage("A1", f"datalayout 書換 {n} 行")

    # [A5] 名前付き定数参照破損
    c = len(re.findall(r"constant \[[0-9]+ x i(?:16|8)\]\s+%[\w.\-]+", text))
    text = re.sub(r"(constant \[[0-9]+ x i(?:16|8)\])\s+(?:%[\w.\-]+)",
                  r"\1 zeroinitializer", text)
    stage("A5", f"named-constant 参照破損 {c} 件")

    # [A4] xor identity (nested/ptrtoint 形も含めて値スキャンで畳む)
    text, n4 = fold_xor_identity(text)
    stage("A4", f"xor identity {n4} 件")

    # [A8] 定数操作 constexpr の値畳み込み (LLVM 17+ では constexpr が廃止)
    ntot = 0
    for _ in range(6):
        text, n8 = fold_const_ops(text)
        ntot += n8
        if n8 == 0:
            break
    stage("A8", f"定数操作 constexpr 畳み込み {ntot} 件")

    # [A3] bitcast pointer→pointer (no-op)
    c3 = len(re.findall(r"bitcast \((?:i[0-9]+|%[\w.\-]+)\*", text))
    text = re.sub(r"bitcast \((?:i[0-9]+|%[\w.\-]+)\* ([^)]+) "
                  r"to (?:i[0-9]+|%[\w.\-]+)\*\)", r"\1", text)

    # [A2] 型付きポインタ → opaque ptr
    for _ in range(4):
        prev = text
        text = re.sub(r"%[\w.\-]+\*", "ptr", text)
        text = re.sub(r"i[0-9]+\*", "ptr", text)
        text = re.sub(r"(?<![\w])ptr\*", "ptr", text)
        if text == prev:
            break
    stage("A2/A3", f"opaque pointer 化 + bitcast 除去 {c3} 件")

    # [A6] ptrtoint (… to i32) → i64
    n6 = len(re.findall(r"ptrtoint \(.*? to i32\)", text))
    text = re.sub(r"ptrtoint \((?:ptr|%[\w.\-]+) (@[\w.\-]+) to i32\)",
                  lambda m: f"ptrtoint (ptr {m.group(1)} to i64)", text)
    text = re.sub(r"ptrtoint \(ptr (%[\w.\-]+) to i32\)",
                  lambda m: f"ptrtoint (ptr {m.group(1)} to i64)", text)
    stage("A6", f"ptrtoint 幅正規化 {n6} 件")

    # [A7] メタデータ・uselistorder
    cmeta = len(re.findall(r", *!\w[\w.\-]* +", text))
    text = re.sub(r", *!\w[\w.\-]* +\S+", "", text)          # ", !insn.addr !0" 形式
    text = re.sub(r"(?<=\)) +!\w[\w.\-]* +\S+", "", text)    # ") !insn.addr !0" 形式
    text = re.sub(r", *!\w[\w.\-]*(?=[,)])", "", text)   # ", !f" 単発
    text = re.sub(r"(?m)^!\w[\w.\-]* *= !\{.*\}\s*\n?", "", text)  # 定義行

    cuse = len(re.findall(r"(?m)^uselistorder", text))
    text = re.sub(r"(?m)^\s*uselistorder .*\n", "", text)
    text = re.sub(r"(?m)^; uselistorder directives\n", "", text)
    text = re.sub(r"(?m)^\n\n\n+", "\n\n", text)
    stage("A7", f"メタデータ {cmeta} 件・uselistorder 行 {cuse} 本 除去")
    return text


def parse_functions(text):
    """{ fnname: (define 行含む本文スライス) } を返す。"""
    starts = []
    for m in re.finditer(r'(?m)^define \w[\w*]+ ?[@"]([^(\s,]+)\(', text):
        starts.append((m.group(1), m.start()))
    starts.append(("__EOF__", len(text)))
    blocks = {}
    for i, (nm, st) in enumerate(starts[:-1]):
        blocks[nm] = text[st:starts[i + 1][1]]
    return blocks


def patch_uninit_alloca(blocks):
    """[B1] store されない alloca への load を値 0 に決定論化 (型は load の幅を踏襲)。"""
    nfix = 0
    for name, body in blocks.items():
        allocas = set(re.findall(r"(?m)^  (%[\w.\-]+) = \w* ?alloca", body))
        if not allocas:
            continue
        # bitcast 経由の alias (残存 bitcast ptr→ptr) も store 対象として認識する
        alias_names = set(re.findall(r"= bitcast ptr (%[\w.\-]+) to ptr", body))
        for a in sorted(allocas | alias_names):
            esc = re.escape(a)
            if re.search(r"(?m)^  store .*?ptr " + esc + r"(?=[,)\s])", body):
                continue
            body, cnt = re.subn(r"= load (\w+), ptr " + esc + r"(?=[ ,)\n])",
                                lambda m: f"= xor {m.group(1)} 0, 0", body)
            if cnt:
                nfix += cnt
        # 修正後の本文を blocks へ書き戻す (後段 select / 出力への反映)
        blocks[name] = body
    stage("B1", f"未初期化 alloca load → 値 0 (決定論化) {nfix} 件")
    return blocks, nfix


CE_ARITH = ("and", "or", "xor", "add", "sub", "mul", "shl", "lshr", "ashr",
            "udiv", "urem", "srem", "ptrtoint", "inttoptr", "zext", "sext",
            "trunc", "bitcast")


def _paren_span(text, open_idx):
    depth = 0
    j = open_idx
    L = len(text)
    while j < L:
        c = text[j]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                break
        j += 1
    return j if depth == 0 else -1


def _innermost_constexpr(line):
    """行内の最も内側の constexpr 候補 (op + '(...)' / op の前が識別子外) を返す。
    返値: (op, start, end, inner) / 見付からなければ None。"""
    best = None
    for op in CE_ARITH:
        pos = 0
        while True:
            idx = line.find(f"{op} (", pos)
            if idx < 0:
                break
            # 前の文字が識別子の一部 (関数名・%名・文字列内) なら constexpr ではない
            if idx > 0 and (line[idx - 1].isalnum() or line[idx - 1] in "%@._$"):
                pos = idx + 1
                continue
            open_idx = idx + len(op) + 1
            end = _paren_span(line, open_idx)
            if end < 0:
                pos = idx + 1
                continue
            inner = line[open_idx + 1:end]
            cand = (op, idx, end + 1, inner)
            if best is None or len(inner) < len(best[3]):
                best = cand
            pos = idx + 1
    return best


def collect_declare_lists(full_text, defined_names):
    """declare 行を収集し、「define で定義済み」への重複宣言は捨てる [B2]。
    同名・非同型 declare (signature 衝突) は bad に記録する (実測用)。"""
    seen_sig = {}
    bad = []
    keep = []
    for m in re.finditer(r"(?m)^declare (\S+)(.*?)(@[\w$.]+)(\(.*?\))( .*?)?$", full_text):
        ret, _, name, sig, tail = m.groups()
        sig_key = (ret, sig)
        if name in defined_names:
            continue
        prev = seen_sig.get(name)
        if prev is not None and prev != sig_key:
            bad.append((name, prev, sig_key))
        seen_sig[name] = sig_key
        keep.append(m.group(0))
    return keep, bad


def count_constexpr(text):
    """[A9] LLVM 17+ で廃止された constexpr の残存を検出・計上する。
    本 pass は現状 count-only (残存数の網羅管理用)。残存 constexpr が
    instruction 化されない限り LLVM 24 系 (emsdk clang) では .ll コンパイルが
    落ちる — これが中規模 IR (mm closure) の wasm 化の現ブロッカー。"""
    n = {}
    for op in CE_ARITH + ("getelementptr",):
        n[op] = len(re.findall(rf"(?<![\w]){op} \(", text))
    return n


def closure_select(blocks, seeds):
    """seeds から呼出 (call および @関数名参照) の閉包を選別。外部 (非 define) を返す。"""
    seen, ext = set(), {}
    for s in seeds:
        if s not in blocks:
            sys.exit(f"[ir_patch] FAIL: --select {s} が IR define 一覧にありません")
        stk = [s]
        while stk:
            f = stk.pop()
            if f in seen:
                continue
            seen.add(f)
            body = blocks[f]
            for m in re.finditer(r"@([^\s,(]+)", body):
                c = m.group(1)
                if c in blocks:
                    if c not in seen:
                        stk.append(c)
                elif not c.startswith("llvm.") and not c.startswith("__asm_"):
                    ext[c] = ext.get(c, 0) + 1
    return seen, ext


def do_select(blocks, full, seeds):
    seen, ext = closure_select(blocks, seeds)
    join_all = "\n".join(blocks[f] for f in seen)
    globals_needed = set(m.group(1) for m in re.finditer(r"(@[\w$.]+)", join_all))
    keep_globals, keep_globals_name = [], []
    for m in re.finditer(r"(?ms)^(@[\w$.]+) = .*?(?=\n\n|^declare )", full):
        if m.group(1) in globals_needed:
            keep_globals.append(m.group(0))
            keep_globals_name.append(m.group(1))
    want = (set(ext) | (globals_needed - set(keep_globals_name))) - set(seen)
    declare_bodies, bad = collect_declare_lists(full, set(seen))
    declares = [d for d in declare_bodies
                if re.match(r"declare \S+.*?@([\w$.]+)\(", d).group(1) in want]
    return keep_globals, sorted(seen), declares, sorted(ext), bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("infile")
    ap.add_argument("outfile")
    ap.add_argument("--select", default="")
    ap.add_argument("--keep-all", action="store_true")
    ap.add_argument("--report", default="")
    args = ap.parse_args()

    full = open(args.infile).read()
    full = normalize(full)
    # [A9] 残存 constexpr の検出・計上 (lift 実装は未実装 — REPORT 参照; 未 lift 分の計上管理)
    ce_res = count_constexpr(full)
    n_ce = sum(ce_res.values())
    stage("A9", f"残存 constexpr {n_ce} 件 " +
          " ".join(f"{k}:{v}" for k, v in ce_res.items() if v))
    blocks = parse_functions(full)
    blocks, nfix = patch_uninit_alloca(blocks)

    if args.select and not args.keep_all:
        seeds = [s for s in args.select.split(",") if s]
        keep_globals, keep_fns, declares, exts, bad = do_select(blocks, full, seeds)
        pre = re.match(r'(?ms)(.*?)(?=\ndefine )', full)
        head = pre.group(1) if pre else ""
        text = head.rstrip() + "\n\n" + "\n\n".join(g.rstrip() for g in keep_globals)
        text += "\n\n" + "\n\n".join(blocks[f].rstrip() for f in keep_fns)
        text += "\n\n" + "\n".join(declares) + "\n"
        stage("C1", f"閉包 {len(keep_fns)} 関数 / 外部参照 {len(exts)} 件")
    else:
        pre = re.match(r'(?ms)(.*?)(?=\ndefine )', full)
        head = pre.group(1) if pre else ""
        declares, bad = collect_declare_lists(full, set(blocks))
        text = (head.rstrip() + "\n\n" + "\n\n".join(
            b.rstrip() for b in blocks.values()) + "\n\n" + "\n".join(declares) + "\n")
        stage("C1", "keep-all (全 define 維持)")

    with open(args.outfile, "w") as fh:
        fh.write(text)
    print(f"[ir_patch] wrote {args.outfile}")
    if args.report:
        with open(args.report, "w") as fh:
            json.dump({"input": args.infile, "output": args.outfile,
                       "b1_fixed": nfix, "b2_sig_collisions": len(bad),
                       "a9_residual_constexpr": sum(count_constexpr(text).values()),
                       "stages": ["A1", "A2", "A3", "A4", "A5", "A6", "A7",
                                  "B1", "B2", "A9", "C1"]}, fh, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
