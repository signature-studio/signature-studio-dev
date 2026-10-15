#!/usr/bin/env python3
# variant_summary.py — PERF-P14 (#970): variant_boot.sh の summary.tsv を label 別に集計する。
#   python3 tools/flelift/boot/variant_summary.py [summary.tsv] [--check]
# 既定の入力は tools/flelift/work/boot/variant/summary.tsv (FLE_BOOT_WORK で場所を変えると、その下の variant/summary.tsv)。
# 同じ (label, run) の行が複数あるときは最後の行だけを採用する (variant_boot.sh の再実行で重複行が増えるため)。
# p50 / p90 は線形補間 (順位 q*(n-1) を両隣の実測値で補間。numpy の既定 linear と同じ)。min–max は実測値そのまま。
# --check: 別実装 (statistics.quantiles, method='inclusive') で p50 / p90 を再計算し、差が 1e-9 を超えたら非 0 で終了する。
import csv, json, math, os, statistics, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT = os.path.join(HERE, "..", "work", "boot", "variant", "summary.tsv")
if os.environ.get("FLE_BOOT_WORK"):
    DEFAULT = os.path.join(os.environ["FLE_BOOT_WORK"], "variant", "summary.tsv")


def pct(xs, q):
    s = sorted(xs)
    pos = q * (len(s) - 1)
    lo = math.floor(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def load(path):
    last = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            last[(r["label"], r["run"])] = r
    groups = {}
    for (label, _), r in last.items():
        groups.setdefault(label, []).append(r)
    return groups


def main():
    args = [a for a in sys.argv[1:] if a != "--check"]
    path = args[0] if args else DEFAULT
    groups = load(path)
    print(f"# summary: {path}")
    print("| label | wasm (B) | n | p50 (s) | p90 (s) | min–max (s) | units_run | va_bytes | signature | rc | FLEBOOT_IPP_CHECK |")
    print("|---|--:|--:|--:|--:|---|--:|--:|---|---|---|")
    bad = 0
    for label, rows in groups.items():
        secs = [float(r["wall_sec"]) for r in rows]
        res = [json.loads(r["FLEBOOT_RESULT"]) for r in rows if r["FLEBOOT_RESULT"]]
        p50, p90 = pct(secs, 0.5), pct(secs, 0.9)
        if "--check" in sys.argv:
            p50_b = statistics.quantiles(secs, n=2, method="inclusive")[0]
            p90_b = statistics.quantiles(secs, n=10, method="inclusive")[8]
            if abs(p50 - p50_b) > 1e-9 or abs(p90 - p90_b) > 1e-9:
                bad += 1
                print(f"# CHECK FAIL {label}: p50 {p50} vs {p50_b}, p90 {p90} vs {p90_b}", file=sys.stderr)
        uniq = lambda xs: ",".join(sorted({str(x) for x in xs}))
        print(f"| {label} | {rows[0]['wasm_bytes']} | {len(rows)} | {p50:.3f} | {p90:.3f} | "
              f"{min(secs):.3f}–{max(secs):.3f} | {uniq(x['units_run'] for x in res)} | "
              f"{uniq(x['va_bytes'] for x in res)} | {uniq(r['signature'] for r in rows)} | "
              f"{uniq(r['rc'] for r in rows)} | {uniq(r['ipp_check'] for r in rows)} |")
    if bad:
        sys.exit(1)


if __name__ == "__main__":
    main()
