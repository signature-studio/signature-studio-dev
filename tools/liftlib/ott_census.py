#!/usr/bin/env python3
"""ott_census.py — OTT 出力の junk census (junkHi 等) を再計算して期待値と突合する (#478)。

数え方の定義 (recipes/ott/e2e_check.mjs の E6 と同一。定義は REPORT_APPENDIX.md の #478 節):
  条件 : param 0.5 (setup(0.5))・入力 N=256 sample×2ch・出力 float32 512 値 (ch0 256 + ch1 256)
         object の byte [0x248] を 0 / 1 にして processReplacing を 1 回
  分類 : 値 v (a=|v|) を上から順に
         v==0 → zero / NaN → nan / a>=4 → junkHi / a<=1e-18 → junkTiny / それ以外 → normal
  junkHi = 「|v|>=4 の出力値の個数」(OTT の出力は ±1 付近が正常なので、4 以上は未初期化読み由来の junk とみなす)

使い方:
  python3 tools/liftlib/ott_census.py <ott.cjs> [--f248 0|1] [--expect-junkhi N] [--max-junkhi N]
  期待値を 1 つも与えなければ値を表示するだけ (exit 0)。--expect-junkhi は一致、--max-junkhi は上限。
  取得不能 (census 行が出ない) は常に exit 2。違反は exit 1。
既定の期待値: --auto none (m10 chain 再現) = junkHi 175 ([0x248]=0) / auto 既定 = 104 以下 (cli.OTT_AUTO_JUNKHI_MAX)。
"""
import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
E2E = os.path.join(HERE, "liftlib", "recipes", "ott", "e2e_check.mjs")


def census(cjs, f248=0, env_extra=None):
    e = dict(os.environ, OTT_CJS=os.path.abspath(cjs), OTT_SWEEP_TIMEOUT=os.environ.get("OTT_SWEEP_TIMEOUT", "60"))
    if env_extra:
        e.update(env_extra)
    r = subprocess.run(["node", E2E], capture_output=True, text=True, env=e, timeout=900)
    m = re.search(r"census \[0x248\]=%d : (\{.*\})" % f248, r.stdout + r.stderr)
    return json.loads(m.group(1)) if m else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cjs")
    ap.add_argument("--f248", type=int, choices=(0, 1), default=0)
    ap.add_argument("--expect-junkhi", type=int)
    ap.add_argument("--max-junkhi", type=int)
    a = ap.parse_args(argv)
    c = census(a.cjs, a.f248)
    if c is None:
        print("[census] 取得不能 (e2e_check.mjs が census 行を出さなかった)", file=sys.stderr)
        return 2
    print("[census] [0x248]=%d: %s" % (a.f248, json.dumps(c)))
    bad = []
    if a.expect_junkhi is not None and c["junkHi"] != a.expect_junkhi:
        bad.append("junkHi %d != 期待 %d" % (c["junkHi"], a.expect_junkhi))
    if a.max_junkhi is not None and c["junkHi"] > a.max_junkhi:
        bad.append("junkHi %d > 上限 %d" % (c["junkHi"], a.max_junkhi))
    for b in bad:
        print("[census] NG:", b, file=sys.stderr)
    print("[census] RESULT:", "FAIL" if bad else "PASS")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
