#!/usr/bin/env python3
"""#912: 4fb090 の 4fa070 呼出しの第 2 引数 (dl) の IR 修復 pass (冪等・双方向).

機械語 4fb090: 4fb12f `mov dl,1` → 4fb134 `call 4fa070` (rcx = [rip-0x86df] = VA 0x4f2a50 の値 = VMT 0x4f2b18, dl = 1).
RetDec の IR (function_4fb090) はこの dl を定数 1 ではなく、スタック変数 (%stack_var_-255) の番地の
下位 byte (`%37 = ptrtoint ... %stack_var_-255`) として渡す。dl が 0 だと 4fa070 は 410320 (ClassCreate) を
飛ばし、クラス (VMT) 自身を 410360 に渡す。410360 は VMT の [vmt-0x50] を読むため、0x41037d 経由で oob になる
(ok 退行 101 / 291 / 296 の直接原因。REPORT_912 §5)。

--mode on : `i64 %37` → `i64 1` (機械語どおり)。--mode off : 逆変換 (ネガコン用)。
対象行が 1 件でない場合は exit 1 (黙って通さない)。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lb_base import VA_TO_LVA  # noqa: E402  (#3188: VMT の LVA は M11_LB_BASE で動く。LB=0 では 994072)

VMT_LVA = 0x4F2B18 + VA_TO_LVA
OLD = '%%39 = call i64 @function_4fa070(ptr nonnull inttoptr (i64 %d to ptr), i64 %%37, ptr %%38)' % VMT_LVA
NEW = '%%39 = call i64 @function_4fa070(ptr nonnull inttoptr (i64 %d to ptr), i64 1, ptr %%38)' % VMT_LVA


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--mode', choices=['on', 'off'], default='on')
    ap.add_argument('--report')
    a = ap.parse_args()
    s = open(a.src).read()
    before, after = (OLD, NEW) if a.mode == 'on' else (NEW, OLD)
    n_before, n_after = s.count(before), s.count(after)
    if n_before == 1:
        out, n = s.replace(before, after), 1
    elif n_after == 1:
        out, n = s, 0
    else:
        print('[fix912] FAIL: 対象行が無い (before=%d after=%d)' % (n_before, n_after), file=sys.stderr)
        sys.exit(1)
    open(a.dst, 'w').write(out)
    if a.report:
        json.dump({'mode': a.mode, 'replaced': n}, open(a.report, 'w'), indent=1)
    print('[fix912] mode=%s replaced=%d' % (a.mode, n))


if __name__ == '__main__':
    main()
