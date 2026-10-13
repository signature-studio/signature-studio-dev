"""lift_determinism_check.py — RetDec raw .drc.ll の非決定性を liftlib base 段の出力で判定する (LIFTLIB-9 / #668)。

  python3 lift_determinism_check.py <outdir> <runs>

<outdir>/r<i>/ott.drc.ll (同一入力で RetDec を実行した raw) を liftlib.passes.base.run_base に通し
(A7 で uselistorder 行を除去する段を含む)、<outdir>/r<i>/base.ll を書く。
全 run の base.ll の sha256 が一致すれば PASS。raw の sha256 は表示のみで判定には使わない
(raw は uselistorder の順序が実行ごとに変わるため)。

ネガコン 1: r1 の base.ll に 1 行を足した複製が、同じ比較関数で「不一致」と判定されること。
ネガコン 2: DET_NEGCTRL_NO_BASE=1 で run_base (A7) を外し raw をそのまま比較すると FAIL になること
(検出力の実測用。この設定では必ず exit 1 になる)。
PASS かつネガコン 1 検出のときのみ exit 0。それ以外は exit 1。
"""
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from liftlib.passes import base as B  # noqa: E402


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def same(a, b):
    return sha(a) == sha(b)


def main():
    out, runs = sys.argv[1], int(sys.argv[2])
    no_base = os.environ.get("DET_NEGCTRL_NO_BASE") == "1"
    rows = []
    for i in range(1, runs + 1):
        d = os.path.join(out, "r%d" % i)
        raw = os.path.join(d, "ott.drc.ll")
        base = os.path.join(d, "base.ll")
        t0 = time.time()
        if no_base:
            text = open(raw).read()
        else:
            text, _ = B.run_base(open(raw).read(), B.make_args())
        with open(base, "w") as f:
            f.write(text)
        rows.append({
            "run": i,
            "raw_sha256_12": sha(raw)[:12],
            "base_sha256_12": sha(base)[:12],
            "base_lines": text.count("\n"),
            "base_sec": round(time.time() - t0, 1),
        })

    print("run  raw_sha256(情報)  base_sha256(判定)  base_lines  base_sec")
    for r in rows:
        print("r%-3d %-18s %-18s %-11d %s" % (r["run"], r["raw_sha256_12"], r["base_sha256_12"], r["base_lines"], r["base_sec"]))

    r1 = os.path.join(out, "r1", "base.ll")
    det_pass = all(same(r1, os.path.join(out, "r%d" % i, "base.ll")) for i in range(2, runs + 1))

    neg = os.path.join(out, "r1", "base.negctrl.ll")
    with open(r1) as f:
        body = f.read()
    with open(neg, "w") as f:
        f.write(body + "; NEG-CONTROL (LIFTLIB-9): one appended line must be detected as a mismatch\n")
    nc_detected = not same(r1, neg)

    verdict = {
        "runs": runs,
        "rows": rows,
        "determinism": "PASS" if det_pass else "FAIL",
        "negctrl_detected": nc_detected,
    }
    with open(os.path.join(out, "summary.json"), "w") as f:
        json.dump(verdict, f, ensure_ascii=False, indent=1)
    print("determinism(base.ll 全 run 一致): %s" % verdict["determinism"])
    print("negctrl(1 行追加を不一致と検出): %s" % ("detected" if nc_detected else "NOT detected"))
    return 0 if (det_pass and nc_detected) else 1


if __name__ == "__main__":
    sys.exit(main())
