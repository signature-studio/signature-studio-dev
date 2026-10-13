"""fp_bind.py — [L2〜L6] --select-decode-only lift で「callee が caller stack / xmm を書く」契約が
raw IR から落ちる箇所を、外部 global への束縛に置き換える pass の共通プリミティブ。

RetDec は callee の caller-stack 書込み (tag 文字列 len, DOM root) や FP 戻り値 (xmm0) を
未定義 alloca 読み・`xor i128 0, 0` に fold する。ここでは
  - fn 単位で行パターンを探し (件数 expect 件でなければ失敗),
  - stack スロットの i64 load を global load に差し替え (bind_slot_loads),
  - 任意の行を差し替え / 直後に行を挿入する (replace_lines)
を提供する。どの関数・どのスロットを束縛するかは呼び出し側 (lift 対象ごとの表) が決める。
"""
import re


def fn_span(lines, fnva):
    want = 'function_%x(' % fnva
    s = next(i for i, l in enumerate(lines) if l.startswith('define') and want in l)
    e = next(i for i in range(s, len(lines)) if lines[i].startswith('}'))
    return s, e


def _fn_hits(lines, fnva, pat):
    s, e = fn_span(lines, fnva)
    out = []
    for i in range(s + 1, e):
        m = re.match(pat, lines[i])
        if m:
            out.append((i, m))
    return out


def replace_lines(lines, fnva, pat, repl, expect, tag):
    """fn 内で pat に一致する行 (expect 件) を repl(match, line) が返す行列で置換する。"""
    hits = _fn_hits(lines, fnva, pat)
    if len(hits) != expect:
        raise SystemExit(f'{tag}: candidate = {len(hits)} (expect {expect})')
    for i, m in reversed(hits):
        lines[i:i + 1] = repl(m, lines[i])
    return len(hits)


def insert_after(lines, i, new):
    """lines[i] の直後に new の行列を挿入する。"""
    lines[i + 1:i + 1] = new


def bind_slot_loads(lines, fnva, slot, glob, expect, tag):
    """fn 内の `load i64, ptr %stack_var_<slot>` (行頭が代入) を `load i64, ptr @<glob>` に差し替える。"""
    load = r'load i64, ptr %stack_var_' + re.escape(slot) + r'\b'
    hits = _fn_hits(lines, fnva, r'\s*%\S+ = ' + load)
    if len(hits) != expect:
        raise SystemExit(f'{tag}: sites = {len(hits)} (expect {expect})')
    for i, _ in hits:
        lines[i] = re.sub(load, 'load i64, ptr @' + glob, lines[i]) + ' ; LIFTFIX ' + tag
    return len(hits)
