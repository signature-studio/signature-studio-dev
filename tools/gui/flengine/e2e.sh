#!/usr/bin/env bash
# GUI-3 (#174) 1 コマンド e2e: 実 FLEngine の lift (m11 closure) に tools/gui shim を結合して実行し、判定する。
#   bash tools/gui/flengine/e2e.sh
# 終了コード: 0 = 全 gate PASS かつ全ネガティブコントロールが期待どおり FAIL / 1 = gate FAIL またはネガコンが FAIL しなかった / 2 = 前提欠如。
# 前提: tools/m11/work/ (work-m11 素材 + gen_ir2 済み IR)・emsdk・node・python3 (+ x86_64-w64-mingw32-gcc: tools/gui/gen_api.py の arity 表)。
#   FL_WIN64_DIR は gen_ir2 の ldfix・m11_build.sh の qstore 段 (PE 突合)・WNDCLASS 走査 (m11_wndclass_scan.py: capstone+pefile) に必要。PATH は env.sh の GF_EXTRA_PATH で足せる。
#   tools/m11 は読取専用: m11_build.sh は work/ を in-place 更新するため、素材を $GF_W/tree へ複製し複製側で m11_gen_ir2.sh → baseline / build を回す。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; source "$HERE/env.sh"
W="$GF_W"; SRC="$GF_M11"; TREE="$W/tree"; R="$HERE/results"; mkdir -p "$W/res" "$R"
S() { echo "[gf_e2e] $*"; }
t0=$(date +%s); S "start load=$(cut -d' ' -f1-3 /proc/loadavg) nproc=$(nproc)"
for f in boot_final.ll boot_final3.ll m11_image.bin; do [ -f "$SRC/work/$f" ] || { S "前提欠如: tools/m11/work/$f (work-m11 素材 + m11_gen_ir2.sh)"; exit 2; }; done
[ -f "${FL_WIN64_DIR:-/nonexistent}/extracted/block00031_PE.bin" ] || { S "前提欠如: FL_WIN64_DIR/extracted/block00031_PE.bin (import thunk 表)"; exit 2; }
command -v x86_64-w64-mingw32-gcc >/dev/null || { S "前提欠如: x86_64-w64-mingw32-gcc (gen_api.py の arity 表)"; exit 2; }
command -v "${RETDEC:-retdec-decompiler}" >/dev/null || { S "前提欠如: retdec-decompiler (m11_wndseed.sh の boot6 lift。PATH か RETDEC= で指定)"; exit 2; }
python3 -c "import capstone, pefile" 2>/dev/null || { S "前提欠如: python3 の capstone / pefile (m11_wndclass_scan.py・m11_wndseed.sh)"; exit 2; }
for i in 0 1 2 3 4; do [ -f "$SRC/work/boot$i.lift.ll" ] || { S "前提欠如: tools/m11/work/boot$i.lift.ll (work-m11 素材。m11_wndseed.sh が boot0..4 を基準にする)"; exit 2; }; done
# tools/m11 は読取のみ (AGENTS §4-4): m11_build.sh は work/ を書き換えるため、work 込みで複製した検証スナップショットで以降を回す
SNAP="$W/snap"; rm -rf "$SNAP"; mkdir -p "$SNAP"
cp -a "$GF_M11" "$SNAP/m11" && cp -a "$GF_M11/../shared" "$SNAP/shared" && cp -a "$GF_M11/../shim" "$SNAP/shim" || { S "検証スナップショットの複製に失敗"; exit 2; }
export GF_M11="$SNAP/m11"; M="$GF_M11"; S "検証スナップショット: $M (元の tools/m11 は読取のみ)"

export GF_SURVEY_RESET=1   # survey の全実行 (base / ff / soft) で、各 unit を boot 直後の全メモリ状態から始める。chained 実行だと前 unit の副作用で base と soft の結果が食い違う (REPORT_APPENDIX_1635.md)
S "0/6 複製: tools/m11 + tools/shim + tools/shared → $TREE (m11_build.sh の相対参照を保つ)"
rm -rf "$TREE"; mkdir -p "$TREE"; cp -a "$SRC" "$GF_GUI/../shim" "$GF_GUI/../shared" "$GF_GUI/../m2" "$GF_GUI/../m5" "$TREE/"   # m2/m5: m11_lift.sh が ../m2/ir_normalize.py・../m5/ir5_patch.py を呼ぶ
mkdir -p "$TREE/m6" && cp -a "$GF_GUI/../m6/ottlib.py" "$TREE/m6/"   # m11_wndclass_scan.py は ../m6/ottlib.py を import する
export GF_M11="$TREE/m11"; M="$GF_M11"
# boot5 = 間接 call 先の fallback (m11_extra_ranges5.txt。0x85df70 = EnumDisplayMonitors の callback を含む)。素材 work-m11 には無いので複製側で lift する (m11_e2e.sh #132 と同じ)
[ -f "$M/work/boot5.lift.ll" ] || ( cd "$M" && bash m11_lift.sh m11_extra_ranges5.txt boot5 600 > "$W/res/m11_lift_boot5.log" 2>&1 ) || { S "boot5 lift 失敗 (m11_lift.sh。RETDEC / FL_WIN64_DIR を確認)"; tail -5 "$W/res/m11_lift_boot5.log"; exit 2; }
( cd "$M" && bash m11_gen_ir2.sh > "$W/res/m11_gen_ir2.log" 2>&1 ) || { S "m11_gen_ir2.sh 失敗 (複製側で IR 再生成。#680 の ldfix=applied 記録が必要)"; tail -5 "$W/res/m11_gen_ir2.log"; exit 2; }   # main #680: m11_build.sh は ir_conditions.json の ldfix=applied を要求する。素材の旧 IR は使えない
( cd "$M" && bash m11_wndseed.sh > "$W/res/m11_wndseed.log" 2>&1 ) || { S "m11_wndseed.sh 失敗 (boot6 lift + 最終 IR。RetDec / PE を確認)"; tail -5 "$W/res/m11_wndseed.log"; exit 2; }   # #565: WNDCLASS 静的実体の WNDPROC 閉包 (boot6) が無いと最終 IR で WNDPROC 8 件が未定義 (W1 FAIL)
[ -f "$M/work/boot6.lift.ll" ] || { S "前提欠如: boot6.lift.ll が生成されていない (m11_wndseed.sh)"; exit 2; }
tail -1 "$W/res/m11_wndseed.log" | sed 's/^/[gf_e2e] wndseed: /'
(cd "$SRC/work" && sha256sum boot_final.ll boot_final3.ll | sed 's/^/material  /') > "$R/ir_sha256.txt"   # 素材そのままの IR (provenance)
S "0/6 baseline (GUI shim 無し, 同一 IR): m11_build.sh → build.sh --base → run.mjs / run.mjs --survey (複製側)"
( cd "$M" && bash m11_build.sh > "$W/res/m11_build.log" 2>&1 ) || { S "m11_build.sh 失敗"; tail -5 "$W/res/m11_build.log"; exit 2; }
(cd "$M/work" && sha256sum boot_final.ll boot_final3.ll | sed 's/^/after_m11_build  /') >> "$R/ir_sha256.txt"   # m11_build.sh (qstore/alloca/post) 後の IR
bash "$HERE/build.sh" --base > "$W/res/build_base.log" 2>&1 || { S "build base 失敗"; tail -5 "$W/res/build_base.log"; exit 2; }   # 比較元は GUI と同じ -pthread build (shim 無し)。非 pthread の m11_boot.cjs と比べると boot は GetMem 761 対 760、survey は 8 unit ぶんの差が出る (REPORT §5-6・#4420)
( cd "$HERE" && node run.mjs --wasm "$W/m11_base.cjs" --out "$W/res/baseline_boot.json" > /dev/null )   # boot の比較元も同じ -pthread build (m11_run.mjs は非 pthread の wasm を見るため GetMem が 1 回多い)
[ -s "$W/res/baseline_boot.json" ] || { S "baseline boot 取得失敗"; exit 2; }
( cd "$HERE" && GF_SURVEY_UNITS="$W/res/baseline_units.json" node run.mjs --survey --wasm "$W/m11_base.cjs" --out "$W/res/baseline_base_survey.json" > /dev/null )
python3 -c "import json,sys; d=json.load(open(sys.argv[1]))['survey']; json.dump(d, open(sys.argv[2],'w'))" "$W/res/baseline_base_survey.json" "$W/res/baseline_survey.json" 2>/dev/null
[ -s "$W/res/baseline_survey.json" ] || { S "baseline survey 取得失敗"; exit 2; }

S "1/6 build: ff (fail-fast 例外) / soft (STUB は 0 返却) / plain (到達ログ無し = ネガコン用)"
bash "$HERE/build.sh"          > "$W/res/build_ff.log"    2>&1 || { S "build ff 失敗"; tail -5 "$W/res/build_ff.log"; exit 1; }
bash "$HERE/build.sh" --soft   > "$W/res/build_soft.log"  2>&1 || { S "build soft 失敗"; tail -5 "$W/res/build_soft.log"; exit 1; }
bash "$HERE/build.sh" --plain  > "$W/res/build_plain.log" 2>&1 || { S "build plain 失敗"; tail -5 "$W/res/build_plain.log"; exit 1; }
tail -1 "$W/res/build_ff.log" | cut -c1-200

S "2/6 run: 通常起動 / survey(ff) / survey(soft) / 指向 probe / 通常起動(plain)"
cd "$HERE"
node run.mjs                                                  --out "$W/res/boot_ff.json"     > /dev/null
node run.mjs --survey                                         --out "$W/res/survey_ff.json"   > /dev/null
GF_SURVEY_UNITS="$W/res/survey_soft_units.json" node run.mjs --survey --wasm "$W/m11_gui_soft.cjs" --out "$W/res/survey_soft.json" > /dev/null
GF_SURVEY_RESET=0 node run.mjs --survey --wasm "$W/m11_gui_soft.cjs" --out "$W/res/survey_soft_chain.json" > /dev/null   # R2 (到達 floor) は前 unit の状態を引き継ぐ従来の survey で見る (隔離版では到達が 12 件に減る)
node probe.mjs                                                --out "$W/res/probe.json"       > /dev/null
node run.mjs --wasm "$W/m11_gui_plain.cjs"                    --out "$W/res/boot_plain.json"  > /dev/null
for f in boot_ff survey_ff survey_soft survey_soft_chain probe boot_plain baseline_boot baseline_survey baseline_units survey_soft_units; do [ -s "$W/res/$f.json" ] || { S "結果 JSON が空: $f"; exit 1; }; done

S "2b/6 WNDCLASS scan (m11_wndclass_scan.py --check: fn WNDPROC は最終 IR に定義されていること)"
python3 "$M/m11_wndclass_scan.py" --pe "$FL_WIN64_DIR/extracted/block00031_PE.bin" --ir "$M/work/boot_final.ll" --json-out "$W/res/wndclass.json" --check --min-instances 11 -q > "$W/res/wndclass.out" 2>&1; tail -1 "$W/res/wndclass.out"
[ -s "$W/res/wndclass.json" ] || { S "wndclass.json が空"; exit 1; }
S "3/6 judge"
python3 judge.py --dir "$W/res"; rc=$?
cp "$W/res/boot_ff.json" "$R/boot.json"; cp "$W/res/survey_soft.json" "$R/survey_soft.json"; cp "$W/res/survey_soft_chain.json" "$R/survey_soft_chain.json"; cp "$W/res/survey_ff.json" "$R/survey_ff.json"; cp "$W/res/probe.json" "$R/probe.json"
cp "$W/res/baseline_boot.json" "$R/baseline_boot.json"; cp "$W/res/baseline_survey.json" "$R/baseline_survey.json"
cp "$W/res/baseline_units.json" "$W/res/survey_soft_units.json" "$R/"   # unit 別の出力 (judge の S3 が突き合わせる。REPORT_APPENDIX_1635.md §2-4)
python3 "$GF_GUI/gen_api.py" > /dev/null    # IMPORTS.md の「実到達」列・§4 を今回の results で再生成

S "4/6 native selftest (tools/gui/test/selftest.sh)"
bash "$GF_GUI/test/selftest.sh" 2>&1 | tail -1 | tee "$W/res/selftest.txt"; grep -q ", 0 failed" "$W/res/selftest.txt" || rc=1

S "4b/6 __pe_image の data 実体化 (GUI-12 #566): 共通規則 vs m11_data_gen.py (実 FLEngine PE, LB=0/0x10000) + ネガコン"
python3 "$HERE/pe_image_parity.py" --pe "$FL_WIN64_DIR/extracted/block00031_PE.bin" > "$W/res/pe_image_parity.txt" 2>&1; pr=$?
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

# N6: seed 導入前の IR (boot0 chunk 単体を最終 IR とみなす) で走査 → W1 FAIL (走査 --check も非 0)
nc "N6 WNDPROC が IR に無い状態の走査 (--check)" "WNDCLASS-CHECK FAIL" python3 "$M/m11_wndclass_scan.py" --pe "$FL_WIN64_DIR/extracted/block00031_PE.bin" --ir "$M/work/boot0.lift.ll" --check --min-instances 11 -q
python3 "$M/m11_wndclass_scan.py" --pe "$FL_WIN64_DIR/extracted/block00031_PE.bin" --ir "$M/work/boot0.lift.ll" --json-out "$W/nc/wndclass_noseed.json" -q
nc "N7 同 JSON を judge (W1)" "W1 WNDCLASS scan.*FAIL" python3 judge.py --dir "$W/res" --wndscan "$W/nc/wndclass_noseed.json"
# N8: 走査の空振り (検出 floor 12 > 実 11) を --check が拒否する
nc "N8 検出件数 floor を実測 +1 に" "WNDCLASS-CHECK FAIL.*floor" python3 "$M/m11_wndclass_scan.py" --pe "$FL_WIN64_DIR/extracted/block00031_PE.bin" --ir "$M/work/boot_final.ll" --check --min-instances 12 -q
# N9: P5 (TLightweightLayeredControl の窓) が NULL に戻った probe を judge
python3 - "$W/res" "$W/nc" <<'PY'
import json, sys
d, o = sys.argv[1:3]
p = json.load(open(d + '/probe.json'))
for w in p['windows']:
    if w['name'] == 'TLightweightLayeredControl': w['hwnd'] = '0x0'
json.dump(p, open(o + '/probe_null_window.json', 'w'))
PY
nc "N9 TLightweightLayeredControl の hwnd が NULL (seed 無し相当)" "P5 TLightweightLayeredControl.*FAIL" python3 judge.py --dir "$W/res" --probe "$W/nc/probe_null_window.json"
# N10: soft の unit 別出力の 1 unit を ok→trap に壊す (S1 の totals は変わらず、unit 単位の S3 だけが落ちること)
python3 - "$W/res" "$W/nc" <<'PY'
import json, sys
d, o = sys.argv[1:3]
u = json.load(open(d + '/survey_soft_units.json'))
k = next(j for j, e in enumerate(u) if e[1] == 'ok')
u[k] = [u[k][0], 'trap', 'NC-flipped']
json.dump(u, open(o + '/survey_soft_units_broken.json', 'w'))
PY
nc "N10 soft の 1 unit (ok→trap) の unit 別出力 (S3 unit parity)" "S3 unit parity \(soft vs base\) +FAIL" python3 judge.py --dir "$W/res" --soft-units "$W/nc/survey_soft_units_broken.json"

S "6/6 done: $(( $(date +%s) - t0 )) s, load=$(cut -d' ' -f1-3 /proc/loadavg)  → exit $rc"
exit $rc
