#!/usr/bin/env bash
# lift_determinism_e2e.sh — RetDec lift 出力の決定性回帰 (LIFTLIB-9 / #668)。
#
#   bash tools/liftlib/lift_determinism_e2e.sh            # 既定 2 run (DET_RUNS=N で変更)
#
#   同一 PE・同一 ranges で RetDec を N 回実行し (奇数 run は ASLR 有効、偶数 run は setarch -R で ASLR 無効)、
#   liftlib base 段 (run_base: A7 の uselistorder 除去 + canon_alloca_order の alloca 正規化) を通した
#   成果物の sha256 が全 run で一致することを確認する。不一致・ネガコン失敗はいずれも非 0 で終了。
#   比較手順: raw の *.drc.ll は uselistorder の並びが実行ごとに変わるため sha256 比較に使わない。
#   比較対象は run_base 出力 (base.ll) のみ。
#
# 入力 (読取のみ): $ANALYSIS_DIR/plugins/ott/binaries/OTT_vst2_win64.dll (analysis-ott-binaries)
#                  tools/m6/work/ott_ranges.txt (work-m6-ott)
# 出力: tools/liftlib/work/determ/ (gitignore)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$HERE"
N="${DET_RUNS:-2}"
[ "$N" -ge 2 ] 2>/dev/null || { echo "[lift_determinism_e2e] DET_RUNS は 2 以上の整数 (比較 0 組で PASS させない): $N" >&2; exit 2; }
ANALYSIS_DIR="${ANALYSIS_DIR:-$HOME/analysis}"
PE="${DET_PE:-$ANALYSIS_DIR/plugins/ott/binaries/OTT_vst2_win64.dll}"
RANGES_F="${DET_RANGES:-$HERE/../m6/work/ott_ranges.txt}"
OUT="${DET_OUT:-$HERE/work/determ}"

need() { [ -e "$1" ] || { echo "[lift_determinism_e2e] 前提が無い: $1  ($2)" >&2; exit 2; }; }
need "$PE" "analysis-ott-binaries を \$ANALYSIS_DIR に展開 (DET_PE で別入力を指定可)"
need "$RANGES_F" "work-m6-ott を展開 (tools/m6/work/ott_ranges.txt。DET_RANGES で別入力を指定可)"
need /opt/retdec/bin/retdec-decompiler "toolchain-retdec"

case "$OUT" in
  ""|/|"$HOME"|"$HOME/") echo "[lift_determinism_e2e] DET_OUT が不正 (空・/・\$HOME は rm -rf 対象にできない): '$OUT'" >&2; exit 2 ;;
esac
rm -rf "$OUT"; mkdir -p "$OUT"
RANGES="$(cat "$RANGES_F")"
echo "[lift_determinism_e2e] RetDec x$N (並列) functions=$(echo "$RANGES" | tr ',' '\n' | wc -l) load=$(cut -d' ' -f1 /proc/loadavg)"
T0=$(date +%s)
for i in $(seq 1 "$N"); do
  mkdir -p "$OUT/r$i/tmp"
  # 奇数 run は ASLR 有効、偶数 run は setarch -R (ASLR 無効) で混ぜる (LIFTLIB-11 / #887: on/off 間の一致を見る)
  if [ $(( i % 2 )) = 0 ]; then PFX=(setarch x86_64 -R); else PFX=(); fi
  ( TMPDIR="$OUT/r$i/tmp" "${PFX[@]}" /opt/retdec/bin/retdec-decompiler "$PE" -o "$OUT/r$i/ott.drc.c" \
      --select-ranges "$RANGES" --select-decode-only --timeout 2400 > "$OUT/r$i/retdec.log" 2>&1
    echo $? > "$OUT/r$i/rc" ) &
done
wait

RC=0
for i in $(seq 1 "$N"); do
  if [ "$(cat "$OUT/r$i/rc" 2>/dev/null)" != 0 ] || [ ! -f "$OUT/r$i/ott.drc.ll" ]; then
    echo "[lift_determinism_e2e] FAIL: RetDec r$i (rc=$(cat "$OUT/r$i/rc" 2>/dev/null))" >&2
    RC=1
  fi
done
[ "$RC" = 0 ] || exit 1
echo "[lift_determinism_e2e] RetDec 完了: $(( $(date +%s) - T0 ))s load_after=$(cut -d' ' -f1 /proc/loadavg)"

python3 "$HERE/lift_determinism_check.py" "$OUT" "$N" || { echo "[lift_determinism_e2e] FAIL" >&2; exit 1; }
echo "[lift_determinism_e2e] PASS (総所要 $(( $(date +%s) - T0 ))s)"
