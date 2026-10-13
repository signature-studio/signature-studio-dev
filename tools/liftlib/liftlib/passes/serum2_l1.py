"""serum2_l1.py — Serum 2 Controller setState の L1 脱落 (直接 vtable 通知) を復元する pass (#1030 / #823)。

脱落の機構 (targets/serum2/license/authstub/REPORT.md §13): 機械語 0x1800c2d69 の `je` は [rsi+0x90] が 0 のとき
0x1800c2ef4 へ飛ぶ。そこは host handler rcx=[rsi+0x10] を読み、rcx!=0 なら `call [[rcx]+0x30]` (edx=0x800010)
で直接通知し、rcx==0 なら 0x1800c2f08 へ抜ける。RetDec raw IR では同じ null 枝が 0x1800c2f08 へ付け替わり、
0x1800c2ef4 のブロックが生成されない。

本 pass は null 枝を 0x1800c2ef4 へ戻し、機械語 0x1800c2ef4–f05 相当の命令列を IR に書き起こす。
直接 vtable 呼出しは `@__vcall_notify(vtbl, slot, this, edx)` の 1 件に畳む。
各命令には機械語 VA の `!insn.addr` を付ける (census で数えられるように)。
"""
import re

from liftlib.passes.fp_bind import fn_span, meta_va_map, site_at

FN = 0x1800C2B50
NULL_BR_VA = 0x1800C2D69
LO, HI = 0x1800C2EF4, 0x1800C2F05
EDX = 8388624  # 0x800010
SITE_LAB = 'dec_label_pc_1800c2ef4'
SKIP_LAB = 'dec_label_pc_1800c2f08'
FALL_LAB = 'dec_label_pc_1800c2d6f'
DECL = 'declare void @__vcall_notify(i64, i64, i64, i64) ; SR-8 L1: 機械語 call [[rcx]+0x30] (edx=0x800010)'


def count(lines):
    """census: 機械語 VA が [LO, HI] の IR 命令の件数。直接 call / edx 即値 / 入口 edge (label 参照)。"""
    s, e = fn_span(lines, FN)
    mv = meta_va_map(lines)
    c = dict(direct_call=0, edx_imm=0, covered=0, entry_edges=0)
    for i in range(s + 1, e):
        mm = re.search(r'!insn\.addr !(\d+)', lines[i])
        va = mv.get(mm.group(1)) if mm else None
        if va is not None and LO <= va <= HI:
            c['covered'] += 1
            if '@__vcall_notify(' in lines[i]:
                c['direct_call'] += 1
            if re.search(r'\b%d\b' % EDX, lines[i]):
                c['edx_imm'] += 1
    c['entry_edges'] = sum(1 for l in lines[s:e] if re.search(r'label %' + SITE_LAB + r'\b', l))
    return c


def restore(lines):
    """null 枝を 0x1800c2ef4 へ戻し、機械語どおりの通知ブロックを挿入する。適用 1 件でなければ失敗。"""
    if any(l.startswith(SITE_LAB + ':') for l in lines):
        raise SystemExit('serum2_l1: 通知ブロックが既に IR にある (二重適用)')
    i = site_at(lines, FN, NULL_BR_VA, r'\s*br i1 %\S+, label %' + SKIP_LAB + r', label %' + FALL_LAB)
    lines[i] = lines[i].replace('label %' + SKIP_LAB, 'label %' + SITE_LAB, 1)

    # 機械語 VA を IR のメタデータに登録する (既存 VA と重複しないことを確認)
    mv = meta_va_map(lines)
    if any(LO <= v <= HI for v in mv.values()):
        raise SystemExit('serum2_l1: 0x1800c2ef4–f05 の insn.addr が既に IR にある')
    nmax = max(int(m.group(1)) for l in lines for m in [re.match(r'^!(\d+)\s*=', l)] if m)
    vas = [0x1800C2EF4, 0x1800C2EF8, 0x1800C2EFB, 0x1800C2EFD, 0x1800C2F05]
    meta = {va: '!%d' % (nmax + 1 + k) for k, va in enumerate(vas)}
    m = lambda va: meta[va]
    block = [
        SITE_LAB + ':  ; SR-8 L1 復元 (機械語 0x1800c2ef4–f05)',
        '  %l1.a = add i64 %arg1, 16, !insn.addr ' + m(0x1800C2EF4),
        '  %l1.b = inttoptr i64 %l1.a to i64*, !insn.addr ' + m(0x1800C2EF4),
        '  %l1.rcx = load i64, i64* %l1.b, align 8, !insn.addr ' + m(0x1800C2EF4),
        '  %l1.z = icmp eq i64 %l1.rcx, 0, !insn.addr ' + m(0x1800C2EF8),
        '  br i1 %l1.z, label %' + SKIP_LAB + ', label %dec_label_pc_1800c2efd, !insn.addr ' + m(0x1800C2EFB),
        '',
        'dec_label_pc_1800c2efd:',
        '  %l1.c = inttoptr i64 %l1.rcx to i64*, !insn.addr ' + m(0x1800C2EFD),
        '  %l1.vt = load i64, i64* %l1.c, align 8, !insn.addr ' + m(0x1800C2EFD),
        '  call void @__vcall_notify(i64 %l1.vt, i64 48, i64 %l1.rcx, i64 8388624), !insn.addr ' + m(0x1800C2F05),
        '  br label %' + SKIP_LAB + ', !insn.addr ' + m(0x1800C2F05),
        '',
    ]
    j = next(k for k in range(i, len(lines)) if lines[k].startswith(FALL_LAB + ':'))
    lines[j:j] = block
    ins = next(k for k, l in enumerate(lines) if l.startswith('target datalayout'))
    lines.insert(ins + 1, DECL)
    lines.extend('!%s = !{i64 %d}' % (meta[va][1:], va) for va in vas)
    return lines
