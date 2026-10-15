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
from typing import Callable, Match


def fn_span(lines: list[str], fnva: int) -> tuple[int, int]:
    want = 'function_%x(' % fnva
    s = next(i for i, l in enumerate(lines) if l.startswith('define') and want in l)
    e = next(i for i in range(s, len(lines)) if lines[i].startswith('}'))
    return s, e


def _fn_hits(lines: list[str], fnva: int, pat: str) -> list[tuple[int, Match[str]]]:
    s, e = fn_span(lines, fnva)
    out: list[tuple[int, Match[str]]] = []
    for i in range(s + 1, e):
        m = re.match(pat, lines[i])
        if m:
            out.append((i, m))
    return out


def replace_lines(lines: list[str], fnva: int, pat: str, repl: Callable[[Match[str], str], list[str]],
                  expect: int, tag: str) -> int:
    """fn 内で pat に一致する行 (expect 件) を repl(match, line) が返す行列で置換する。"""
    hits = _fn_hits(lines, fnva, pat)
    if len(hits) != expect:
        raise SystemExit(f'{tag}: candidate = {len(hits)} (expect {expect})')
    for i, m in reversed(hits):
        lines[i:i + 1] = repl(m, lines[i])
    return len(hits)


def insert_after(lines: list[str], i: int, new: list[str]) -> None:
    """lines[i] の直後に new の行列を挿入する。"""
    lines[i + 1:i + 1] = new


def meta_va_map(lines: list[str]) -> dict[str, int]:
    """`!N = !{i64 VA}` → {N: VA} (insn.addr メタの機械語 VA 解決用)。"""
    out: dict[str, int] = {}
    for l in lines:
        m = re.match(r'^!(\d+)\s*=\s*!\{i64 (\d+)\}', l.strip())
        if m:
            out[m.group(1)] = int(m.group(2))
    return out


def site_at(lines: list[str], fnva: int, va: int, pat: str) -> int:
    """fn 内で insn.addr の機械語 VA == va かつ pat に一致する行の index。1 件でなければ失敗。
    機械語 VA を鍵にするので、IR 行番号・alloca 名の変化に依らず同じ site を指す。"""
    s, e = fn_span(lines, fnva)
    mv = meta_va_map(lines)
    hits: list[int] = []
    for i in range(s + 1, e):
        mm = re.search(r'!insn\.addr !(\d+)', lines[i])
        if mm and mv.get(mm.group(1)) == va and re.match(pat, lines[i]):
            hits.append(i)
    if len(hits) != 1:
        raise SystemExit(f'site {va:#x} in {fnva:#x}: candidate = {len(hits)} (expect 1)')
    return hits[0]


def replace_at(lines: list[str], fnva: int, va: int, pat: str, new: list[str]) -> int:
    """機械語 VA va の行 (pat 一致) を new の行列で置換する。"""
    i = site_at(lines, fnva, va, pat)
    lines[i:i + 1] = new
    return i


def bind_load_at(lines: list[str], fnva: int, va: int, slot: str, glob: str, tag: str) -> None:
    """機械語 VA va の `load i64, ptr %stack_var_<slot>` を `load i64, ptr @<glob>` に差し替える (1 site)。"""
    load = r'load i64, ptr %stack_var_' + re.escape(slot) + r'\b'
    i = site_at(lines, fnva, va, r'\s*%\S+ = ' + load)
    lines[i] = re.sub(load, 'load i64, ptr @' + glob, lines[i]) + ' ; LIFTFIX ' + tag


def bind_load_slot_at(lines: list[str], fnva: int, va: int, expect_slot: str, glob: str, tag: str) -> str:
    """機械語 VA va の `load i64, ptr %stack_var_<slot>` を `load i64, ptr @<glob>` に差し替える。
    slot は IR 行から読み、expect_slot と一致しなければ失敗する (照合)。1 site でなければ失敗。"""
    pat = r'\s*%\S+ = load i64, ptr %stack_var_(-?\d+)\b'
    i = site_at(lines, fnva, va, pat)
    m = re.match(pat, lines[i])
    assert m is not None, 'bind_load_slot_at: pat が site 行に一致しない'
    slot = m.group(1)
    if slot != expect_slot:
        raise SystemExit(f'{tag}: slot at {va:#x} = {slot} (expect {expect_slot})')
    lines[i] = re.sub(r'load i64, ptr %stack_var_' + re.escape(slot) + r'\b',
                      'load i64, ptr @' + glob, lines[i]) + ' ; LIFTFIX ' + tag
    return slot


def bind_slot_loads(lines: list[str], fnva: int, slot: str, glob: str, expect: int, tag: str) -> int:
    """fn 内の `load i64, ptr %stack_var_<slot>` (行頭が代入) を `load i64, ptr @<glob>` に差し替える。"""
    load = r'load i64, ptr %stack_var_' + re.escape(slot) + r'\b'
    hits = _fn_hits(lines, fnva, r'\s*%\S+ = ' + load)
    if len(hits) != expect:
        raise SystemExit(f'{tag}: sites = {len(hits)} (expect {expect})')
    for i, _ in hits:
        lines[i] = re.sub(load, 'load i64, ptr @' + glob, lines[i]) + ' ; LIFTFIX ' + tag
    return len(hits)
