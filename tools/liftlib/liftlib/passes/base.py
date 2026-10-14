# [liftlib vendored] tools/m5/ir5_patch.py (+ tools/m2/ir_normalize.py) — 統一基盤の base 正規化。
#   変更点: (1) `!insn.addr` メタデータを保持 (機械語アドレス突合用) (2) ライブラリ API 化 (run_base)
#   (3) sys.exit → 例外。ロジックは元の A1..A9L/B1/S1/C8/C9/C1/C13 を保持。
# M5: RetDec .ll → wasm 再コンパイル可能形の機械変換 (M3 tools/m3/ir_patch.py の継承 + M5 追加パス)。
#
#   python3 ir5_patch.py IN.ll OUT.ll [--select f1,f2,...] [--redirect REDIRECT.json]
#                      [--xmm-arg-map XMM.json] [--report OUT.json] [--keep-all]
#
# M3 継承ステージ: [A1..A8] [B1] [B2] [C1] (ir_patch.py と同一の思想; 詳細は
# tools/m3/REPORT.md 参照)。
#
# M5 追加ステージ:
#   [A9L] 残存 constexpr (LLVM 17+ で廃止された, シンボル参照を含む組) の
#         命令化 lift。M3 の [A9] は count-only だったが, 本実装は実際に
#         instruction へ落とす (ptrtoint/inttoptr は命令形が合法, bitcast
#         ptr→ptr は no-op 除去, 算術 constexpr はレジスタ化)。幅不整合
#         (`store i32 ptrtoint(... to i64)` 相当) は trunc/zext/sext を補って解消。
#   [S1]  SSE __asm_* 疑似宣言 (RetDec の i128 表現) の lower:
#         - `call void @__asm_movups.2(load値, 値)` パターン (16B store が
#           call に化けてポインタが消える — M2 既知 (d) 同型) を
#           元の load アドレスを辿って `store i128` に復元
#         - `@__asm_movss.3` / `@__asm_movss.4` / `@__asm_movd.2` 等の
#           lane 入出力を bitcast/instruction 式に置換 (残りは msimd.c の
#           helper に委譲して declare だけ残す)
#   [C8]  RetDec が entry spill 化した xmm 引数 (未初期化 alloca i128 load)
#         を, 指定 VA の linear memory から load する形に置換 (wasm-に環境で
#         呼び出し側が k を書き込む; x86 の xmm 引数渡しの wasm 写像)
#   [C9]  外部 helper call の redirect (FastMM 内部 alloc/free → shim heap)。
#         --redirect JSON: {"function_XXXX": "mm_alloc"} の形。
#   [C10] select 外 declare の削除 (--prune-external: 未使用 declare を C1 後に掃除)

import argparse
import json
import re
import sys

DATALAYOUT_WASM = ('target datalayout = "e-m:e-p:32:32-p10:8:8-p20:8:8-i64:64-i128:128'
                   '-f128:64-n32:64-S128-ni:1:10:20"')

# ---------------------------------------------------------------
# M3 継承: 定数畳み込み / xor identity / A1..A8 正規化 (m3/ir_patch.py より)
# ---------------------------------------------------------------

# ---- vendored: tools/m2/ir_normalize.py ----
POINTER_TYPE = re.compile(r"i[0-9]+\*")
NAMED_PTR_TYPE = re.compile(r"%[\w.\-]+\*")


def m2_normalize(text: str) -> str:
    # (0) datalayout を wasm32 互換に差し替え (RetDec は x86-64 の datalayout
    #     のまま出すため wasm バックエンドの MachineFunction 作成でいずれも致命)
    text = re.sub(
        r'(?m)^target datalayout = ".*"$',
        'target datalayout = "e-m:e-p:32:32-p10:8:8-p20:8:8-i64:64-i128:128'
        '-f128:64-n32:64-S128-ni:1:10:20"',
        text)

    # (1) wide-string named-constant 破損
    text = re.sub(r"(constant \[[0-9]+ x i(?:16|8)\])\s+(?:%[\w.\-]+)",
                  r"\1 zeroinitializer", text)

    # (3) xor(identical) → 0 (RetDec 特産)
    text = re.sub(r"zext \(i32 xor \(i32 ([^,()]+), \1\) to i64\)", "0", text)

    # (2) bitcast pointer→pointer (opaque への no-op 化) を先に除去
    text = re.sub(r"bitcast \((?:i[0-9]+|%[\w.\-]+)\* ([^)]+) "
                  r"to (?:i[0-9]+|%[\w.\-]+)\*\)", r"\1", text)
    for _ in range(4):
        prev = text
        text = re.sub(r"(?<![\w])ptr\*", "ptr", text)
        text = NAMED_PTR_TYPE.sub("ptr", text)
        text = POINTER_TYPE.sub("ptr", text)
        # これから残るポインタ間 no-op bitcast (`= call ptr bitcast ptr X to ptr,`)
        text = re.sub(r"(= \w+) bitcast ptr ([%\w.\-]+) to ptr, ",
                      r"\1 \2, ", text)
        if text == prev:
            break

    # (2d) ptrtoint の 幅不整合 (ptr @x to i32) → to i64
    #      あわせて呼出先が i32 を期待する constexpr の過大料も ( RetDec が addr
    #      arithmetic を i64 に逃している面) i64→i32 の trunc は当 cam/m2 では不要とし、
    #      呼び出し側の型を i32 期待に合わせる形で trunc (constexpr) 文法
    #      (`trunc (i64 X to i32)`) は LLVM 17+ で constexpr trunc が廃止なので
    #      ここでは *呼出側の引数型を i64 に懐柔済みの形にしかみない* でよい:
    #      RetDecの declare 側引数型はすでに i64 (i64 %arg) なので (m2観測),
    #      i32 期待の形は charset 例外として観察ベースで対応。
    text = re.sub(r"ptrtoint \((ptr|%[\w.\-]+) (@[\w.\-]+) to i32\)",
                  lambda m: f"ptrtoint (ptr {m.group(2)} to i64)", text)
    text = re.sub(r"ptrtoint \(ptr (%[\w.\-]+) to i32\) ",
                  lambda m: f"ptrtoint (ptr {m.group(1)} to i64) ", text)
    return text



# ---- /m2 ----

VERBOSE = False
STAGE_LOG = []


def stage(tag, msg):
    STAGE_LOG.append((tag, msg))
    if VERBOSE:
        print(f"[base]   [{tag}] {msg}", file=sys.stderr)


def fold_const_ops(text):
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


def rename_asm_dot_symbols(text):
    """RetDec の overload 名 (@__asm_movss.3 等) は JS 識別子として無効のため
    (glue 生成が破損する) `__mathN` スタイルへ機械置換する。
    msimd_a*/msimd.c 側は同名 (例: __asm_movss__3) を供給する。"""
    m = re.sub(r"@__asm_([A-Za-z0-9_]+)\.(\d+)", r"@__asm_\1__\2", text)
    n = len(re.findall(r"@__asm_[A-Za-z0-9_]+__\d+", m))
    if n:
        stage("R1", f"__asm_* overload 名置換 {n} 行 (movss.3 → movss__3)")
    # 一旦前段 rename を立てなかった分の subn を入力型の確定 (mu-armor)
    return m


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

    # [A4] xor identity
    text, n4 = fold_xor_identity(text)
    stage("A4", f"xor identity {n4} 件")

    # [A8] 定数操作 constexpr の値畳み込み
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
        # 残存 typed pointer: 配列型 `[N x ty]*` と関数型 `iN (...) *`
        # (ft7 実測: ptrtoint ([3 x i8]* @g to i64), i32 (ptr)* 引数 が
        #  LLVM 17 で parse error になるため opaque 化に含める)
        text, na = re.subn(r"(?<![\w])\[[^\]]*\]\*", "ptr", text)
        text, nf = re.subn(r"(?<![\w])(?:i[0-9]+|float|double|void)\s*\([^()]*\)\s*\*", "ptr", text)
        stage("A2/A3", f"配列/関数型 typed pointer opaque 化 {na + nf} 件")
        if text == prev:
            break
    stage("A2/A3", f"opaque pointer 化 + bitcast 除去 {c3} 件")

    # [A6] ptrtoint (… to i32) → i64 は i64 値位置 (call arg 等) のみ。
    # store i32 等の値位置では元の幅を保持する (ft7 実測: `store i32
    # ptrtoint (ptr @g to i64)` が A9L 命令化後に幅不一致 parse error に)。
    n6 = len(re.findall(r"(?<![\w])i64 ptrtoint \(.*? to i32\)", text))
    text = re.sub(r"(?<![\w])i64 ptrtoint \((?:ptr|%[\w.\-]+) (@[\w.\-]+) to i32\)",
                  lambda m: f"i64 ptrtoint (ptr {m.group(1)} to i64)", text)
    text = re.sub(r"(?<![\w])i64 ptrtoint \(ptr (%[\w.\-]+) to i32\)",
                  lambda m: f"i64 ptrtoint (ptr {m.group(1)} to i64)", text)
    stage("A6", f"ptrtoint 幅正規化 (i64 slot のみ) {n6} 件")

    # [A7] メタデータ・uselistorder
    #   値は常に `!name` 参照ゆえ ` +![\w.\-]+` で止める (\S+ だと区切りのカンマを食み,
    #   `) !insn.addr` のカンマ無し形が残って emcc (clang) のパースエラーになる — CAB-239 修正)
    cmeta = len(re.findall(r", *!(?!insn\.addr)\w[\w.\-]* +!", text))
    text = re.sub(r", *!(?!insn\.addr)\w[\w.\-]* +![\w.\-]+", "", text)
    text = re.sub(r"(?<=\)) +!(?!insn\.addr)\w[\w.\-]* +![\w.\-]+", "", text)
    text = re.sub(r", *!(?!insn\.addr)\w[\w.\-]*(?=[,)])", "", text)
    # insn.addr 参照用の `!N = !{i64 VA}` は保持し, それ以外のメタデータ定義だけ除去
    text = re.sub(r"(?m)^!(?!\d+ = !\{i64 \d+\}\s*$)\w[\w.\-]* *= !\{.*\}\s*\n?", "", text)

    cuse = len(re.findall(r"(?m)^uselistorder", text))
    # RetDec は directive を持つ関数だけ `\n; uselistorder directives\n` を出す。先頭の空行ごと消し,
    # directive の有無 (実行ごとに変わる) が空行数に残らないようにする (#1664)
    text = re.sub(r"(?m)^\n; uselistorder directives\n(?:[ \t]*uselistorder .*\n)*", "", text)
    text = re.sub(r"(?m)^\s*uselistorder .*\n", "", text)
    text = re.sub(r"(?m)^; uselistorder directives\n", "", text)
    text = re.sub(r"(?m)^\n\n\n+", "\n\n", text)
    stage("A7", f"メタデータ {cmeta} 件・uselistorder 行 {cuse} 本 除去")
    return text


def parse_functions(text):
    starts = []
    for m in re.finditer(r'(?m)^define \w[\w*]+ ?[@"]([^(\s,]+)\(', text):
        starts.append((m.group(1), m.start()))
    starts.append(("__EOF__", len(text)))
    blocks = {}
    for i, (nm, st) in enumerate(starts[:-1]):
        blocks[nm] = text[st:starts[i + 1][1]]
    return blocks


def patch_uninit_alloca(blocks):
    nfix = 0
    for name, body in blocks.items():
        allocas = set(re.findall(r"(?m)^  (%[\w.\-]+) = \w* ?alloca", body))
        if not allocas:
            continue
        for a in sorted(allocas):
            esc = re.escape(a)
            if re.search(r"(?m)^  store .*?ptr " + esc + r"(?=[,)\s])", body):
                continue
            def _zero_val(m):
                # xor は integer/byte 型のみ可 (LLVM 17)。ptr 型 load は
                # null 相当の inttoptr i64 0 で置換する (ft7 で xor ptr 0, 0
                # が clang parse error になった実測の修正)。
                ty = m.group(1)
                return ("= inttoptr i64 0 to ptr" if ty == "ptr"
                        else f"= xor {ty} 0, 0")
            # `, align N` 付き load も置換対象 (xor/inttoptr に align 属性は不可;
            # ft7 で `xor i64 0, 0, align 8` が parse error になった実測の修正)
            body, cnt = re.subn(r"= load (\w+), ptr " + esc + r"(?=[ ,)\n])(?:, align \d+)?",
                                _zero_val, body)
            if cnt:
                nfix += cnt
        blocks[name] = body
    stage("B1", f"未初期化 alloca load → 値 0 (決定論化) {nfix} 件")
    return blocks, nfix


CE_ARITH = ("and", "or", "xor", "add", "sub", "mul", "shl", "lshr", "ashr",
            "udiv", "urem", "srem", "ptrtoint", "inttoptr", "zext", "sext",
            "trunc", "bitcast")


def count_constexpr(text):
    n = {}
    for op in CE_ARITH:
        n[op] = len(re.findall(rf"(?<![\w]){op} \(", text))
    n["icmp"] = len(re.findall(r"(?<![\w])icmp \w+ \(", text))
    n["getelementptr"] = len(re.findall(r"(?<![\w])getelementptr \(", text))
    return n


def closure_select(blocks, seeds):
    seen, ext = set(), {}
    for s in seeds:
        if s not in blocks:
            raise RuntimeError(f"[base] --select {s} が IR define 一覧にありません")
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


def collect_declare_lists(full_text, defined_names):
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


# ---------------------------------------------------------------
# M5 [A9L] 残存 constexpr の命令化 lift
# ---------------------------------------------------------------

def _paren_end(line, open_idx):
    depth = 0
    j = open_idx
    L = len(line)
    while j < L:
        c = line[j]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                break
        j += 1
    return j if depth == 0 else -1


def _innermost_ce(line):
    """行内の最内側の constexpr 候補 (op + '(...)' で前が識別子外) を返す。"""
    best = None
    for op in CE_ARITH:
        pos = 0
        while True:
            idx = line.find(f"{op} (", pos)
            if idx < 0:
                break
            if idx > 0 and (line[idx - 1].isalnum() or line[idx - 1] in "%@._$"):
                pos = idx + 1
                continue
            open_idx = idx + len(op) + 1
            end = _paren_end(line, open_idx)
            if end < 0:
                pos = idx + 1
                continue
            inner = line[open_idx + 1:end]
            cand = (op, idx, end + 1, inner)
            if best is None or len(inner) < len(best[3]):
                best = cand
            pos = idx + 1
    # icmp constexpr (`icmp ne (i32 X, i32 0)`) — LLVM 17 で廃止 (ft7 実測)
    pos = 0
    while True:
        m = re.compile(r"(?<![\w])icmp (\w+) \(").search(line, pos)
        if m is None:
            break
        idx = m.start()
        open_idx = m.end() - 1
        end = _paren_end(line, open_idx)
        if end < 0:
            pos = idx + 1
            continue
        inner = line[open_idx + 1:end]
        cand = ("icmp", idx, end + 1, line[idx:end + 1])
        if best is None or len(inner) < len(best[3]):
            best = cand
        pos = idx + 1
    return best


_WIDTHS = {"i32": 32, "i64": 64, "i16": 16, "i8": 8}


def _src_pref(op, val):
    """cast 命令に前置するソース型を推定 (inttoptr の即値では i64 を保証)。
    cast 元は RetDec 正規化後 'i64 0x1000100' 型のように明示型接頭辞付きか
    SSA 値のどちらか。接頭辞が無い場合は inttoptr に限り i64 を補う。"""
    tok = val.strip().split(" ")[0] if " " in val.strip() else None
    if tok and (tok.startswith("i") or tok.startswith("f") or tok == "ptr"):
        return val
    if op == "inttoptr":
        return f"i64 {val}"
    if op == "ptrtoint":
        # グローバル/レジスタ参照の ptrtoint は opaque ptr で受ける
        # (ft7 実測: `ptrtoint @g to i16` は expected type で parse error)
        return f"ptr {val}"
    return val


def _is_const_int(tok):
    return re.fullmatch(r"(-?\d+)", tok) is not None


_CAST_OP = ("ptrtoint", "inttoptr", "zext", "sext", "trunc", "bitcast")


def _mat_sym(tok, ty, idx, suffix):
    """arith/icmp operand を値化する。返値: (val, 新 idx, 挿入命令リスト)。"""
    ins = []
    # 型接頭辞付き即値 (`i64 8` 等) はその値のみ使う (ft7 実測:
    # add i64 0, i64 8 は type token を値として parse error になる)
    t = re.sub(r"^(?:i[0-9]+|f[0-9]+|ptr)\s+(?=[-+0-9])", "", tok)
    if _is_const_int(t):
        return t, idx, ins
    if t.startswith("%"):
        return t, idx, ins
    # シンボルを示すトークン: アドレス値は ptrtoint 経由で値化
    # (`add i64 0, @g` は ptr を i64 add に直接置けないため)
    if t.startswith("@"):
        nvx = f"%ce{idx}{suffix}"
        ins.append(f"  {nvx} = ptrtoint ptr {t} to {ty}")
        return nvx, idx + 1, ins
    nvx = f"%ce{idx}{suffix}"
    ins.append(f"  {nvx} = add {ty} 0, {t}")
    return nvx, idx + 1, ins


def _lift_one_line(line, cnt, suffix=""):
    """行内の最内 constexpr 1 個を命令化して差し替える。
    返値: (新行, 挿入命令リスト, 新 cnt) — cnt は次回のレジスタ採番 (SSA
    衝突防止のため成功時は作ったレジスタ数だけ進める。ft7 で同一 block 内の
    多重 cast lift が同名列定義衝突になった実測の修正)。変換できなければ
    (line, [], cnt)。
    (FTS mm closure IR 実測の残存組: ptrtoint/inttoptr/bitcast/add 等 ~187 件)"""
    hit = _innermost_ce(line)
    if hit is None:
        return line, [], cnt
    op, start, end, inner = hit

    nv = f"%ce{cnt}{suffix}"
    if op in _CAST_OP:
        m = re.fullmatch(r"(?:ptr|[iif]\d+)\s+([%@][\w.\-]+|[iifp]\d+[^\s]?\s?[^\s]+|[^\s]+)\s+to\s+([ip][\w\d]*)",
                         inner.strip())
        if m:
            val, toty = m.group(1), m.group(2)
            if op == "bitcast":
                # bitcast (ptr X to ptr) は no-op で除去。iN→ptr は inttoptr 命令化。
                if toty == "ptr":
                    v = re.sub(r"^(?:ptr|[iif]\d+)\s+", "", val)
                    return line[:start] + v + line[end:], [], cnt
            ins = [f"  {nv} = {op} {_src_pref(op, val)} to {toty}"]
            # 文脈の期待幅との整合 (ft7 実測: `store i32 ptrtoint (ptr @g to i64)`
            # の命令化後に幅不一致 parse error)。constexpr 時点で許容されていた
            # 暗黙の幅変換を trunc/zext/inttoptr で明示化する。
            expect = None
            mt = re.search(r"(?<![\w])(i[0-9]+|ptr)$", line[:start].rstrip())
            if mt:
                expect = mt.group(1)
            else:
                mh = re.match(r"\s*%[\w.\-]+ = \w+ (i[0-9]+) ", line[:start])
                if mh:
                    expect = mh.group(1)
            extra = 0
            if expect and expect != toty:
                if expect == "ptr" and toty != "ptr":
                    ins.append(f"  {nv}x = inttoptr {toty} {nv} to ptr")
                    nv_used = f"{nv}x"
                    extra += 1
                elif toty == "ptr" and expect != "ptr":
                    ins.append(f"  {nv}x = ptrtoint ptr {nv} to {expect}")
                    nv_used = f"{nv}x"
                    extra += 1
                else:
                    w_exp, w_tot = int(expect[1:]), int(toty[1:])
                    if w_exp < w_tot:
                        ins.append(f"  {nv}x = trunc {toty} {nv} to {expect}")
                        nv_used = f"{nv}x"
                        extra += 1
                    elif w_exp > w_tot:
                        ins.append(f"  {nv}x = zext {toty} {nv} to {expect}")
                        nv_used = f"{nv}x"
                        extra += 1
                if extra:
                    nv = nv_used
            return line[:start] + nv + line[end:], ins, cnt + 1 + extra
        return line, [], cnt

    # icmp constexpr (`icmp ne (i32 X, i32 0)` → 命令化; ft7 実測で
    # br の条件に残存し `icmp constexprs are no longer supported` エラー)
    if op == "icmp":
        m2 = re.fullmatch(r"icmp\s+(\w+)\s+\(([iif]\d+)\s+(.+?),\s*([iif]\d+)\s+(.+?)\)",
                          inner.strip())
        if m2:
            pred, ty, a, _t2, b = m2.groups()
            av, idx, ins = _mat_sym(a, ty, cnt, suffix)
            bv, idx, ins2 = _mat_sym(b, ty, idx, suffix)
            ins += ins2
            nvt = f"%ce{idx}{suffix}"
            ins.append(f"  {nvt} = icmp {pred} {ty} {av}, {bv}")
            return line[:start] + nvt + line[end:], ins, idx + 1
        return line, [], cnt

    # 算術 2 項 (シンボル参照を含む場合に命令化)
    mm = re.fullmatch(r"([iif]\d+) (.+?), (.+)", inner.strip())
    if mm and op in ("add", "sub", "or", "xor", "and", "mul", "shl", "lshr",
                     "ashr", "udiv", "urem", "srem"):
        ty, a, b = mm.group(1), mm.group(2), mm.group(3)
        # 内側が既に A8 で畳めない (= レジスタ/シンボル入りの入れ子 constexpr)
        # ため常に命令化する (ft7 で `add i64 %6, add (i64 %ce..., 8)` が
        # function-local name 参照の constexpr として parse error になった実測)
        av, idx, ins = _mat_sym(a, ty, cnt, suffix)
        bv, idx, ins2 = _mat_sym(b, ty, idx, suffix)
        ins += ins2
        nvt = f"%ce{idx}{suffix}"
        ins.append(f"  {nvt} = {op} {ty} {av}, {bv}")
        return line[:start] + nvt + line[end:], ins, idx + 1
    return line, [], cnt


def lift_residual_constexpr_ex(text):
    """[A9L2] A9L 後の残存を追加処理:
      - `bitcast (ptr X to ptr)` → X (no-op 除去; load/call 引数の留置)。
      - `ptrtoint ([N x ty]* @g to i64)` 相当 (型付き pointer 残骸) → `@g`。
      (指令の直接 removal は 0 回回すのみ: force fix)"""
    n = 0
    text, nbc = re.subn(r"bitcast \(ptr ([@%][\w$.]+) to ptr\)", r"\1", text)
    n += nbc
    text, npt = re.subn(r"ptrtoint \([\d]+ x [\w]+\* (@[\w$.]+) to i64\)", r"\1", text)
    n += npt
    text = re.sub(r"ptrtoint ([@%\w$.]+) to i64\b(?![\w])", r"ptrtoint ptr \1 to i64", text)
    text = re.sub(r"inttoptr ([@%][\w$.]+) to ptr\b", r"inttoptr i64 \1 to ptr", text)
    stage("A9L2", f"bitcast 除去 {nbc}, ptrtoint 配列化 {npt}")
    return text, n


_CE_NONCE = [0]


def lift_residual_constexpr(blocks):
    """[A9L] blocks 内の残存 constexpr を命令化して置き換える (固定点まで反復)。"""
    nlines = 0
    _CE_NONCE[0] += 1
    nonce = f"n{_CE_NONCE[0]}"
    changed = True
    it = 0
    while changed:
        changed = False
        it += 1
        newblocks = {}
        for name, body in blocks.items():
            lines = body.split("\n")
            out = []
            cnt = 0
            # ブロック内で名前衝突するので block 名を suffix 化 (map 参照なしに安全):
            # 反復ごとにも suffix を変える (前回反復で挿入済みの %ce* との衝突防止)
            for ln in lines:
                newln, ins, cnt = _lift_one_line(ln, cnt, f"{nonce}{it}_{name}")
                if ins:
                    out.extend(ins)
                    out.append(newln.rstrip() if newln.strip() != newln else newln)
                    nlines += 1
                    changed = True
                else:
                    out.append(ln)
            newblocks[name] = "\n".join(out)
        blocks = newblocks
    blocks.pop("__ce_count__", None)
    res_all = count_constexpr("\n".join(blocks.values()))
    total_ops = {k: v for k, v in res_all.items() if v}
    stage("A9L", f"constexpr 命令化 {nlines} 行, 残存 {sum(total_ops.values())} 件 " +
          " ".join(f"{k}:{v}" for k, v in sorted(total_ops.items())))
    return blocks, total_ops


# ---------------------------------------------------------------
# M5 [S1] SSE __asm_* 疑似宣言の lower (store 復元 / lane 出入力)
# ---------------------------------------------------------------

ASM_STORAGE = re.compile(
    r"!\?\s*call void @__asm_(movups|movaps|movdqa)\.2\(i128 %(\w[\w.\-]*), i128 %(\w[\w.\-]*)\)")


def _find_store_srcs(block):
    """%N = load i128, i128* %P の対応表 {reg: ptr_reg} を作る。"""
    m = {}
    for ln in block.split("\n"):
        mm = re.match(r"  (%[\w.\-]+) = load i128, ptr (%[\w.\-]+)", ln)
        if mm:
            m[mm.group(1)] = mm.group(2)
    return m


ASM_STORE_CALL = r"^  call void @__asm_(?:movups|movaps|movdqa)(?:__\d+|\.\d+)?\.?(?:__)?\d*\(i128 (%[\w.\-]+), i128 (%[\w.\-]+)\)(?: .*)?$"


def lower_asm_store(blocks):
    """[S1a] `call void @__asm_movups*(load値, 値)` を store へ復元。名前は
    RetDec の overload 接尾 (`.2` / R1 名寄せ後 `__2`) の両方を許容。"""
    n = 0
    pat = re.compile(r"^  call void @__asm_(?:movups|movaps|movdqa)(?:__\d+|\.\d+)?\(i128 (%[\w.\-]+), i128 (%[\w.\-]+)\)(?:,? ?.*)?$")
    for name, body in list(blocks.items()):
        lines = body.split("\n")
        srcs = _find_store_srcs(body)
        out = []
        for ln in lines:
            mm = pat.match(ln)
            if not mm:
                out.append(ln); continue
            addr_reg = mm.group(1).strip()
            val_reg = mm.group(2).strip()
            addr_reg = addr_reg if addr_reg.startswith("%") else None
            # 第一引数は「load された値」(ポインタではない) — load 元アドレスを辿る
            ptr = srcs.get(addr_reg)
            if ptr is None:
                # live-in に現れない場合も load 直後の行で辿る
                hh = re.match(r"i128 (%[%\w.\-]+)", mm.group(1))
                pos_idx = lines.index(ln)
                for hh_ln in reversed(out):
                    hx = re.match(r"  (%[\w.\-]+) = load i128, ptr (%[\w.\-]+)", hh_ln)
                    if hx and hx.group(1) == addr_reg:
                        ptr = hx.group(2)
                        break
            if ptr is None:
                out.append(ln)
                continue
            out.append(f"  store i128 {val_reg}, ptr {ptr}")
            n += 1
        # usename note: `out` の置換は行方向のみ
        blocks[name] = "\n".join(out)
    stage("S1a", f"__asm_* .2 store 復元 {n} 件")
    return blocks, n


def lower_asm_lane_store(blocks):
    """[S1c] `call void @__asm_movlps|movlpd|movhps|movhpd(i64 旧値, i128 値)` を store i64 へ復元 (SR-4 / #75)。
    RetDec は `movlps m64, xmm` を「m64 の旧値を読む read operand + xmm」の void call にし, 書込みを落とす
    (S1a の movups と同型だが i64 幅)。旧値が直前の `load i64, ptr P` なら P へ xmm の低 (movl*) / 高 (movh*) 64bit を store する。
    旧値が load 由来でない形は触らない (残れば simd 生成側が unsupported として報告)。"""
    n = 0
    pat = re.compile(r"^  call void @__asm_(movlps|movlpd|movhps|movhpd)(?:__\d+|\.\d+)?\(i64 (%[\w.\-]+), i128 (%[\w.\-]+)\)(?:,? ?.*)?$")
    for name, body in list(blocks.items()):
        if "@__asm_mov" not in body:
            continue
        loads = {}
        for ln in body.split("\n"):
            mm = re.match(r"  (%[\w.\-]+) = load i64, ptr (%[\w.\-]+)", ln)
            if mm:
                loads[mm.group(1)] = mm.group(2)
        out = []
        for ln in body.split("\n"):
            mm = pat.match(ln)
            ptr = loads.get(mm.group(2)) if mm else None
            if not mm or ptr is None:
                out.append(ln); continue
            mn, val = mm.group(1), mm.group(3)
            tag = "%%s1c_%d" % n
            src = val
            if mn.startswith("movh"):
                out.append(f"  {tag}_sh = lshr i128 {val}, 64")
                src = f"{tag}_sh"
            out.append(f"  {tag}_lo = trunc i128 {src} to i64")
            out.append(f"  store i64 {tag}_lo, ptr {ptr}")
            n += 1
        blocks[name] = "\n".join(out)
    if n:
        stage("S1c", f"__asm_movl/h(ps|pd) store 復元 {n} 件")
    return blocks, n


def prune_asm_lane_helpers(blocks):
    """[S1b] 純 lane 入出力形式の __asm_* を命令へ置換。
    - movss.3(i32) → zext i32 to i128 (0 埋め broadcast 無し; load と同じ意味で使用)
    - movss.4 / movd.2 (i128→i64/i32) → 多重化されている tranc 系:
        RetDec の出力は ret i64 で返ってくる。Lane0 抽出相当 — helper 委譲のままが安全なら
        変換せず declare を残す。
    本実装では [S1b] は movss.3 の zext 化のみ (実測 4 件) で, 他は helper に委譲。"""
    n = 0
    for name, body in list(blocks.items()):
        lines = body.split("\n")
        out = []
        for ln in lines:
            mm = re.match(r"^  (%[\w.\-]+) = call i128 @__asm_movss\.3\(i32 ([\w.\-]+)\)(.*)$", ln)
            if mm:
                nv, src, tail = mm.groups()
                out.append(f"  {nv} = zext i32 {src} to i128{tail}")
                n += 1
            else:
                out.append(ln)
        blocks[name] = "\n".join(out)
    stage("S1b", f"movss.3 zext 化 {n} 件")
    return blocks, n


# ---------------------------------------------------------------
# M5 [C8] xmm entry-spill 引数の VA 経由取り込み
# ---------------------------------------------------------------

def xmm_arg_inject(blocks, xmm_map):
    """[C8] xmm_map: { function_name: VA(str) } — その関数の entry の
    `= load i128, ptr %N` (N=entry alloca i128) を `= load i128, ptr inttoptr…`
    に捨てる: 指定 VA は linear memory に呼び出し側が事前書き込みする。"""
    n = 0
    for fname, va in xmm_map.items():
        body = blocks.get(fname)
        if body is None:
            continue
        # 先頭の `= load i128, i128* %X` (X=alloca i128) を差し替える
        m = re.search(r"(?m)^  (%[\w.\-]+) = load i128, ptr %([\w.\-]+)( .*)?$", body)
        if not m:
            continue
        # alloca i128 であることを確認
        if not re.search(rf"(?m)^  %{re.escape(m.group(2))} = alloca i128(?: .*)?$",
                         body[:m.start()]):
            continue
        va_dec = int(va, 0)
        rep = f"  {m.group(1)} = load i128, ptr inttoptr (i64 {va_dec} to ptr)"
        body = body[:m.start()] + rep + body[m.end():]
        blocks[fname] = body
        n += 1
        stage("C8", f"{fname}: xmm entry 値を VA {va} から取り込み")
    return blocks, n


# ---------------------------------------------------------------
# M5 [C9] 外部 helper call redirect
# ---------------------------------------------------------------

def redirect_calls(blocks, redirect):
    """[C9] redirect: { 'function_XXXX': 'mm_alloc' } — call 行を代替関数へ。
    返値のポインタ幅整合のため declare も追加する (declare i64 @target)。"""
    added_decl = []
    n = 0
    for fname, body in list(blocks.items()):
        lines = body.split("\n")
        out = []
        for ln in lines:
            hit = None
            for src, dst in redirect.items():
                if re.search(rf"call \S+ @{re.escape(src)}\(", ln):
                    hit = (src, dst)
                    break
            if hit:
                src, dst = hit
                ln = re.sub(rf"@{re.escape(src)}\(", f"@{dst}(", ln)
                if f"@{dst}(" not in "\n".join(added_decl) and not dst.startswith("function_"):
                    added_decl.append(f"declare i64 @{dst}(i64) local_unnamed_addr")
                n += 1
            out.append(ln)
        blocks[fname] = "\n".join(out)
    stage("C9", f"外部 helper call redirect {n} 箇所: {redirect}")
    return blocks, added_decl


# ---------------------------------------------------------------



def head_of(full):
    pre = re.match(r'(?ms)(.*?)(?=\ndefine )', full)
    return pre.group(1) if pre else ""


def write_stub_c(stubNames, path):
    with open(path, "w") as fh:
        fh.write("/* ir5_patch [--stub-auto] 生成: 未解決 function_* の 0 返しスタブ\n */\n")
        fh.write('#include <stdint.h>\n')
        for nm in sorted(set(stubNames)):
            fh.write(f"int64_t {nm}(int64_t a) {{ (void)a; return 0; }}\n")


def main():
    global VERBOSE
    ap = argparse.ArgumentParser()
    ap.add_argument("infile")
    ap.add_argument("outfile")
    ap.add_argument("--select", default="")
    ap.add_argument("--keep-all", action="store_true")
    ap.add_argument("--redirect", default="")
    ap.add_argument("--xmm-arg-map", default="")
    ap.add_argument("--c11-fix", default="")
    ap.add_argument("--stub-out", default="")
    ap.add_argument("--sig-fix", default="")
    ap.add_argument("--report", default="")
    args = ap.parse_args()
    VERBOSE = True
    full = open(args.infile).read()
    text, rep = run_base(full, args)
    with open(args.outfile, "w") as fh:
        fh.write(text)
    print(f"[base] wrote {args.outfile}")
    if args.report:
        with open(args.report, "w") as fh:
            json.dump(rep, fh, indent=1, ensure_ascii=False)


def lift_fixups(text):
    """RetDec/A9L 由来の無害な機械的欠陥の修復 (m7 m6_e2e.sh の lift_fixup と同等):
       - `add i64 0, i64 %X` (型トークン混入; parse error) → `add i64 %X, 0`
       - 同 signature の重複 declare の除去。"""
    n_fix = [0]

    def repl(m):
        n_fix[0] += 1
        return f"{m.group(1)} = add i64 {m.group(2)}, 0"
    text = re.sub(r"(?m)^([ ]*%[\w.\-]+) = add i64 0, i64 (%[\w.\-]+)(?=$|,)", repl, text)
    seen, keep, d = set(), [], 0
    for ln in text.split("\n"):
        m = re.match(r"^declare (\S+) @([\w.\-]+)\((.*?)\)( local_unnamed_addr)?$", ln)
        if m:
            key = (m.group(2), m.group(3))
            if key in seen:
                d += 1
                continue
            seen.add(key)
        keep.append(ln)
    return "\n".join(keep), n_fix[0], d


_ALLOCA_LINE = re.compile(r"^(\s*)%(\d+) = alloca (\S+)(.*)$")
_LOCAL_REF = re.compile(r"%(\d+)(?![\w.])")


def canon_alloca_order(text):
    """関数ごとの連続した alloca 行を型名順に並べ直し、%N 参照を付け替える (LIFTLIB-11 / #887)。

    RetDec は同一入力でも alloca 行の並びを ASLR 等に依存して入れ替えることがある (k80 で実測)。
    型キーは型全体 (align を除く) の文字列順で並べ替え、同型は番号の昇順、スロット名 (%N) は番号の昇順に振り直す。
    入力の行順・同先頭トークンの型 (struct 同士) に依存しない。意味は変わらない (スロットの番号付けのみ)。
    """
    lines = text.split("\n")
    n = len(lines)
    i = 0
    while i < n:
        if lines[i].startswith("define "):
            j = i + 1
            while j < n and not lines[j].startswith("}"):
                j += 1
            _canon_alloca_body(lines, i, j)
            i = j + 1
        else:
            i += 1
    return "\n".join(lines)


def _canon_alloca_body(lines, s, e):
    rename = {}
    fixed = set()
    k = s + 1
    while k < e:
        if not _ALLOCA_LINE.match(lines[k]):
            k += 1
            continue
        run = []
        while k < e and _ALLOCA_LINE.match(lines[k]):
            run.append(k)
            k += 1
        if len(run) < 2:
            continue
        ms = [_ALLOCA_LINE.match(lines[x]) for x in run]
        names = [m.group(2) for m in ms]
        bodies = [m.group(3) + m.group(4) for m in ms]
        keys = [(re.sub(r",\s*align\s+\d+", "", b), int(names[q])) for q, b in enumerate(bodies)]
        slots = sorted(names, key=int)
        order = sorted(range(len(run)), key=lambda q: keys[q])
        for p, q in enumerate(order):
            if names[q] != slots[p]:
                rename[names[q]] = slots[p]
            lines[run[p]] = f"{ms[q].group(1)}%{slots[p]} = alloca {bodies[q]}"
            fixed.add(run[p])
    if rename:
        for x in range(s + 1, e):
            if x not in fixed:
                lines[x] = _LOCAL_REF.sub(lambda mo: "%" + rename.get(mo.group(1), mo.group(1)), lines[x])


def make_args(**kw):
    import types
    d = dict(infile="", outfile="", select="", keep_all=False, redirect="", xmm_arg_map="", c11_fix="",
             stub_out="", sig_fix="", report="")
    d.update(kw)
    return types.SimpleNamespace(**d)


def run_base(full, args):
    """m2 ir_normalize + m5 ir5_patch の連結 (ライブラリ版)。返値: (text, report)。"""
    _CE_NONCE[0] = 0
    del STAGE_LOG[:]
    full = m2_normalize(full)
    full = normalize(full)

    full = rename_asm_dot_symbols(full)

    redirect = {}
    if args.redirect:
        redirect = json.load(open(args.redirect))
    xmm_map = {}
    if args.xmm_arg_map:
        xmm_map = json.load(open(args.xmm_arg_map))

    blocks = parse_functions(full)
    # define block スライスに混入した後続 declare 行 (末尾関数が EOF まで切れる) を剥がす
    for _k in list(blocks):
        if re.search(r"(?m)^declare ", blocks[_k]):
            blocks[_k] = re.sub(r"(?m)^declare .*\n", "", blocks[_k]).rstrip() + "\n"

    # [C9] 先に redirect (残り pass は redirect 後の形で動く; declare 由来の call も)
    blocks, added_decl = redirect_calls(blocks, redirect)
    redirect = {k: v for k, v in redirect.items()}

    # [C11] レジスタ戻り値の最小修復 (main 終了時の再結成は C1 出力前なので, ここで patterns 適用)
    c11_slot = None
    if args.c11_fix:
        c11_slot = json.load(open(args.c11_fix))
        for fnm, cfg in c11_slot.items():
            if fnm not in blocks:
                continue
            body = blocks[fnm]
            lab = "dec_label_pc_" + str(cfg["block"])
            mlab = re.search(rf"(?m)^{re.escape(lab)}:", body)
            if not mlab:
                continue
            i0 = mlab.start()
            mnext = re.search(rf"(?m)^dec_label_pc_\w+:", body[i0 + 1:])
            i1 = i0 + 1 + mnext.start() if mnext else len(body)
            seg = body[i0:i1]
            old, new = cfg["old"], cfg["new"]
            done = False
            if old in seg:
                seg = seg.replace(old, new, 1)
                done = True
                stage("C11", f"{fnm}: {old} → {new} (戻り値修正)")
            # [C11 補助] "ins" フィールド: セグメント末尾に追加命令を足せる
            #   例: base_path:%args による copy dst ($storemerge21) レジスタ初期化
            if done and cfg.get("ins_append"):
                seg = seg.rstrip() + "\n" + "\n".join(cfg["ins_append"]) + "\n"
                stage("C11a", f"{fnm}: 追加指令 {[c[:60] for c in cfg['ins_append']]}")
            blocks[fnm] = body[:i0] + seg + body[i1:]

    # [S1] SSE lower (store 復元 / lane 入出力)
    blocks, n_stores = lower_asm_store(blocks)
    blocks, n_lane_store = lower_asm_lane_store(blocks)
    blocks, n_lane = prune_asm_lane_helpers(blocks)

    # [C8] xmm 引数取り込み
    blocks, n_c8 = xmm_arg_inject(blocks, xmm_map)

    # [A9L] 残存 constexpr の命令化 lift
    blocks, a9_res = lift_residual_constexpr(blocks)

    # [B1]
    blocks, nfix = patch_uninit_alloca(blocks)

    # A9 二巡 (B1 で作った行にも constexpr が来ないと良いが, 念のため)
    blocks, a9_res2 = lift_residual_constexpr(blocks)
    # [A9L2] 全結合テキストに対して後段の残留 bitcast/ptrtoint 処理
    for _k in blocks:
        b2, n_a = lift_residual_constexpr_ex(blocks[_k])
        blocks[_k] = b2
    stage("A9L2", "全 block へ bitcast/ptrtoint 残処理適用")

    if args.select and not args.keep_all:
        sel = args.select
        if sel.startswith("exact:"):
            keep_fns = [s for s in sel[6:].split(";") if s]
            missing = [s for s in keep_fns if s not in blocks]
            if missing:
                stage("C1", f"FAIL: exact 選択に存在しない関数 {missing}")
                raise RuntimeError('exact 選択に存在しない関数')
        else:
            seen2, _ext = closure_select(blocks, [s for s in sel.split(",") if s])
            keep_fns = sorted(seen2)
        keep_fns_set = set(keep_fns)
        body_all = "\n".join(blocks[f] for f in keep_fns)
        exts = set()
        for m in re.finditer(r"@([\w$.]+)", body_all):
            c = m.group(1)
            if c not in keep_fns_set and not c.startswith("llvm."):
                exts.add(c)
        globs_needed = exts | set(m.group(1) for m in re.finditer(r"(@[\w$.]+)", body_all))
        gtxt = []
        for m in re.finditer(r"(?ms)^(@[\w$.]+) = .*?(?=\n\n|^declare |\n\ndefine )", full):
            if m.group(1) in globs_needed:
                gtxt.append(m.group(0).rstrip())
        declare_bodies, bad = collect_declare_lists(full, set(blocks))
        fn_exts = {c for c in exts if not c.startswith("__asm_")}
        asm_needed = {m.group(1) for m in re.finditer(r"call \S+ @(__asm_[\w$.]+)\(", body_all)}
        # 選択した関数外で require される declare:
        #  - 既存 declare 行 (ir)          : its 名が fn_exts / asm_needed
        #  - 選択肢の define 行からの合成  : keep 外に define がある名 (declare 行が存在しない)
        declared_keep, seenx = [], set()
        for d in declare_bodies:
            nm = re.match(r"declare \S+.*?@([\w$.]+)\(", d).group(1)
            if nm in fn_exts or nm in asm_needed:
                if nm not in seenx:
                    declared_keep.append(d)
                    seenx.add(nm)
        for nm in sorted(fn_exts):
            if nm in seenx:
                continue
            if nm in blocks:
                # define 行から declare を合成 (パラメータ名を落とす)
                first = blocks[nm].split("\n")[0]
                dm = re.match(r"^define (\S+) @([\w$.]+)\((.*)\)(.*)$", first)
                if not dm:
                    continue
                ret = dm.group(1)
                sig = dm.group(3)
                # のパラメータ名を落とす ("ptr %arg1" → "ptr")
                parts = []
                for p in [q.strip() for q in sig.split(",") if q.strip()]:
                    pty = re.match(r"^(ptr|i\d+|float|double)(?:\s+\S+)?$", p)
                    parts.append(pty.group(1) if pty else p)
                declared_keep.append(
                    f"declare {ret} @{nm}({', '.join(parts)}) local_unnamed_addr")
                seenx.add(nm)
        head = head_of(full)
        text = head.rstrip() + "\n\n" + "\n\n".join(gtxt) + \
            "\n\n" + "\n\n".join(blocks[f].rstrip() for f in keep_fns) + \
            "\n\n" + "\n".join(declared_keep) + "\n"
        if added_decl:
            text = text.rstrip() + "\n" + "\n".join(added_decl) + "\n"
        stage("C1", f"{len(keep_fns)} 関数(available={len(blocks)}) / 外部参照 {len(exts)} 件")

        # [C12] 未解決 function_* declare (ワーク置換モジュール外) の stub 化
        stubs = []
        for _dm in re.finditer(r"(?m)^declare \S+ @{[\w$.]+", text):
            pass
        for _dm in re.finditer(r"(?m)^declare \S+ @([\w$.]+)\(", text):
            nm = _dm.group(1)
            if nm.startswith("function_") and nm not in blocks:
                stubs.append(nm)
        if stubs:
            stage("C12", f"未解決 function_* declare を stub 化: {sorted(set(stubs))}")
            write_stub_c(set(stubs), args.stub_out or "m5stubs.c")
        txt_new = re.sub(r"(?m)^(declare \S+ @mm_failfast_c80)\(i64\)", r"\1(i64, i64, i64)", text)
        if txt_new != text:
            text = txt_new
            stage("C1c", "declare mm_failfast_c80: (i64) → (i64,i64,i64) に統一")
        # [C12] 未解決外部 declare (work_mmfun 由来) を 0 返しスタブ declare に向け換え
        # (emcc の -sERROR_ON_UNDEFINED_SYMBOLS=0 + wasm-ld stub で trap しないための機械処理)
        out_extra = []
        for _m in [None]:
            pass
        stubs = []
        for _dm in re.finditer(r"(?m)^declare (\S+) @([\w$.]+)\(",
                               "\n".join(text.split("\n")[-150:])):
            nm = _dm.group(2)
            if nm.startswith("function_"):
                stubs.append(nm)
        # 実装側から与えられる mm_* は対象外; function_* の 0 返しスタブを追加
        for nm in sorted(set(stubs)):
            # 引数自体は call 側アリティに合せる (最大 4 で閉める: IR 内で超えると宣言の線上)
            arity = 0
            for cm in re.finditer(rf"call \S+ @{re.escape(nm)}\)", text):
                arity = 0
            # stub は i64 1 個として宣言し, 実装 0 返し
            out_extra.append(f"declare i64 @{nm}(i64) local_unnamed_addr")
        for nm in sorted(set(stubs)):
            pass
        if out_extra:
            stage("C12", f"未解決 function_* declare を stub 化: {sorted(set(stubs))}")
            write_stub_c(set(stubs), args.stub_out or "work/m5stubs.c")

        # C 側 (harness) prototype との整合: 無引数形で保持する場合 bespoke に統一。
        # function_412d60 等, extern 宣言 (mm_harness.c) に合わせ IR define の first line を
        # ptr→i64 の機械統一をする (wasm-ld signature-mismatch 警告の除去)。
        # [C1b] define シグネチャ統一 (config: {"function_X": "(i64 %arg1, i64 %arg2)"})
        if args.sig_fix:
            sigmap = json.load(open(args.sig_fix))
            for _fix, _to in sigmap.items():
                txt_new = re.sub(
                    r"(?m)^(define \S+ @" + re.escape(_fix) + r")\([^)]*\)",
                    r"\1" + _to, text)
                if txt_new != text:
                    text = txt_new
                    stage("C1b", f"{_fix}: define シグネチャを {_to} に統一")
    else:
        pre = re.match(r'(?ms)(.*?)(?=\ndefine )', full)
        head = pre.group(1) if pre else ""
        declares, bad = collect_declare_lists(full, set(blocks))
        # 重複 declare 行の除去 (同一 (name, ret, sig) の 2 度目以降を捨てる)
        seen_d = set()
        uniq = []
        for d in declares:
            mm = re.match(r"declare (\S+)(.*?)(@[\w$.]+)(\(.*?\))( .*?)?$", d)
            key = (mm.group(3), mm.group(1), mm.group(4)) if mm else None
            if key in seen_d:
                continue
            seen_d.add(key)
            uniq.append(d)
        declares = uniq
        added_d = []
        for d in added_decl:
            keyk = d.lstrip("declare ")
            if keyk not in seen_d:
                seen_d.add(keyk)
                added_d.append(d)
        adds = added_d
        text = (head.rstrip() + "\n\n" + "\n\n".join(
            b.rstrip() for b in blocks.values()) + "\n\n" +
            "\n".join(uniq) + "\n" + "\n".join(adds) + "\n")
        stage("C1", "keep-all (全 define 維持)")

    # [R2] added_decl (redirect 実装) の declare 引数を呼出側の arity に合わせる
    for _m in re.finditer(r"(?m)^declare \S+ @(mm_[\w]+)\(([^)]*)\)", text):
        nm, cur_sig = _m.group(1), _m.group(2)
        arities = set()
        for cm in re.finditer(rf"call \S+ @{nm}\(([^)]*)\)", text):
            arities.add(len([a for a in cm.group(1).split(",") if a.strip()]))
        if arities:
            k = max(arities)
            if k not in (0, 1):
                sig = ", ".join(["i64"] * k)
                nn = re.sub(rf"(?m)^(declare \S+ @{re.escape(nm)})\([^)]*\)",
                            rf"\1({sig})", text)
                if nn != text:
                    text = nn
                    stage("R2", f"declare @{nm} → {k} 引数形に統一")

    # [C13] external global のリンク解決 (0 初期化定義に置換)。
    # ft7 closure 実測: DLL データ (FastMM 管理表/VMT bookkeeping 等) の実体は
    # IR に無く wasm-ld が undefined symbol (global_var_15e6ba8 等) になるため、
    # アドレスが取れる 0 初期化定義を置く (DLL 実データの取込は M6 の
    # データセクション pass に委ねる)。i8/i16/i32 は連続管理表の base になり
    # 得る (@1 実測: ptrtoint @1 + 261888 内 offset) ので 256KB を後見する。
    _ext_n = [0]

    def _ext_zero(m):
        _ext_n[0] += 1
        name, ty = m.group(1), m.group(2)
        if ty in ("i8", "i16", "i32"):
            return f"{name} = global [65536 x {ty}] zeroinitializer"
        if ty == "ptr":
            return f"{name} = global ptr null"
        return f"{name} = global {ty} 0"

    text, n_ext = re.subn(
        r"(?m)^(@[\w$.]+) = external (?:local_unnamed_addr )?global (i[0-9]+|ptr)$",
        _ext_zero, text)
    stage("C13", f"external global → 0 初期化定義 (リンク解決; DLL データ実体取込は M6) {n_ext} 件")

    text, n_fix, n_dup = lift_fixups(text)
    stage("FIX", f"add i64 0, i64 %X 修復 {n_fix} 行 / 重複 declare 除去 {n_dup} 行")
    a9_res_fin = count_constexpr(text)
    sum_fin = sum(a9_res_fin.values())
    rep = {"fixups_add0": n_fix, "dup_declares_removed": n_dup, "b1_fixed": nfix, "s1_stores": n_stores, "s1_lane_store": n_lane_store, "s1_lane": n_lane,
           "c8_xmm": n_c8, "c9_redirect": redirect,
           "a9_residual_constexpr": sum_fin,
           "a9_residual_by_op": {k: v for k, v in a9_res_fin.items() if v},
           "stages": ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "B1", "A9L", "S1", "C8", "C9", "C1"]}
    return text, rep


def do_select(blocks, full, seeds):
    keep_globals, keep_fns, declares, exts, bad = _do_select_impl(blocks, full, seeds)
    return keep_globals, sorted(keep_fns), declares, sorted(exts), bad


def _do_select_impl(blocks, full, seeds):
    # m3 ir_patch.py の do_select と同形 (外部 declare 残存に asm helper も含める)
    seen, ext = set(), {}
    for s in seeds:
        if s not in blocks:
            raise RuntimeError(f"[base] seed {s} が define 一覧にありません")
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
    join_all = "\n".join(blocks[f] for f in seen)
    globals_needed = set(m.group(1) for m in re.finditer(r"(@[\w$.]+)", join_all))
    keep_globals, keep_globals_name = [], []
    for m in re.finditer(r"(?ms)^(@[\w$.]+) = .*?(?=\n\n|^declare )", full):
        if m.group(1) in globals_needed:
            keep_globals.append(m.group(0))
            keep_globals_name.append(m.group(1))
    want = (set(ext) | (globals_needed - set(keep_globals_name))) - set(seen)
    declare_bodies, bad = collect_declare_lists(full, set(seen))
    declares = []
    for d in declare_bodies:
        nm = re.match(r"declare \S+.*?@([\w$.]+)\(", d).group(1)
        if nm in want or (d.find("\\") < 0 and nm.startswith("__asm_")):
            # __asm_* helper (msimd.c 側で供給) は declare を必ず残す
            declares.append(d)
    return keep_globals, sorted(seen), declares, sorted(ext), bad


if __name__ == "__main__":
    main()
