#!/usr/bin/env bash
# engine_lift.sh の出力 (e.fixcmp.ll) から x86_fp80 を含む関数を除外 (declare 化) した部分集合を emcc -c する (到達性のみ; 正しさは別)。
#   bash tools/plugins/reverb_delay/engine_f80_subset.sh <block>      (ENGINE_TAG は engine_lift.sh と同じ値を渡す)
# 出力: work/reverb_delay/engine<block>${ENGINE_TAG}/{e.sub.ll, f80_excluded.tsv, summary_sub.csv}
# gate: 部分集合の emcc -c rc が 0 かつ define 数が「除外数だけ」減っていること (除外が f80 関数以外に及んでいないことの確認)。 不合格なら exit 1。
# NC: 同じ入力 (e.fixcmp.ll) の無改変 emcc -c rc を engine_lift.sh の summary.csv (第 9 列) から引く (除外が必要だったことの記録)。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
B="$1"
OUT="work/reverb_delay/engine$B${ENGINE_TAG:-}"
[ -f "$OUT/e.fixcmp.ll" ] || { echo "missing $OUT/e.fixcmp.ll (先に engine_lift.sh を実行)" >&2; exit 2; }
t0=$(date +%s)
python3 reverb_delay/engine_f80_stub.py "$OUT/e.fixcmp.ll" "$OUT/e.sub.ll" "$OUT/f80_excluded.tsv" 2> "$OUT/f80_stub.info"
NEX=$(($(wc -l < "$OUT/f80_excluded.tsv") - 1))
( source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; mkdir -p "$OUT/tmp"; TMPDIR="$OUT/tmp" emcc -c "$OUT/e.sub.ll" -o "$OUT/e.sub.o" -w -O0 -msimd128 > "$OUT/emcc_sub.log" 2>&1 )
rc=$?
t1=$(date +%s)
NFULL=$(grep -c '^define' "$OUT/e.fixcmp.ll")
NSUB=$(grep -c '^define' "$OUT/e.sub.ll")
NC=$(cut -d, -f9 "$OUT/summary.csv" 2>/dev/null || echo -1)
GATE=FAIL
[ "$rc" -eq 0 ] && [ "$NSUB" -eq $((NFULL - NEX)) ] && GATE=PASS
echo "$B,f80_excluded=$NEX,define_full=$NFULL,define_sub=$NSUB,emcc_c_rc=$rc,nc_emcc_c_rc_unmodified=$NC,gate=$GATE,sec=$((t1-t0))" | tee "$OUT/summary_sub.csv"
[ "$GATE" = PASS ]
