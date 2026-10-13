#!/usr/bin/env bash
# KH-7 (#59) 1 コマンド再現: HeartCore の UI 層を M7 GUI shim (tools/gui) へ接続できるかを実バイナリで評価する。
#   bash tools/targets/kilohearts/ui_eval/run_all.sh
# exit: 0 = 接続準備 OK (全検査 PASS) / 1 = 評価の前提違反・ネガコン失敗・素材なし / 2 = 前提は成立、接続準備に未達 (gap) が残る
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
export KH_UI_WORK="${KH_UI_WORK:-$HERE/work}"; mkdir -p "$KH_UI_WORK"
SCR="$HERE/../scripts"
if python3 -c 'import pefile, capstone, numpy' 2>/dev/null; then PY=(python3)
else PY=(uv run --no-project --with pefile --with capstone --with numpy python); fi
t0=$(date +%s); echo "load(start): $(cut -d' ' -f1-3 /proc/loadavg)  nproc=$(nproc)"
CORE=$(bash "$HERE/extract_core.sh" | tail -1) || { echo "素材なし/検証失敗"; exit 1; }
echo "core: $CORE ($(stat -c %s "$CORE") B)"
[ -f "$KH_UI_WORK/rtti_vtables.json" ] || "${PY[@]}" "$SCR/rtti_walk.py" "$CORE" "$KH_UI_WORK/rtti_vtables.json" >/dev/null || exit 1
[ -f "$KH_UI_WORK/callgraph.pkl" ] || "${PY[@]}" "$SCR/callgraph.py" "$CORE" "$KH_UI_WORK/rtti_vtables.json" "$KH_UI_WORK/callgraph.pkl" 4 >/dev/null || exit 1
rc=(); names=()
run() { local n="$1"; shift; echo; echo "===== $n"; "$@"; local r=$?; echo "----- $n exit=$r"; rc+=("$r"); names+=("$n"); }
run "1 ui_imports (import 面・GPU 不在・shim 被覆)" "${PY[@]}" "$HERE/ui_imports.py" "$CORE" "$KH_UI_WORK/ui_imports.json"
run "2 ui_present (画面転送呼び出しの復元)" "${PY[@]}" "$HERE/ui_present.py" "$CORE" "$KH_UI_WORK/ui_present.json"
run "3 ui_closure (UI/Skia 規模・OS 境界クラス)" "${PY[@]}" "$HERE/ui_closure.py" "$CORE" "$KH_UI_WORK/callgraph.pkl" "$KH_UI_WORK/rtti_vtables.json" "$KH_UI_WORK/ui_closure.json"
command -v llvm-objdump >/dev/null || { echo "llvm-objdump が無い: 別算法検算ができない"; exit 1; }
llvm-objdump -d --no-show-raw-insn --section=.text "$CORE" > "$KH_UI_WORK/objdump.txt" || exit 1
run "4 xcheck_xref (別算法: llvm-objdump 線形逆アセンブルとの突合)" "${PY[@]}" "$HERE/xcheck_xref.py" "$CORE" "$KH_UI_WORK/objdump.txt"
run "5 shim_probe (M7 GUI shim へ実形で投入)" bash "$HERE/shim_probe.sh"
# 修正案 (g1_shim_fix.patch) を当てた作業コピーで同じプローブが 0 (全一致) になること。0 以外は REPORT の主張 (修正案で 7/7) が偽 = 評価無効として 1 にする
expect0() { bash "$HERE/shim_probe_fixed.sh"; local r=$?; [ "$r" -eq 0 ] || { echo "修正案を当てても全一致にならない (exit=$r)"; return 1; }; }
run "6 shim_probe_fixed (G1 修正案の事前検証; 期待 exit 0)" expect0
echo; echo "===== summary (所要 $(( $(date +%s) - t0 )) s, load(end): $(cut -d' ' -f1-3 /proc/loadavg))"
worst=0
for i in "${!rc[@]}"; do echo "  exit=${rc[$i]}  ${names[$i]}"; [ "${rc[$i]}" -eq 1 ] && worst=1; [ "$worst" -ne 1 ] && [ "${rc[$i]}" -eq 2 ] && worst=2; [ "${rc[$i]}" -gt 2 ] && worst=1; done
case $worst in 0) echo "VERDICT: READY";; 2) echo "VERDICT: NOT READY (gap あり。REPORT §6 の未解決を参照)";; *) echo "VERDICT: EVALUATION INVALID (前提違反/ネガコン失敗/異常終了)";; esac
exit $worst
