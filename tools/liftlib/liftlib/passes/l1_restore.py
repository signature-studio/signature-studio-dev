"""liftlib.passes.l1_restore — 直接 vtable 通知 (`call [rax+0x30]`) の脱落を復元する (Serum2 authstub L1, #823 / #1009)。

入力: RetDec raw .ll。機械語 0x1800c2d69 の `je 0x1800c2ef4` の真の枝 (null 枝) が、lift 時に
dec_label_pc_1800c2f08 へ付け替わっている (authstub REPORT §13 / REPORT_APPENDIX §13b)。
出力: 当該 `br` の真の枝を新設ブロック dec_label_pc_1800c2ef4 へ戻し、そのブロックに
  host = [rsi+0x10]; host==0 なら skip; else BLK 前段 store → call __icall_dispatch(0x1800c2f05) → skip
を置く。BLK 前段 store は icall_rewrite.py の `st(...)` と同じ配置 (icall_rt.c の読み取り位置):
  BLK+0x00 = target = [[host]+0x30] (機械語 `mov rax,[rcx]; call [rax+0x30]`)
  BLK+0x08 = rcx = host
  BLK+0x10 = rdx = 0x800010 (機械語 `mov edx,0x800010`)
BLK の絶対アドレスは icall_rt.c の既定 ICALL_BLK (0x34308000) を既定値とし、引数 blk で差し替える。
"""
import re
import sys
from typing import Callable, Match

from liftlib.passes.fp_bind import fn_span, site_at

FN = 0x1800C2B50
SITE_JE = 0x1800C2D69
ENTRY = 0x1800C2EF4
VT_LOAD_VA = 0x1800C2EFD
EDX_VA = 0x1800C2F00
CALL_VA = 0x1800C2F05
SKIP = 0x1800C2F08
SKIP_LAB = 'dec_label_pc_%x' % SKIP
ENTRY_LAB = 'dec_label_pc_%x' % ENTRY
DECL = 'declare void @__icall_dispatch(i64)'
BLK_DEFAULT = 0x34308000
RDX_VAL = 0x800010
VT_SLOT = 0x30


def _next_meta_id(lines: list[str]) -> int:
    ids = [int(m.group(1)) for l in lines for m in [re.match(r'^!(\d+)\s*=', l)] if m]
    return max(ids) + 1


def _block(m: dict[str, int], blk: int) -> list[str]:
    e = '!insn.addr !' + str(m['entry'])
    v = '!insn.addr !' + str(m['vt'])
    d = '!insn.addr !' + str(m['edx'])
    c = '!insn.addr !' + str(m['call'])
    st: Callable[[int], str] = lambda off: 'inttoptr (i64 %d to i64*)' % (blk + off)
    return [
        '',
        ENTRY_LAB + ':                           ; LIFTFIX L1 (restored, #823)',
        '  %l1h.p = add i64 %arg1, 16, ' + e,
        '  %l1h.pp = inttoptr i64 %l1h.p to i64*, ' + e,
        '  %l1host = load i64, i64* %l1h.pp, align 8, ' + e,
        '  %l1nul = icmp eq i64 %l1host, 0, ' + e,
        '  br i1 %l1nul, label %' + SKIP_LAB + ', label %l1_call, ' + e,
        '',
        'l1_call:                                         ; LIFTFIX L1 (BLK 前段 store, #1497)',
        '  %l1vt.pp = inttoptr i64 %l1host to i64*, ' + v,
        '  %l1vt = load i64, i64* %l1vt.pp, align 8, ' + v,
        '  %l1fn.p = add i64 %l1vt, ' + str(VT_SLOT) + ', ' + v,
        '  %l1fn.pp = inttoptr i64 %l1fn.p to i64*, ' + v,
        '  %l1tgt = load i64, i64* %l1fn.pp, align 8, ' + v,
        '  store i64 %l1tgt, i64* ' + st(0) + ', align 8, ' + v,
        '  store i64 %l1host, i64* ' + st(8) + ', align 8, ' + v,
        '  store i64 %d, i64* %s, align 8, ' % (RDX_VAL, st(0x10)) + d,
        '  call void @__icall_dispatch(i64 ' + str(CALL_VA) + '), ' + c,
        '  br label %' + SKIP_LAB + ', ' + c,
        '',
    ]


def restore_l1(lines: list[str], blk: int = BLK_DEFAULT) -> dict[str, object]:
    if any(l.startswith(ENTRY_LAB + ':') for l in lines):
        raise SystemExit('l1_restore: 0x1800c2ef4 ブロックが既に存在する (二重適用)')
    s, e = fn_span(lines, FN)
    pat = r'\s*br i1 %110, label %' + SKIP_LAB + r', label %dec_label_pc_1800c2d6f, (!insn\.addr !\d+)'
    i_br = site_at(lines, FN, SITE_JE, pat)
    m_br = re.match(pat, lines[i_br])
    assert m_br is not None, 'l1_restore: SITE_JE の br 行が pat に一致しない'
    meta_br = m_br.group(1)
    mid = _next_meta_id(lines)
    m = {'entry': mid, 'vt': mid + 1, 'edx': mid + 2, 'call': mid + 3}
    lines[i_br] = '  br i1 %110, label %' + ENTRY_LAB + ', label %dec_label_pc_1800c2d6f, ' + meta_br
    i_skip = next(i for i in range(s + 1, e) if lines[i].startswith(SKIP_LAB + ':'))
    lines[i_skip:i_skip] = _block(m, blk)
    lines.append('!%d = !{i64 %d}' % (m['entry'], ENTRY))
    lines.append('!%d = !{i64 %d}' % (m['vt'], VT_LOAD_VA))
    lines.append('!%d = !{i64 %d}' % (m['edx'], EDX_VA))
    lines.append('!%d = !{i64 %d}' % (m['call'], CALL_VA))
    if DECL not in lines:
        ins = next(i for i, l in enumerate(lines) if l.startswith('target datalayout'))
        lines.insert(ins + 1, DECL)
    return {'br_line': i_br + 1, 'entry': ENTRY_LAB, 'call_va': hex(CALL_VA), 'blk': hex(blk),
            'meta': [m['entry'], m['vt'], m['edx'], m['call']]}


def main() -> None:
    src, dst = sys.argv[1], sys.argv[2]
    lines = open(src).read().splitlines()
    rep = restore_l1(lines)
    open(dst, 'w').write('\n'.join(lines) + '\n')
    print('l1_restore:', rep, '->', dst)


if __name__ == '__main__':
    main()
