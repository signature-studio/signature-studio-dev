#!/usr/bin/env bash
# lift IR 署名ゲート (SHX-T7, #173): sig_normalize.py で IR を shimx 署名へ正規化 → verify_sig.sh で mismatch 0 を保証する。
#   使い方: bash scripts/sig_gate.sh <ir.ll> [tag]
#   出力 : work/sig/<tag>.norm.ll (正規化 IR) / <tag>.norm.json (report) / 正規化前後の mismatch 数
#   exit : 正規化後 mismatch 0 かつ unresolved 0 → 0 / それ以外 → 1 (CI が落ちる)
#   正規化前の mismatch 数は情報として出す (SIG_GATE_RAW=0 で省略)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"
IR="$1"; TAG="${2:-ir}"
mkdir -p "$HERE/work/sig"
NORM="$HERE/work/sig/$TAG.norm.ll"
python3 "$HERE/scripts/gen_sigs.py" --check
python3 "$HERE/scripts/sig_normalize.py" "$IR" "$NORM" --report "$HERE/work/sig/$TAG.norm.json" --strict
if [ "${SIG_GATE_RAW:-1}" = 1 ]; then
    RAW=0; bash "$HERE/scripts/verify_sig.sh" "$IR" "$TAG.raw" > "$HERE/work/sig/$TAG.raw.out" 2>&1 || RAW=1
    echo "[sig_gate] $TAG: 正規化前 $(grep -h 'signature mismatch =' "$HERE/work/sig/$TAG.raw.out" | tail -1 | sed 's/.*= //') 件 (情報)"
fi
bash "$HERE/scripts/verify_sig.sh" "$NORM" "$TAG.norm"
