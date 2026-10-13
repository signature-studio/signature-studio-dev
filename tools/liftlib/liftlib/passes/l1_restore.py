"""liftlib.passes.l1_restore — 直接 vtable 通知 (`call [rax+0x30]`) の脱落を復元する (Serum2 authstub L1, #823 / #1009)。

入力: RetDec raw .ll。機械語 0x1800c2d69 の `je 0x1800c2ef4` の真の枝 (null 枝) が、lift 時に
dec_label_pc_1800c2f08 へ付け替わっている (authstub REPORT §13 / REPORT_APPENDIX §13b)。
出力: 当該 `br` の真の枝を新設ブロック dec_label_pc_1800c2ef4 へ戻し、そのブロックに
  host = [rsi+0x10]; host==0 なら skip; else call __icall_dispatch(0x1800c2f05) → skip
を置く。call の引数 (rcx=host, edx=0x800010) の受け渡しは #228 (icall) の ABI に従う別工程で、
本 pass は site の VA と制御辺だけを復元する。
各 site は機械語 VA (insn.addr) で指定し、1 件でなければ失敗する。
"""
import re
import sys

from liftlib.passes.fp_bind import fn_span, site_at

FN = 0x1800C2B50
SITE_JE = 0x1800C2D69
ENTRY = 0x1800C2EF4
CALL_VA = 0x1800C2F05
SKIP = 0x1800C2F08
SKIP_LAB = 'dec_label_pc_%x' % SKIP
ENTRY_LAB = 'dec_label_pc_%x' % ENTRY
DECL = 'declare void @__icall_dispatch(i64)'


def _next_meta_id(lines):
    ids = [int(m.group(1)) for l in lines for m in [re.match(r'^!(\d+)\s*=', l)] if m]
    return max(ids) + 1


def _block(m_entry, m_call):
    e = '!insn.addr !' + str(m_entry)
    c = '!insn.addr !' + str(m_call)
    return [
        '',
        ENTRY_LAB + ':                           ; LIFTFIX L1 (restored, #823)',
        '  %l1h.p = add i64 %arg1, 16, ' + e,
        '  %l1h.pp = inttoptr i64 %l1h.p to i64*, ' + e,
        '  %l1host = load i64, i64* %l1h.pp, align 8, ' + e,
        '  %l1nul = icmp eq i64 %l1host, 0, ' + e,
        '  br i1 %l1nul, label %' + SKIP_LAB + ', label %l1_call, ' + e,
        '',
        'l1_call:                                         ; LIFTFIX L1',
        '  call void @__icall_dispatch(i64 ' + str(CALL_VA) + '), ' + c,
        '  br label %' + SKIP_LAB + ', ' + c,
        '',
    ]


def restore_l1(lines):
    if any(l.startswith(ENTRY_LAB + ':') for l in lines):
        raise SystemExit('l1_restore: 0x1800c2ef4 ブロックが既に存在する (二重適用)')
    s, e = fn_span(lines, FN)
    pat = r'\s*br i1 %110, label %' + SKIP_LAB + r', label %dec_label_pc_1800c2d6f, (!insn\.addr !\d+)'
    i_br = site_at(lines, FN, SITE_JE, pat)
    meta_br = re.match(pat, lines[i_br]).group(1)
    mid = _next_meta_id(lines)
    m_entry, m_call = mid, mid + 1
    lines[i_br] = '  br i1 %110, label %' + ENTRY_LAB + ', label %dec_label_pc_1800c2d6f, ' + meta_br
    i_skip = next(i for i in range(s + 1, e) if lines[i].startswith(SKIP_LAB + ':'))
    lines[i_skip:i_skip] = _block(m_entry, m_call)
    lines.append('!%d = !{i64 %d}' % (m_entry, ENTRY))
    lines.append('!%d = !{i64 %d}' % (m_call, CALL_VA))
    if DECL not in lines:
        ins = next(i for i, l in enumerate(lines) if l.startswith('target datalayout'))
        lines.insert(ins + 1, DECL)
    return {'br_line': i_br + 1, 'entry': ENTRY_LAB, 'call_va': hex(CALL_VA), 'meta': [m_entry, m_call]}


def main():
    src, dst = sys.argv[1], sys.argv[2]
    lines = open(src).read().splitlines()
    rep = restore_l1(lines)
    open(dst, 'w').write('\n'.join(lines) + '\n')
    print('l1_restore:', rep, '->', dst)


if __name__ == '__main__':
    main()
