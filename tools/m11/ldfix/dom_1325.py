#!/usr/bin/env python3
"""dom_1325.py — #1325 (LD-46): first-deref-not-entry の (関数, 引数) について、最初の deref の IR ブロック B が
%argN の全使用を支配するかを測り、関数ごとに修復可否 (支配関係つき修復の可否) を記録する。
使い方 (tools/m11 で実行): python3 ldfix/dom_1325.py [OUT.json]   (入力: work/boot_final3.ll・work/m11_image.bin・work/boot*.drc.config.json)
判定 (1 組ごと):
  b_found      : 最初の deref の機械語ブロック先頭 VA に対応する IR ブロック B があるか (無ければ no-ir-block)
  母集団       : 全関数の (関数, 引数) のうち、出所 'arg' の deref を持つもの (fix_f3c_use と同じ母集団。argv 由来は数えない)
  use_total    : IR 中の %argN の使用行数 (define 行を除く)
  use_dom      : そのうち、使用が置かれるブロックが B に支配される (B 自身を含む) 行数
  use_entry    : entry ブロックにある使用行数 (B が entry 以外なら、B より前に実行される)
  reason       : 見送り理由 (fix_f3c_use の門の順): raw-after (先頭 deref の後に生の使用) / w32 (32bit deref) /
                 no-ir-block (B の IR ブロックが無い) / no-rep-use (置換対象無し) / rep-not-dominated (置換対象が B に支配されない) /
                 dominated (修復可能。実際に直すかは fix_f3c_use の残りの門 (loaded 等) で決まる)
"""
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ldfix  # noqa: E402
from ldmach import FnMach  # noqa: E402
from ldmach_img import ImageMachine  # noqa: E402

def main():
    out = sys.argv[1] if len(sys.argv) > 1 else None
    text = open('work/boot_final3.ll', errors='replace').read()
    mach = ImageMachine('work/m11_image.bin', 'work/boot*.drc.config.json')
    for x in ldfix.DEF_RE.finditer(text):
        ldfix.F3C_ARITY[int(x.group('name')[9:], 16)] = len([p for p in x.group('args').split(',') if p.strip()])
    rows = []
    for m in ldfix.DEF_RE.finditer(text):
        k = m.group('name')[9:]
        va = int(k, 16)
        end = text.index('\n}', m.end()) + 2
        body = text[m.start():end]
        fn = ldfix.Fn('function_' + k, va, body)
        labs = [int(x, 16) for x in re.findall(r'^dec_label_pc_([0-9a-f]+)[:.]', body, re.M)]
        if not labs:
            continue
        mach.cover(va, max(labs))
        fv = FnMach(mach, va, labs)
        if not fv.ins:
            continue
        _lsf, _ptr, uses, blk0 = ldfix.f3c_track(fv)
        leaders = sorted(ldfix._f3c_leaders(fv.ins))
        blocks = fn.blocks()
        ir_va = {}
        for bi, (bva, _ls) in enumerate(blocks):
            if bva is not None:
                ir_va.setdefault(bva, bi)
        lines_only = [ls for (_bva, ls) in blocks]
        dom = ldfix.ir_dominators(ldfix.ir_succ(lines_only))
        hdr = re.match(r'define [^@]*@function_\w+\(([^)]*)\)', body).group(1).split(',')
        for n in sorted({u[2] for u in uses if u[0] == 'deref' and u[4] == 'arg'}):
            ds = [u for u in uses if u[0] == 'deref' and u[2] == n and u[4] == 'arg']
            first = min(u[1] for u in ds)
            if first in blk0:
                continue
            ls_ = [l for l in leaders if l <= first]
            bstart = ls_[-1] if ls_ else None
            bidx = ir_va.get(bstart)
            ptr = hdr[n - 1].split()[0] != 'i64'
            # %argN の使用 (define 行を除く)
            argre = re.compile(r'(?<![\w.$-])%arg' + str(n) + r'(?![\w.$-])')
            use_blocks = []
            for bi, (_bva, ls) in enumerate(blocks):
                for l in ls:
                    if l.startswith('define '):
                        continue
                    if argre.search(l):
                        use_blocks.append(bi)
            use_total = len(use_blocks)
            use_entry = sum(1 for b in use_blocks if b == 0)
            # fix_f3c_use と同じ置換対象: 機械語の生の使用の数 (keep) を先頭から残し、残りを deref 値に置換する
            keep = len([u for u in uses if u[0] == 'raw' and u[2] == n])
            rep_blocks = use_blocks[keep:]
            if any(u[0] == 'raw' and u[2] == n and u[1] > first for u in uses):
                reason, use_dom, rep_dom = 'raw-after', 0, 0
            elif not all(u[3] == 64 for u in ds):
                reason, use_dom, rep_dom = 'w32', 0, 0
            elif bidx is None:
                reason, use_dom, rep_dom = 'no-ir-block', 0, 0
            else:
                use_dom = sum(1 for b in use_blocks if bidx in dom[b])
                rep_dom = sum(1 for b in rep_blocks if bidx in dom[b])
                if not rep_blocks:
                    reason = 'no-rep-use'
                elif rep_dom == len(rep_blocks):
                    reason = 'dominated' if bidx != 0 else 'entry'
                else:
                    reason = 'rep-not-dominated'
            rows.append({'fn': 'function_' + k, 'arg': n, 'ptr': ptr,
                         'first_deref': '%x' % first, 'machine_block': '%x' % bstart if bstart is not None else None,
                         'ir_block': '%x' % blocks[bidx][0] if bidx is not None and blocks[bidx][0] is not None else None,
                         'use_total': use_total, 'use_dom': use_dom, 'use_entry': use_entry,
                         'keep': keep, 'rep': len(rep_blocks), 'rep_dom': rep_dom, 'reason': reason})
    cnt = collections.Counter(r['reason'] for r in rows)
    for r in rows:
        print('function_%s arg%d ptr=%d first=%s blk=%s ir=%s uses=%d (dom %d, entry %d) keep=%d rep=%d (dom %d) -> %s' % (
            r['fn'][9:], r['arg'], int(r['ptr']), r['first_deref'], r['machine_block'], r['ir_block'],
            r['use_total'], r['use_dom'], r['use_entry'], r['keep'], r['rep'], r['rep_dom'], r['reason']))
    print('合計 %d 組 / %d 関数' % (len(rows), len({r['fn'] for r in rows})))
    print(dict(cnt))
    if out:
        json.dump(rows, open(out, 'w'), indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
