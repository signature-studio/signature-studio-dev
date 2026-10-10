#!/usr/bin/env bash
# 「CAB-129 修正後、--fix なし純リンクで 17 unit 再測」の検証手順 (CAB-211 / M11 shimx_link REPORT §6)。
#
#   bash tools/shimx/scripts/rem11_check.sh
#
# やること:
#   1. tools/m11/shimx_link/build.sh --trace --soft で **純リンク** (IR 無改変・alloca 拡幅/コールバック
#      アダプタ等の --fix 一切無し) のトレース付きビルドを作る
#   2. run_trace.mjs で起動実行 (SHIMX_TRACE=1) し unit 到達数と shim 呼出を収集
#   3. reach_check.py で「静的到達するが動的呼出が無い shimx API 133 名」(M11 reach.json) のうち
#      本実行で検証できた名を算出 (R8 進捗)
#
# 判定: init_count >= 18 かつ longjmp_hit == 0 なら「真の 17 unit 完走」(unit #18 に進入 = CAB-129 修正の効果)。
# 現状 (CAB-129 未修正) は init_count=17 / longjmp_hit=1 / boot_rc=1 の「shadow stack 破壊による偽の DllMain 完走」
# で停止するのが既知の到達点 (M11 REPORT §0, §3-#2)。--fix を付けた対照は tools/m11/shimx_link/e2e.sh。
#
# 成果物は tools/shimx/work/rem11/ (gitignore) と m11/work/shimx_link/ (m11 側の一時物, gitignore)。
# tools/m11/shimx_link/ の tracked ファイルは読取のみで改変しない。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../.." && pwd)"
SXW="$REPO/shimx/work/rem11"
OUT_TAG="m11_sx_trace_soft"

echo "[rem11] 1/3 純リンク (no --fix) ビルド"
bash "$REPO/m11/shimx_link/build.sh" --trace --soft || { echo "[rem11] ビルド失敗 (M11 成果物が無ければ先に bash tools/m11/m11_e2e.sh)"; exit 2; }

echo "[rem11] 2/3 起動実行 (SHIMX_TRACE=1)"
set +u; . /opt/emsdk/emsdk_env.sh > /dev/null 2>&1; set -u
mkdir -p "$SXW"
SHIMX_TRACE=1 node "$REPO/m11/shimx_link/run_trace.mjs" "$REPO/m11/work/shimx_link/$OUT_TAG.cjs" --out "$SXW" > "$SXW/run_stdout.txt" 2>&1 || true
grep SXL_RESULT "$SXW/run_stdout.txt" | cut -c1-300 || tail -5 "$SXW/run_stdout.txt"

echo "[rem11] 3/3 判定 + R8 進捗"
python3 "$HERE/reach_check.py" --run "$SXW/$OUT_TAG.run.json" --out "$SXW/reach_progress.md" || exit 1

python3 - "$SXW/$OUT_TAG.run.json" <<'PYEOF'
import json, sys
r = json.load(open(sys.argv[1]))
# 判定基準 (M11 shimx_link REPORT §0/§3-#2 の実測と対応):
#   純リンクの現状 (CAB-129 未修正)  = init_count=17 / dllmain_done=True / longjmp_hit=1 / boot_rc=1
#     → shadow stack 破壊による「偽の DllMain 完走」で、17 unit 完走とは言えない
#   真の 17 unit 完走 (--fix 対照 = CAB-129 修正後の期待)
#                                  = init_count=18 (unit #18 に進む) / longjmp_hit=0 / unit #18 OOB で停止
ic, ljh = r.get('init_count'), r.get('longjmp_hit')
ok = (ic is not None and ic >= 18 and ljh == 0)
print('[rem11] 判定: init_count=%s longjmp_hit=%s threw=%s boot_rc=%s -> %s' % (
    ic, ljh, (r.get('threw') or '')[:40], r.get('boot_rc'),
    '真の 17 unit 完走 (unit #18 に進入 — CAB-129 修正の効果を確認)' if ok
    else '偽の DllMain 完走 (init_count=17 で longjmp — CAB-129 未修正の既知状態)'))
sys.exit(0)
PYEOF
