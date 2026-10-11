#!/usr/bin/env python3
"""xmm0_ret_census.py — [LIFTLIB-3] 汎用 xmm0-ret bind の効果を数える (SUBAGENT_RULES 規則 37)。

1 コマンド再現:
    python3 tools/liftlib/xmm0_ret_census.py

数え方の定義 (規則 36):
  - 「y 個」= OTT (.dll) の各関数について, 機械語 (capstone) の**全 ret ブロック**で
    xmm0 の到達定義が関数内 (ENTRY でない) ものを数える。1 関数 = 1 カウント。
  - 「n 個」= RetDec raw .ll の module に define がある関数だけを対象にする
    (declare のみ / image 外は母集合から除外)。
  - 判定は Binder/MFunc.ret_in_xmm0() の実装をそのまま呼ぶ (独自実装の使い回しでは
    ない: 別アルゴリズムの検算を counts_alt() に入れている)。

出力: 表形式で stdout に集計。--json で機械可読。
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from liftlib import ir as IR                      # noqa: E402
from liftlib.mc import MFunc                      # noqa: E402
from liftlib.pe import Image                      # noqa: E402
from liftlib.passes import base as B              # noqa: E402

DLL = "/home/ubuntu/work/analysis/plugins/ott/binaries/OTT_vst2_win64.dll"
RAW = os.path.join(HERE, "..", "m6", "work", "ott.drc.ll")


def leaf_module():
    """leafspec cfg と同じ closure を持つ module (base 正規化済み)。"""
    text, _ = B.run_base(open(RAW).read(), B.make_args())
    return IR.Module.parse(text)


def counts_main():
    """母集合 = leaf module の function_<hex> define。ret_in_xmm0() で数える。"""
    img = Image(DLL)
    mod = leaf_module()
    hit, total = [], 0
    for fn in mod.funcs():
        nm = fn.name
        if not re.match(r"function_[0-9a-f]+$", nm):
            continue
        va = int(nm.split("_")[1], 16)
        rng = img.func_at(va)
        if rng is None:
            continue
        total += 1
        mf = MFunc(img, *rng)
        if mf.ret_in_xmm0():
            hit.append(nm)
    return hit, total


def counts_alt():
    """別アルゴリズムでの検算 (rule 37): ENTRY→ret の**全経路**で xmm0 が書かれるか。

    MFunc.defs_before は may 解析 (reaching defs = 経路の和)。`0 not in d` =
    「xmm0 が未書のままの経路が 1 本も存在しない」。本関数はその補集合, つまり
    「ENTRY から ret まで xmm0 を一度も書かない経路が存在するか」を
    (block, xmm0書込み有無) の組で worklist して直接調べる。実装が全く別で,
    判定の向きも逆 (存在判定 vs 不在判定) なので独立検算になる。
    """
    img = Image(DLL)
    mod = leaf_module()
    hit, total = [], 0
    for fn in mod.funcs():
        nm = fn.name
        if not re.match(r"function_[0-9a-f]+$", nm):
            continue
        va = int(nm.split("_")[1], 16)
        rng = img.func_at(va)
        if rng is None:
            continue
        total += 1
        mf = MFunc(img, *rng)
        cfg = mf.cfg()
        rets = set(v for v in mf.order if mf.insns[v].is_ret)
        if not rets:
            continue
        start = mf.start
        # (block, wrote) を key に訪れたか。wrote=True の到達を禁じれば
        # 「どこかで書いた」経路を除外できる
        seen, todo = set(), [(start, False)]
        bad = False
        while todo and not bad:
            blk, wrote = todo.pop()
            if (blk, wrote) in seen:
                continue
            seen.add((blk, wrote))
            w = wrote
            for v in cfg[blk]["vas"]:
                if v in rets and not w:
                    bad = True          # 未書のまま ret に到達
                    break
                if "xmm0" in mf.insns[v].writes:
                    w = True
            if bad:
                break
            for s in cfg[blk]["succ"]:
                todo.append((s, w))
        if not bad:
            hit.append(nm)
    return hit, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    hit, total = counts_main()
    hit2, total2 = counts_alt()
    d = dict(denominator=total, detected=len(hit), alt_denominator=total2, alt_detected=len(hit2),
             agree=set(hit) == set(hit2), funcs=sorted(hit),
             diff=sorted(set(hit) ^ set(hit2)))
    if a.json:
        print(json.dumps(d, indent=1, ensure_ascii=False))
        return 0
    print("[xmm0_ret_census] 定義: leaf module の function_<hex> define のうち, 機械語の全 ret で")
    print("                 xmm0 の到達定義が関数内 (ENTRY でない) なもの = 1 カウント")
    print("  分母 (leaf define, image 内)        : %d" % total)
    print("  ret_in_xmm0() で検出                : %d" % len(hit))
    print("  別アルゴリズム (linear 走査) で検出  : %d" % len(hit2))
    print("  両者の一致                          : %s" % ("YES" if d["agree"] else "NO %s" % d["diff"]))
    print("  関数名:")
    for nm in sorted(hit):
        print("    ", nm)
    return 0 if d["agree"] else 1


if __name__ == "__main__":
    sys.exit(main())
