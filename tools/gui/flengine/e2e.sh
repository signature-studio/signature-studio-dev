#!/usr/bin/env bash
# GUI-3 (#174) 1 コマンド e2e: 実 FLEngine の lift (m11 closure) に tools/gui shim を結合して実行し、判定する。
#   bash tools/gui/flengine/e2e.sh
# 終了コード: 0 = 全 gate PASS かつ全ネガティブコントロールが期待どおり FAIL / 1 = gate FAIL またはネガコンが FAIL しなかった / 2 = 前提欠如。
# 前提: tools/m11/work/ (work-m11 素材 + gen_ir2 済み IR)・emsdk・node・python3 (+ x86_64-w64-mingw32-gcc: tools/gui/gen_api.py の arity 表)。
#   FL_WIN64_DIR は gen_ir2 の ldfix にだけ必要 (本スクリプトは IR を再生成しない)。PATH は env.sh の GF_EXTRA_PATH で足せる。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; source "$HERE/env.sh"
W="$GF_W"; M="$GF_M11"; R="$HERE/results"; mkdir -p "$W/res" "$R"
S() { echo "[gf_e2e] $*"; }
t0=$(date +%s); S "start load=$(cut -d' ' -f1-3 /proc/loadavg) nproc=$(nproc)"
for f in boot_final.ll boot_final3.ll m11_image.bin; do [ -f "$M/work/$f" ] || { S "前提欠如: tools/m11/work/$f (work-m11 素材 + m11_gen_ir2.sh)"; exit 2; }; done
[ -f "${FL_WIN64_DIR:-/nonexistent}/extracted/block00031_PE.bin" ] || { S "前提欠如: FL_WIN64_DIR/extracted/block00031_PE.bin (import thunk 表)"; exit 2; }
command -v x86_64-w64-mingw32-gcc >/dev/null || { S "前提欠如: x86_64-w64-mingw32-gcc (gen_api.py の arity 表)"; exit 2; }

S "0/6 baseline (GUI shim 無し, 同一 IR): m11_build.sh → m11_run.mjs / m11_survey.mjs"
( cd "$M" && bash m11_build.sh > "$W/res/m11_build.log" 2>&1 ) || { S "m11_build.sh 失敗"; tail -5 "$W/res/m11_build.log"; exit 2; }
( cd "$M" && node m11_run.mjs 2>/dev/null | sed -n 's/^M11_RESULT //p' > "$W/res/baseline_boot.json" && node m11_survey.mjs 2>/dev/null | sed -n 's/^M11_SURVEY //p' > "$W/res/baseline_survey.json" )
[ -s "$W/res/baseline_boot.json" ] && [ -s "$W/res/baseline_survey.json" ] || { S "baseline 取得失敗"; exit 2; }

S "1/6 build: ff (fail-fast 例外) / soft (STUB は 0 返却) / plain (到達ログ無し = ネガコン用)"
bash "$HERE/build.sh"          > "$W/res/build_ff.log"    2>&1 || { S "build ff 失敗"; tail -5 "$W/res/build_ff.log"; exit 1; }
bash "$HERE/build.sh" --soft   > "$W/res/build_soft.log"  2>&1 || { S "build soft 失敗"; tail -5 "$W/res/build_soft.log"; exit 1; }
bash "$HERE/build.sh" --plain  > "$W/res/build_plain.log" 2>&1 || { S "build plain 失敗"; tail -5 "$W/res/build_plain.log"; exit 1; }
tail -1 "$W/res/build_ff.log" | cut -c1-200

S "2/6 run: 通常起動 / survey(ff) / survey(soft) / 指向 probe / 通常起動(plain)"
cd "$HERE"
node run.mjs                                                  --out "$W/res/boot_ff.json"     > /dev/null
node run.mjs --survey                                         --out "$W/res/survey_ff.json"   > /dev/null
node run.mjs --survey --wasm "$W/m11_gui_soft.cjs"            --out "$W/res/survey_soft.json" > /dev/null
node probe.mjs                                                --out "$W/res/probe.json"       > /dev/null
node run.mjs --wasm "$W/m11_gui_plain.cjs"                    --out "$W/res/boot_plain.json"  > /dev/null
for f in boot_ff survey_ff survey_soft probe boot_plain baseline_boot baseline_survey; do [ -s "$W/res/$f.json" ] || { S "結果 JSON が空: $f"; exit 1; }; done

S "3/6 judge"
python3 judge.py --dir "$W/res"; rc=$?
cp "$W/res/boot_ff.json" "$R/boot.json"; cp "$W/res/survey_soft.json" "$R/survey_soft.json"; cp "$W/res/survey_ff.json" "$R/survey_ff.json"; cp "$W/res/probe.json" "$R/probe.json"
cp "$W/res/baseline_boot.json" "$R/baseline_boot.json"; cp "$W/res/baseline_survey.json" "$R/baseline_survey.json"
python3 "$GF_GUI/gen_api.py" > /dev/null    # IMPORTS.md の「実到達」列・§4 を今回の results で再生成

S "4/6 native selftest (tools/gui/test/selftest.sh)"
bash "$GF_GUI/test/selftest.sh" 2>&1 | tail -1 | tee "$W/res/selftest.txt"; grep -q ", 0 failed" "$W/res/selftest.txt" || rc=1

S "4b/6 __pe_image の data 実体化 (GUI-12 #566): 共通規則 vs m11_data_gen.py (実 FLEngine PE, LB=0/0x10000) + ネガコン"
python3 "$HERE/pe_image_parity.py" --pe "$FL_WIN64_DIR/extracted/block00031_PE.bin" --m11-data "$M/work/m11_data.c" > "$W/res/pe_image_parity.txt" 2>&1; pr=$?
grep -E "PASS|FAIL|done" "$W/res/pe_image_parity.txt"; [ $pr = 0 ] || rc=1
bash "$GF_GUI/test/pe_image_e2e.sh" > "$W/res/pe_image_e2e.txt" 2>&1; pr=$?
grep -E "PASS|FAIL|done" "$W/res/pe_image_e2e.txt"; [ $pr = 0 ] || rc=1

S "5/6 ネガティブコントロール (全て FAIL / 非 0 になることを要求)"
nc() { # nc <label> <regex that the failing output must match> <cmd...> : 非 0 かつ regex に一致 (judge のクラッシュ等を FAIL 確認と誤認しない)
  local label="$1" pat="$2"; shift 2
  "$@" > "$W/res/nc.out" 2>&1; local r=$?
  if [ $r = 0 ]; then S "NC $label: 期待に反して PASS (rc=0) → この検査は壊れても検出できない"; rc=1
  elif ! grep -Eq "$pat" "$W/res/nc.out"; then S "NC $label: 非 0 (rc=$r) だが期待した FAIL 行 /$pat/ が無い (判定器のクラッシュ?)"; tail -3 "$W/res/nc.out"; rc=1
  else S "NC $label: FAIL を確認 (rc=$r): $(grep -Eo "$pat" "$W/res/nc.out" | head -1 | cut -c1-120)"; fi; }
nc "N1 到達ログ無し (plain) ビルドの起動を boot として判定" "R1 first GUI API reaches shim \(boot\) +FAIL" python3 judge.py --dir "$W/res" --boot boot_plain.json
nc "N2 baseline と units_run が食い違う (期待値 23 を要求)" "B1 boot parity +FAIL" python3 judge.py --dir "$W/res" --expect-units 23
mkdir -p "$W/nc"; python3 -c "
import json; d=json.load(open('$R/reach_expected.json')); d['names'].append('NoSuchGuiApi'); json.dump(d, open('$W/nc/reach_expected_plus1.json','w'))"
nc "N3 到達 floor に未到達 API を 1 つ足す" "R2 survey reach floor +FAIL.*NoSuchGuiApi" python3 judge.py --dir "$W/res" --expected "$W/nc/reach_expected_plus1.json"
python3 - "$W/res" "$W/nc" <<'PY'
import json, sys
d, o = sys.argv[1:3]
s = json.load(open(d + '/survey_soft.json')); s['survey']['ok'] -= 1; s['survey']['trap'] += 1
json.dump(s, open(o + '/survey_soft_broken.json', 'w'))
PY
nc "N4 survey の 1 unit を ok→trap に壊す (parity gate)" "S1 survey parity \(soft\) +FAIL" python3 judge.py --dir "$W/res" --survey-soft "$W/nc/survey_soft_broken.json"
# N5: GetDC(NULL) を元の fail-fast に戻した shim で native selftest が落ちること (追加した回帰テストが実効)
sed 's#return (I64)gdi_get_screen_dc();.*#gui_failfast("GetDC", "screen DC (GetDC(NULL)) not implemented");#' "$GF_GUI/src/gui_core.c" > "$W/nc/gui_core.c"
grep -q 'not implemented' "$W/nc/gui_core.c" || { S "N5 準備失敗 (sed が効いていない)"; rc=1; }
nc_selftest() { ( set -e; gcc -O1 -g -w -fsanitize=address,undefined -fno-sanitize-recover=undefined -pthread -I "$GF_GUI/include" -I "$GF_GUI/src" -I "$GF_GUI/build" \
    "$GF_GUI"/src/gui_platform.c "$GF_GUI"/src/gui_reach.c "$GF_GUI"/build/gui_reach_tab.c "$W/nc/gui_core.c" "$GF_GUI"/src/gui_gdi.c "$GF_GUI"/src/gui_headless.c "$GF_GUI"/build/gui_stubs.c \
    "$GF_GUI/test/selftest.c" -o "$W/nc/selftest_old" -lm; "$W/nc/selftest_old" 2>&1 | tail -3; ); }
nc "N5 GetDC(NULL) を fail-fast に戻した shim で selftest" "FAIL-FAST: unimplemented Win32 API: GetDC" nc_selftest

S "6/6 done: $(( $(date +%s) - t0 )) s, load=$(cut -d' ' -f1-3 /proc/loadavg)  → exit $rc"
exit $rc
