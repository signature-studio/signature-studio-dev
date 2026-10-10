#!/usr/bin/env bash
# M11 e2e (1 コマンド再現): FLEngine_x64.dll 部分起動 PoC (audio/GUI なし)
#   DllMain(entry_point) → _StartLib → _InitLib → InitUnits(942 unit) を RetDec lift → emcc → wasm → node で実行し,
#   到達 stage / 停止理由 / FastMM4 状態 / 各種数値を機械判定して出力する. 未達でも現在の到達点を再現して exit 0.
# 使い方:
#   bash tools/m11/m11_e2e.sh           # work/ の成果物があれば再利用 (無ければ自動で全再生成), build は増分
#   bash tools/m11/m11_e2e.sh --full    # RetDec lift から全再生成 (scan→bounds→lift 4chunk→tail 固定点→IR→build; 約 10 分)
#   bash tools/m11/m11_e2e.sh --trace   # icall / unit init のトレースを stderr に出す
# 前提: /opt/emsdk, /opt/retdec, node(v26: ~/.local/share/pnpm/bin), analysis/win64/extracted/block00031_PE.bin
set -u
cd "$(dirname "$0")"
export PATH="$HOME/.local/share/pnpm/bin:$PATH"
FULL=0; TRACE=0
for a in "$@"; do case "$a" in --full) FULL=1 ;; --trace) TRACE=1 ;; esac; done
mkdir -p work work/tmp
LOG=work/e2e_steps.log
: > "$LOG"
step() { echo "[m11_e2e] $*"; }
run() { # run <label> <cmd...> : 失敗しても継続 (rc を記録)
  local label="$1"; shift
  if "$@" >> "$LOG" 2>&1; then step "$label: ok"; return 0; else step "$label: FAILED (rc=$?; $LOG 参照)"; return 1; fi
}

PE=/home/ubuntu/work/analysis/win64/extracted/block00031_PE.bin
miss=0
[ -f "$PE" ] || { step "PE バイナリ無し: $PE"; miss=1; }
[ -x /opt/emsdk/emsdk_env.sh ] || [ -f /opt/emsdk/emsdk_env.sh ] || { step "emsdk 無し"; miss=1; }
command -v node > /dev/null || { step "node 無し"; miss=1; }
if [ $miss = 1 ]; then echo "M11_SUMMARY {\"reached_stage\":0,\"stop_reason\":\"prerequisite missing\"}"; exit 0; fi

need_lift=0
for i in 0 1 2 3; do [ -f work/boot$i.lift.ll ] || need_lift=1; done
[ -f work/boot_final.ll ] || need_lift=1
if [ $FULL = 1 ] || [ $need_lift = 1 ]; then
  step "全再生成モード (scan → bounds → lift → tail 固定点 → IR)"
  [ -f work/scan_index.json ] && [ $FULL = 0 ] || run "m11_scan" python3 m11_scan.py
  run "m11_bounds" python3 m11_bounds.py
  run "lift 4 chunks (RetDec)" bash m11_lift_all.sh
  for it in 1 2 3; do
    run "m11_tail #$it" python3 m11_tail.py
    run "lift boot4 #$it" bash m11_lift.sh work/boot_ranges_extra.txt boot4 600
    run "gen_ir2 #$it" bash m11_gen_ir2.sh
  done
else
  [ -f work/boot_final.ll ] || run "gen_ir2" bash m11_gen_ir2.sh
fi
[ -f work/m11_data.c ] || run "m11_data_gen" python3 m11_data_gen.py
[ -f work/m11_image.bin ] || run "m11_image_gen" python3 m11_image_gen.py
run "build (emcc 増分)" bash m11_build.sh

if [ ! -f work/m11_boot.cjs.wasm ]; then
  step "wasm 未生成: build ログ ($LOG) 末尾"; tail -15 "$LOG"
  echo "M11_SUMMARY {\"reached_stage\":0,\"stop_reason\":\"build failed\"}"; exit 0
fi

step "実行 A: 通常起動 (DllMain attach → InitUnits ループ)"
M11_TRACE=$TRACE timeout 300 node m11_run.mjs > work/e2e_full.out 2>&1 || true
step "実行 B: unit survey (942 unit を try/catch 隔離)"
timeout 600 node m11_survey.mjs > work/e2e_survey.out 2>&1 || true

python3 m11_judge.py
exit 0
