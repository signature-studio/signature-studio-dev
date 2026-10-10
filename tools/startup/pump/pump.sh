#!/usr/bin/env bash
# CAB-102 検収: 1 コマンドで ビルド → リンク置換テスト → C 単体 → ST(HOSTED) → MT(ATOMIC/SPIN/NONE/stress/ctrl)。
#   bash tools/startup/pump/pump.sh            (exit 0 = 全 PASS)
#   FORCE=1 で work/ のオブジェクトを作り直す。
# winstubs / shimx のソースは読取専用。ビルド物は本 dir の work/ (winstubs.sh の work/ とは共有しない)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
WORK="$HERE/work"
mkdir -p "$WORK"
[ "${FORCE:-0}" = 1 ] && rm -rf "$WORK/obj_ST" "$WORK/obj_MT"
B="bash $HERE/scripts/build.sh"
info() { echo "[pump] $*"; }

info "1/6 オブジェクトビルド (shimx + winstubs 読取専用ソース + pump; ST/MT, 本 dir 専用 work/)"
$B objs ST
$B objs MT
info "    shimx $(ls "$WORK"/obj_ST/shimx/*.o | wc -l) obj / winstubs $(ls "$WORK"/obj_ST/ws/*.o | wc -l) obj / pump $(ls "$WORK"/obj_ST/pump/*.o | wc -l) obj"

info "2/6 リンク (unit ST / weak 対照 ST / e2e ST / e2e MT)"
DUPLOG="$WORK/link.log"
: > "$DUPLOG"
$B link ST "$WORK/unit_st.js"  unit "$HERE/test/pump_unit.c"  2>&1 | tee -a "$DUPLOG"
mv "$WORK/unit_st.js" "$WORK/unit_st.cjs"
$B link ST "$WORK/weak_st.js"  weak "$HERE/test/weakprobe.c"  2>&1 | tee -a "$DUPLOG"
mv "$WORK/weak_st.js" "$WORK/weak_st.cjs"
$B link ST "$WORK/e2e_st.js"   pumpmod "$HERE/test/pump_e2e.c" 2>&1 | tee -a "$DUPLOG"
mv "$WORK/e2e_st.js" "$WORK/e2e_st.cjs"
$B link MT "$WORK/e2e_mt.js"   pumpmod -sPTHREAD_POOL_SIZE=2 "$HERE/test/pump_e2e.c" 2>&1 | tee -a "$DUPLOG"
mv "$WORK/e2e_mt.js" "$WORK/e2e_mt.cjs"
DUP="$(grep -o 'duplicate symbol: [A-Za-z0-9_]*' "$DUPLOG" | sed 's/duplicate symbol: //' | sort -u || true)"
if [ -n "$DUP" ]; then
    echo "[pump] FAIL: リンクで duplicate symbol: $DUP" >&2
    exit 1
fi
info "    duplicate symbol なし (winstubs weak × pump 強定義)"

info "3/6 (a) リンク置換テスト + C 単体テスト (node)"
node "$HERE/host/run_e2e.mjs" "$WORK" unit

info "4/6 ST (HOSTED): ブロックせずホストへ返す経路"
node "$HERE/host/run_e2e.mjs" "$WORK" st

info "5/6 MT: (b) ATOMIC 疎通 / (c) 遅延・SPIN・NONE(worklet 相当) / (d) 2000 件ストレス / ctrl RTT"
node "$HERE/host/run_e2e.mjs" "$WORK" mt

info "6/7 headless Chrome (D 検収と同一環境での RING ABI 遅延比較)"
bash "$HERE/scripts/build.sh" link MT "$WORK/chrome/pump_chrome.js" pumpchrome "$HERE/test/pump_e2e.c" 2>&1 | grep -E "error" && exit 1 || true
node "$HERE/host/run_chrome.mjs" "$WORK"

info "7/7 完了: 全 PASS (詳細: $WORK/e2e_summary.json, $WORK/chrome_summary.json)"
