#!/usr/bin/env bash
# nc_pe_golden.sh — GUI-7 (#183) テスト PE の NC / popup / tooltip 描画の golden (独立 Python オラクル) + ネガコン 2 本。
#   PE (test/gui_nc_app.c) -> mingw -> RetDec -> 後処理 -> gcc native + shim + headless host -> PPM -> golden/gen_golden_ncpe.py と画素比較。
#   ネガコン: (1) 期待値 1 画素改変 (--tamper) / (2) tooltip の TOPMOST 欠陥 PE (z 順欠陥) は、どちらも MISMATCH (exit 1) で拒否されなければ不合格。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/.."; B="$ROOT/build"; mkdir -p "$B"
python3 "$ROOT/gen_api.py" >/dev/null
# lift -> native 実行 (app_src, 出力先, PPM 名) を 1 組として扱う
run_pe() {
  local src="$1" out="$2" ppm="$3"
  mkdir -p "$out"
  bash "$ROOT/lift/gui_lift.sh" "$src" "$out" >"$out/lift.log" 2>&1
  gcc -O1 -g -w -fsanitize=address,undefined -pthread -I "$ROOT/include" -I "$ROOT/src" -I "$B" \
    -Wno-error=int-conversion -Wno-error=incompatible-pointer-types -Wno-error=int-to-pointer-cast \
    "$out/lifted.c" -c -o "$out/lifted.o"
  gcc -O1 -g -w -fsanitize=address,undefined -pthread -I "$ROOT/include" -I "$B" -Dmain=gui_lift_app_main \
    -c "$ROOT/lift/gui_lift_main.c" -o "$out/lift_main.o"
  gcc -O1 -g -w -fsanitize=address,undefined -pthread -I "$ROOT/include" -I "$ROOT/src" -I "$B" \
    "$out/lifted.o" "$out/lift_main.o" "$ROOT"/src/gui_platform.c "$ROOT"/src/gui_reach.c "$B"/gui_reach_tab.c "$ROOT"/src/gui_core.c "$ROOT"/src/gui_gdi.c \
    "$ROOT"/src/gui_headless.c "$B"/gui_stubs.c "$HERE/nc_pe_run.c" -o "$out/nc_pe_run" -lm
  (cd "$out" && ./nc_pe_run "$ppm")
}
run_pe "$HERE/gui_nc_app.c" "$B/ncpe_lift" "$B/ncpe_scene.ppm"
python3 "$ROOT/golden/gen_golden_ncpe.py" "$B/ncpe_scene.ppm"
# 欠陥 PE: NC_PE_FAULT_ZORDER を先頭で定義し、TOPMOST を外して main の下に隠れる tooltip の分岐を選ぶ (同じ経路で lift)
{ echo "#define NC_PE_FAULT_ZORDER 1"; cat "$HERE/gui_nc_app.c"; } >"$B/gui_nc_app_zfault.c"
run_pe "$B/gui_nc_app_zfault.c" "$B/ncpe_zfault" "$B/ncpe_zfault.ppm"
fail=0
# ネガコン 1: 期待値を 1 画素壊すと MISMATCH で exit 1 (PPM は正しいまま)
rc=0; python3 "$ROOT/golden/gen_golden_ncpe.py" "$B/ncpe_scene.ppm" --tamper >"$B/ncpe_tamper.cmp" 2>&1 || rc=$?
if [ "$rc" = 1 ] && grep -q '^MISMATCH ' "$B/ncpe_tamper.cmp"; then echo "negctl 1/2 OK: tampered golden (1 px) rejected"; else echo "NEGCTL FAIL: tampered golden not rejected as MISMATCH (rc=$rc)"; fail=1; fi
# ネガコン 2: z 順欠陥 PE の PPM は期待画像と MISMATCH になること
rc=0; python3 "$ROOT/golden/gen_golden_ncpe.py" "$B/ncpe_zfault.ppm" >"$B/ncpe_zfault.cmp" 2>&1 || rc=$?
if [ "$rc" = 1 ] && grep -q '^MISMATCH ' "$B/ncpe_zfault.cmp"; then echo "negctl 2/2 OK: z-order fault rejected ($(cut -c1-60 "$B/ncpe_zfault.cmp"))"; else echo "NEGCTL FAIL: z-order fault not rejected as MISMATCH (rc=$rc)"; fail=1; fi
[ "$fail" = 0 ] && echo "[nc-pe-golden] ALL PASS" || { echo "[nc-pe-golden] FAILED"; exit 1; }
