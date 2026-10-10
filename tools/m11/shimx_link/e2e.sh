#!/usr/bin/env bash
# M11 + shimx リンクの 1 コマンド e2e (CAB-166)。常に exit 0 (到達点を再現して数値を出す)。
#   bash tools/m11/shimx_link/e2e.sh
# 前提: bash tools/m11/m11_e2e.sh が一度通っていること (tools/m11/work/ の lift 成果物)。
# 生成: tools/m11/work/shimx_link/ (一時物) と tools/m11/shimx_link/results/ (小さな集計のみ。コミット対象)
set -u
cd "$(dirname "$0")"
export PATH="$HOME/.local/share/pnpm/bin:$PATH"
W=../work/shimx_link
mkdir -p "$W" results
step() { echo "[sxl_e2e] $*"; }
b() { bash build.sh "$@" > "$W/build_$(echo "$*" | tr -d ' -')_log.txt" 2>&1 && step "build $*: $(tail -1 "$W/build_$(echo "$*" | tr -d ' -')_log.txt")" || { step "build $* FAILED"; tail -5 "$W/build_$(echo "$*" | tr -d ' -')_log.txt"; }; }

# (1) 純リンク (IR 無改変) と (2) 補正付きリンク
b                     # plain / GUI fail-fast / IR 無改変
b --soft              # plain / GUI 0 返却
b --soft --fix        # + alloca 拡幅 + 列挙コールバックアダプタ
b --trace --soft --fix
b --trace --fix       # fail-fast GUI + 補正 (最初に当たる GUI API を特定)

# gen557: shimx REPORT の分母 (boot_final2.ll) での分類
mkdir -p "$W/gen557"
python3 gen_link.py --ir ../work/boot_final2.ll --shimx-nm "$W/shimx_nm.txt" --m11-nm "$W/m11_nm.txt" --out "$W/gen557" 2>/dev/null | head -1

# 実行 (SHIMX_TRACE=1)
for v in plain_failfast plain_soft plain_soft_fix trace_failfast_fix trace_soft_fix; do
  [ -f "$W/m11_sx_$v.cjs" ] || continue
  SHIMX_TRACE=1 node run_trace.mjs "$W/m11_sx_$v.cjs" 2>&1 | grep SXL_RESULT | cut -c1-420
done
# unit 隔離 survey (shimx / 既存 M11 ビルド)
SHIMX_TRACE=1 node survey_trace.mjs "$W/m11_sx_trace_soft_fix.cjs" 2>&1 | grep SXL_SURVEY | cut -c1-300
node survey_trace.mjs ../work/m11_boot.cjs --out "$W/baseline" 2>&1 | grep SXL_SURVEY | cut -c1-300
python3 analyze.py
# 小さな実行ログをコミット対象に保存
cp "$W/m11_sx_trace_soft_fix.stderr.txt" results/stderr_trace_soft_fix.txt 2>/dev/null
cp "$W/fix_report.json" results/fix_alloca_report.json 2>/dev/null
cp "$W/gen_fix/classes.json" results/classes_boot_final3.json 2>/dev/null
cp "$W/gen557/classes.json" results/classes_boot_final2.json 2>/dev/null
exit 0
