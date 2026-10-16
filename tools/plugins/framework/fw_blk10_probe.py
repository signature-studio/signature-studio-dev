#!/usr/bin/env python3
"""BLK+0x10 (9048080) への整数 store の直前に実行時ダンプ呼出しを挿入する (#4143)。

入力: fw_flat4_canon3.ll。出力: 挿入済みの .ll と、挿入位置の対応表 (JSON)。
各 store の直前に次を入れる:
  %blk10dbgN = zext/trunc/値そのもの (i64 へ)
  call void @fw_dbg_blk10(i64 %blk10dbgN, i32 <元 .ll の行番号>)
呼出し先は fw_blk10_probe.c (fw_dbg_blk10) が実装する。

ポインタの解決は fw_blk_writers.py と同じ 2 形 (named / inline 定数式) で、
対応表の native 番地は、同じ関数内で直前にある `dec_label_pc_<hex>:` ラベル
(ブロック単位の近似。ラベルより前の store は前のブロックのラベルに寄る)。
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fw_blk_writers import fn_re, ptr_re, st_re, st_const_re  # noqa: E402

BLK10 = 9048080
# BLK+0x10 に加えて、エラーコード格納候補 (fw_blk_writers.py の ERRCODE=7155720 と隣接 7155712)
PROBE_ADDRS = {BLK10, 7155712, 7155720}
label_re = re.compile(r'^(dec_label_pc_([0-9a-fA-F]+)):')
# 値は貪欲に取り、最後の `, ptr <番地>` を番地とする (値の getelementptr 内の `ptr @x` と区別)
st_any = re.compile(r'^\s*store (\w+) (.+), ptr (%[\w.]+|inttoptr \(.*\))(?:, align \d+)?\s*$')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ll')
    ap.add_argument('--out', required=True)
    ap.add_argument('--map', required=True)
    a = ap.parse_args()
    lines = open(a.ll, errors='replace').read().split('\n')
    out, mp = [], {}
    fn, ptrs, label = None, {}, None
    declared = False
    for ln, line in enumerate(lines, 1):
        if line.startswith('define '):
            m = fn_re.match(line)
            fn, ptrs, label = (m.group(1) if m else '?'), {}, None
            if not declared:
                out.append('declare void @fw_dbg_blk10(i64, i32)')
                declared = True
            out.append(line)
            continue
        if fn is None:
            out.append(line)
            continue
        m = label_re.match(line)
        if m:
            label = m.group(2)
        m = ptr_re.match(line)
        if m:
            ptrs[m.group(1)] = int(m.group(2))
            out.append(line)
            continue
        st = st_any.match(line)
        ty = val = addr = None
        if st:
            ty, val = st.group(1), st.group(2)
            at = st.group(3)
            m = re.fullmatch(r'(%[\w.]+)', at)
            if m and m.group(1) in ptrs:
                addr = ptrs[m.group(1)]
            else:
                m = re.fullmatch(r'inttoptr \((?:i\d+ )?(\d+) to ptr\)', at)
                addr = int(m.group(1)) if m else None
        if addr in PROBE_ADDRS and ty in ('ptr', 'i8', 'i16', 'i32', 'i64'):
            tmp = f'%blk10dbg{ln}'
            if ty == 'ptr':
                out.append(f'  {tmp} = ptrtoint ptr {val} to i64')
                arg = tmp
            elif ty == 'i64':
                arg = val
            else:
                out.append(f'  {tmp} = zext {ty} {val} to i64')
                arg = tmp
            out.append(f'  call void @fw_dbg_blk10(i64 {arg}, i32 {ln})')
            mp[ln] = {'fn': fn, 'native_label': label, 'store': line.strip()[:160]}
        out.append(line)
    open(a.out, 'w').write('\n'.join(out))
    json.dump(mp, open(a.map, 'w'), indent=1)
    print(f'probes inserted: {len(mp)}')


if __name__ == '__main__':
    main()
