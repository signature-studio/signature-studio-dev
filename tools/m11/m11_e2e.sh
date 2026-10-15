#!/usr/bin/env bash
# M11 e2e (1 コマンド再現): FLEngine_x64.dll 部分起動 PoC (audio/GUI なし)
#   DllMain(entry_point) → _StartLib → _InitLib → InitUnits(942 unit) を RetDec lift → emcc → wasm → node で実行し,
#   到達 stage / 停止理由 / FastMM4 状態 / 各種数値を機械判定して出力する. 期待値 (e2e_expect.env) を下回れば exit 1 (#715 回帰ゲート).
#   #680 fail-closed: 前提不足 (PE・emsdk・node・capstone/pefile) / IR 生成 (ldfix skip 含む) / build (qstore skip 含む) の失敗は非 0.
#   PE は tools/shared/env.sh の FL_WIN64_DIR 経由 (既定 /home/ubuntu/work/analysis/win64)。IR 生成条件は work/ir_conditions.json に記録し judge が印字する.
# 使い方:
#   M11_EXPECT_STAGE=5 M11_EXPECT_SURVEY_OK=850 bash tools/m11/m11_e2e.sh  # 期待値の上書き (既定は e2e_expect.env)。下回れば exit 1 (#715)
#   bash tools/m11/m11_e2e.sh           # work/ の成果物があれば再利用 (無ければ自動で全再生成), build は増分
#   bash tools/m11/m11_e2e.sh --full    # RetDec lift から全再生成 (scan→functions_dll.csv (無ければ Ghidra 12.1.4 で作成)→bounds→lift 4chunk→tail 固定点→IR→build; 実測 約 22 分 (Ghidra での CSV 作成 約 10 分を含む。REPORT_N3172 §3))
#   bash tools/m11/m11_e2e.sh --trace   # icall / unit init のトレースを stderr に出す
#   M11_LB_BASE=0x10000 bash tools/m11/m11_e2e.sh   # LVA = RVA + 0x10000 (#222; 既定 0 = 従来 LVA=RVA). 変更時は --full 推奨 (IR の VA→LVA remap が変わる)
# 前提: /opt/emsdk, /opt/retdec, node(v26: ~/.local/share/pnpm/bin), analysis/win64/extracted/block00031_PE.bin
set -u
cd "$(dirname "$0")"
# #715 fail-closed: 期待値ファイルが無いと回帰ゲートが黙って無効になるため、無ければ前提確認より前に非 0 で止める
[ -f e2e_expect.env ] || { echo "[m11_e2e] e2e_expect.env 無し: 回帰ゲートの期待値が読めない (fail-closed)"; echo "M11_SUMMARY {\"reached_stage\":0,\"stop_reason\":\"e2e_expect.env missing (fail-closed)\"}"; exit 1; }
source e2e_expect.env     # M11_EXPECT_STAGE / M11_EXPECT_SURVEY_OK (環境変数が優先)
case "$M11_EXPECT_STAGE" in ''|*[!0-9]*) echo "[m11_e2e] M11_EXPECT_STAGE が整数でない: '$M11_EXPECT_STAGE' (fail-closed)"; exit 1 ;; esac
case "$M11_EXPECT_SURVEY_OK" in ''|*[!0-9]*) echo "[m11_e2e] M11_EXPECT_SURVEY_OK が整数でない: '$M11_EXPECT_SURVEY_OK' (fail-closed)"; exit 1 ;; esac
source ../shared/env.sh   # FL_WIN64_DIR (既定は従来どおり /home/ubuntu/work/analysis/win64)
export PATH="$HOME/.local/share/pnpm/bin:$PATH"
FULL=0; TRACE=0
for a in "$@"; do case "$a" in --full) FULL=1 ;; --trace) TRACE=1 ;; esac; done
mkdir -p work work/tmp
LOG=work/e2e_steps.log
: > "$LOG"
step() { echo "[m11_e2e] $*"; }
must() { # must <label> <cmd...> : fail-closed (#680). IR 生成・build の失敗は測定結果を作らず非 0 で終了する
  local label="$1"; shift
  if "$@" >> "$LOG" 2>&1; then step "$label: ok"; return 0; fi
  step "$label: FAILED (fail-closed; $LOG 末尾)"; tail -15 "$LOG"
  echo "M11_SUMMARY {\"reached_stage\":0,\"stop_reason\":\"$label failed (fail-closed)\"}"; exit 1
}

PE="${M11_PE:-${PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}}"
export PE M11_PE="$PE"
miss=0
[ -f "$PE" ] || { step "PE バイナリ無し: $PE"; miss=1; }
[ -x /opt/emsdk/emsdk_env.sh ] || [ -f /opt/emsdk/emsdk_env.sh ] || { step "emsdk 無し"; miss=1; }
command -v node > /dev/null || { step "node 無し"; miss=1; }
python3 -c 'import capstone, pefile' 2>/dev/null || { step "capstone/pefile 無し (ldfix・qstore が必要)"; miss=1; }
if [ $miss = 1 ]; then echo "M11_SUMMARY {\"reached_stage\":0,\"stop_reason\":\"prerequisite missing\"}"; exit 1; fi

need_lift=0
for i in 0 1 2 3; do [ -f work/boot$i.lift.ll ] || need_lift=1; done
[ -f work/boot_final.ll ] || need_lift=1
PE_PREV="$(python3 m11_cond.py --get pe)"   # IR を生成した PE (#680 review: PE が変わったら IR・data/image を作り直す)
PE_SHA="$(sha256sum "$PE" | cut -d' ' -f1)"   # #728: lift 成果物を生成した PE の指紋 (work/lift_pe.sha256)
[ "$(cat work/lift_pe.sha256 2>/dev/null)" = "$PE_SHA" ] || need_lift=1
if [ $FULL = 1 ] || [ $need_lift = 1 ]; then
  step "全再生成モード (scan → bounds → lift → tail 固定点 → IR)"
  [ -f work/scan_index.json ] && [ $FULL = 0 ] || must "m11_scan" python3 m11_scan.py
  must "functions_dll.csv (Ghidra 12.1.4)" bash m11_ghidra_dll.sh   # #3172: 素材に無い中間物。無ければ作る (有れば即 0)
  must "m11_bounds" python3 m11_bounds.py
  must "lift 4 chunks (RetDec)" bash m11_lift_all.sh
  for it in 1 2 3; do
    must "m11_tail #$it" python3 m11_tail.py
    must "lift boot4 #$it" bash m11_lift.sh work/boot_ranges_extra.txt boot4 600
    must "gen_ir2 #$it" bash m11_gen_ir2.sh
  done
  [ -f m11_extra_ranges5.txt ] && { must "lift boot5 (RetDec)" bash m11_lift.sh m11_extra_ranges5.txt boot5 600; must "gen_ir2 (boot5 追加)" bash m11_gen_ir2.sh; }
  echo "$PE_SHA" > work/lift_pe.sha256
else
  # #222: IR の VA→LVA remap は M11_LB_BASE 依存。stamp が違えば lift 成果物 (LB 非依存) から IR だけ再生成
  # #680 (review): 既存 work/ の回復 — ldfix 未記録 (旧スナップショット)・IR 指紋不一致・PE 変更でも gen_ir2 を走らせる
  if [ ! -f work/boot_final.ll ] || [ "$(cat work/ir_lb_base.stamp 2>/dev/null)" != "${M11_LB_BASE:-0}" ] \
     || [ "$(python3 m11_cond.py --get ldfix)" != applied ] || ! python3 m11_cond.py --check work/boot_final.ll \
     || [ "$PE_PREV" != "$PE" ]; then
    must "gen_ir2 (M11_LB_BASE=${M11_LB_BASE:-0})" bash m11_gen_ir2.sh
  fi
fi
# #132: boot5 = 間接 call 先の fallback 実装 (m11_extra_ranges5.txt, 25 関数). 無ければ RetDec で lift して IR を作り直す
if [ -f m11_extra_ranges5.txt ]; then
  [ -f work/boot5.lift.ll ] || must "lift boot5 (RetDec)" bash m11_lift.sh m11_extra_ranges5.txt boot5 600
  if [ work/boot5.lift.ll -nt work/boot_final.ll ] || ! grep -q '^define [^@]*@function_457860(' work/boot_final.ll; then
    must "gen_ir2 (boot5 追加)" bash m11_gen_ir2.sh
  fi
fi
echo "${M11_LB_BASE:-0}" > work/ir_lb_base.stamp
if [ "$PE_PREV" != "$PE" ]; then rm -f work/m11_data.c work/m11_image.bin; fi
if [ "$(cat work/img_lb_base.stamp 2>/dev/null)" != "${M11_LB_BASE:-0}" ]; then rm -f work/m11_data.c work/m11_image.bin; fi
echo "${M11_LB_BASE:-0}" > work/img_lb_base.stamp
[ -f work/m11_data.c ] || must "m11_data_gen" python3 m11_data_gen.py "$PE"
[ -f work/m11_image.bin ] || must "m11_image_gen" python3 m11_image_gen.py "$PE"
if python3 -c 'import pefile' 2>/dev/null; then  # #222: LB_BASE 適用の静的検査 (M11_LB_BASE 未指定 = 0 では reloc 値のみ検査)
  must "lb_check (M11_LB_BASE=${M11_LB_BASE:-0})" python3 lb_check.py "$PE" work/m11_image.bin "${M11_LB_BASE:-0}"
fi
must "build (emcc 増分)" bash m11_build.sh

if [ ! -f work/m11_boot.cjs.wasm ]; then
  step "wasm 未生成: build ログ ($LOG) 末尾"; tail -15 "$LOG"
  echo "M11_SUMMARY {\"reached_stage\":0,\"stop_reason\":\"build failed\"}"; exit 1
fi

step "実行 A: 通常起動 (DllMain attach → InitUnits ループ)"
M11_TRACE=$TRACE M11_PTRCHECK_MAX_NEW="${M11_EXPECT_PTR_NEW_MAX:-}" timeout 300 node m11_run.mjs > work/e2e_full.out 2>&1; rc_run=$?
step "実行 B: unit survey (942 unit を try/catch 隔離)"
M11_PTRCHECK_SURVEY_MAX_NEW="${M11_EXPECT_PTR_SURVEY_NEW_MAX:-}" timeout 600 node m11_survey.mjs > work/e2e_survey.out 2>&1; rc_survey=$?
step "実行 C: 寛容起動 (InitUnits を逐次 942 unit・失敗 unit は skipped として続行; #2714)"
M11_TOLERANT_OUT=work/tolerant_units.json timeout 600 node m11_tolerant.mjs > work/e2e_tolerant.out 2>&1 || true

# #715: 回帰ゲート。期待値 (e2e_expect.env・環境変数で上書き可) を下回れば judge が非 0 を返し、e2e も非 0 で終わる
python3 m11_judge.py --require-stage "$M11_EXPECT_STAGE" --min-survey-ok "$M11_EXPECT_SURVEY_OK"; rc=$?
# #2714: 寛容起動のゲート (942 unit 試行・集計の整合) と strict・survey の完全一致の回帰, およびネガコン (退行入力を検出できること)
python3 m11_tolerant_gate.py --strict-done "$M11_EXPECT_STRICT_DONE" --survey-ok "$M11_EXPECT_SURVEY_OK_EXACT"; rct=$?
python3 m11_tolerant_gate.py --negctl --strict-done "$M11_EXPECT_STRICT_DONE" --survey-ok "$M11_EXPECT_SURVEY_OK_EXACT"; rcn=$?
[ "$rct" = 0 ] && [ "$rcn" = 0 ] || rc=1
# #2778: 実行 A・B の終了コード (ptrcheck ゲート不合格は非 0。基準 M11_EXPECT_PTR_*_NEW_MAX が未設定なら常に 0)
[ "$rc_run" = 0 ] && [ "$rc_survey" = 0 ] || rc=1
python3 m11_icall_audit.py 2>/dev/null | tail -1 || true
exit $rc
