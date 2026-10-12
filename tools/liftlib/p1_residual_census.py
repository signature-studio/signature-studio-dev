#!/usr/bin/env python3
"""p1_residual_census.py — [LIFTLIB-4] p1 残留 UNSUPPORTED の内訳を数える (規則 37)。

1 コマンド再現:
    python3 tools/liftlib/p1_residual_census.py

数え方の定義 (規則 36):
  - 母集合 = OTT (`OTT_vst2_win64.dll`) の RetDec raw `.ll` (`tools/m6/work/ott.drc.ll`) を
    base 正規化した module の `function_<hex>` define で, `img.func_at(va)` が解決できるもの。
  - 適用パス = **既定の OTT auto と同じ順**: f2 の callee 相 (入口 xmm 引数の付与) →
    f7 → p1 (p1 は関数ごとに run_function)。
  - 1 件 = `p1.run_function` が 1 回 `UNSUPPORTED` を出す site。理由は `@<addr>` を `@X`,
    SSA 名を `%V` に潰して集計する (アドレスや SSA 番号で別件に割れないようにするため)。
  - `--json` で機械可読。

この条件での LIFTLIB-4 実測 = 残留 6 (LIFTLIB-3 は 15, LIFTLIB-2 (f2 無し) は 21)。
"""
import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from liftlib import ir as IR                      # noqa: E402
from liftlib.pe import Image                      # noqa: E402
from liftlib.passes import base, p1, f2           # noqa: E402

from liftlib.env import OTT_DLL as DLL          # noqa: E402
RAW = os.path.join(HERE, "..", "m6", "work", "ott.drc.ll")


def census():
    img = Image(DLL)
    text, _ = base.run_base(open(RAW).read(), base.make_args())
    mod = IR.Module.parse(text)
    # 既定 --auto (f2,f7,p1) と同じ順。f2 は callee 相のみ (callsite 相は recipe 側と衝突)
    f2.run(mod, img, [], {}, phase="callee")
    log, st = [], {}
    for fn in mod.funcs():
        va = int(fn.name.split("_")[1], 16) if re.match(r"function_[0-9a-f]+$", fn.name) else None
        if va is None or img.func_at(va) is None:
            continue
        p1.run_function(mod, fn, img, True, log, st)
    cnt = collections.Counter()
    for l in log:
        if l.startswith("UNSUPPORTED"):
            r = l.split(": ", 1)[1]
            r = re.sub(r"@[0-9a-f]+", "@X", r)
            r = re.sub(r"%[^\s]+", "%V", r)
            cnt[r] += 1
    return st, cnt, log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--addrs", action="store_true", help="site アドレスも出す")
    a = ap.parse_args()
    st, cnt, log = census()
    if a.json:
        print(json.dumps(dict(stats=st, reasons=dict(cnt),
                              addrs=[l for l in log if "UNSUPPORTED" in l]),
                         indent=1, ensure_ascii=False))
        return 0
    print("[p1_residual_census] 母集合 = base 正規化後の function_<hex> define (img.func_at 解決分)")
    print("                    適用 = f2 callee → f7 → p1 (既定 --auto と同順)")
    for k, v in cnt.most_common(40):
        print("  %3d  %s" % (v, k))
    print("  --- 合計: unsupported=%d reconstructed=%d rewired=%d" % (
        st.get("unsupported", 0), st.get("reconstructed", 0), st.get("rewired", 0)))
    if a.addrs:
        print("  --- addresses ---")
        for l in log:
            if "UNSUPPORTED" in l:
                print("     ", l)
    return 0


if __name__ == "__main__":
    sys.exit(main())
