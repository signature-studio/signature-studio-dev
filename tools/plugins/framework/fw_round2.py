#!/usr/bin/env python3
"""fw_round2.py — 本体 lift (fw_lift.sh) の decode 漏れ関数を第二ラウンドで解消する.

背景: fw_prep.py の F.ranges は .pdata 由来ゆえ, decode 済み関数から直接 call される
「.pdata 非登録関数」(RetDec が declare+call だけ出す) が本体に定義無しで残る
(m11 の closure 漏れ (a) と同根; 実測 990 件 / images 外 3 件はデータ呼出 artifact)。
本 pass は IR を走査して callee 集合 - define 集合 = missing を ranges CSV にし,
RetDec decode → ir_icall_restore → merge で本体 IR に足す (固定点まで最大 --rounds 回)。

  python3 fw_round2.py --ir fw_all.restored.ll --map fw_map.json --ranges-out r2.ranges [--max N]
出力: r2.ranges (無ければ固定点) と stderr サマリ
"""
import argparse, json, re, sys


def scan(ir):
    defs, calls = set(), set()
    cur = False
    with open(ir, errors='replace') as f:
        for line in f:
            if line.startswith('define '):
                cur = True
                m = re.match(r'define \S+ @function_([0-9a-f]+)\(', line)
                if m:
                    defs.add(int(m.group(1), 16))
                continue
            if cur and line.startswith('}'):
                cur = False
            for m in re.finditer(r'call [^@]*@function_([0-9a-f]+)\(', line):
                calls.add(int(m.group(1), 16))
    return defs, calls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ir', required=True)
    ap.add_argument('--map', required=True)
    ap.add_argument('--ranges-out', required=True)
    ap.add_argument('--max', type=lambda x: int(x, 0), default=0xd03000, help='range 上限 (image top)')
    a = ap.parse_args()
    m = json.load(open(a.map))
    fset = {int(k, 16) for k in m['func_map']}
    defs, calls = scan(a.ir)
    missing = sorted(calls - defs)
    inimg = [v for v in missing if 0x401000 <= v < a.max and v not in fset]
    # 4KB 窓 → 隣接/重複区間を併合 (decode-only は範囲内の実コードのみ取り込む)
    ivs = []
    for v in inimg:
        if ivs and v <= ivs[-1][1] + 1:
            ivs[-1][1] = max(ivs[-1][1], v + 4095)
        else:
            ivs.append([v, v + 4095])
    ranges = ['0x%x-0x%x' % (lo, hi) for lo, hi in ivs]
    open(a.ranges_out, 'w').write(','.join(ranges))
    print('[round2] missing %d (in-image %d) -> %d merged ranges' % (len(missing), len(inimg), len(ranges)), file=sys.stderr)


if __name__ == '__main__':
    main()
