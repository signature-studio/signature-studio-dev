#!/usr/bin/env bash
# CAB-96 win-stubs 検収: 1 コマンドで ビルド → ユニット(ST/MT) → baseline 差分 → リンクテスト → 起動 e2e → IR 署名突合。
#   bash tools/startup/winstubs/winstubs.sh          (exit 0 = 全 PASS)
#   FORCE=1 で work/ のオブジェクトを作り直す。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
WORK="$HERE/../work/winstubs"
mkdir -p "$WORK"
[ "${FORCE:-0}" = 1 ] && rm -rf "$WORK/obj_ST" "$WORK/obj_MT"
. "$HERE/scripts/env.sh"
B="bash $HERE/scripts/build.sh"
info() { echo "[winstubs] $*"; }

info "1/8 オブジェクトビルド (shimx 読取専用ソース + winstubs; ST/MT)"
$B objs ST; $B objs MT
info "    shimx $(ls "$WORK"/obj_ST/shimx/*.o | wc -l) obj / winstubs $(ls "$WORK"/obj_ST/ws/*.o | wc -l) obj"

info "2/8 テスト wasm のリンク (units ST/MT, baseline, probe, boot)"
python3 "$HERE/scripts/gen_probe.py" "$WORK/probe.c"
$B link ST "$WORK/units_st.cjs" wrap "$HERE/test/ws_cases.c"
$B link MT "$WORK/units_mt.cjs" wrap "$HERE/test/ws_cases.c"
$B link ST "$WORK/base_st.cjs" base -DWS_BASELINE "$HERE/test/ws_cases.c"
$B link ST "$WORK/probe_st.cjs" wrap "$WORK/probe.c"
$B link MT "$WORK/probe_mt.cjs" wrap "$WORK/probe.c"
$B link ST "$WORK/boot_st.cjs" wrap -sMODULARIZE=1 -sEXPORT_NAME=WsBoot -sEXPORTED_RUNTIME_METHODS=FS,callMain -sINVOKE_RUN=0 -sFORCE_FILESYSTEM=1 "$HERE/test/ws_boot.c"

info "3/8 shimx 単体リンク (winstubs 無し) の未解決シンボル収集"
rc=0; $B link ST "$WORK/probe_base.cjs" base -Wl,--error-limit=0 "$WORK/probe.c" > "$WORK/probe_base.log" 2>&1 || rc=$?
[ "$rc" -ne 0 ] || { echo "[winstubs] FAIL: shimx 単体でリンクが通ってしまった (差分が無い?)"; exit 1; }
grep -o "undefined symbol: [A-Za-z0-9_]*" "$WORK/probe_base.log" | sed 's/undefined symbol: //' | sort -u > "$WORK/probe_base.undef.txt"
info "    未解決 $(wc -l < "$WORK/probe_base.undef.txt") 本"

info "4/8 ユニット + 差分表 + リンク + 起動 e2e (node)"
node "$HERE/run_tests.mjs" "$WORK"

info "5/8 lift IR (tools/m11 boot_final2.ll) の declare 署名 × winstubs/shimx 定義の突合"
bash "$HERE/scripts/verify_sig_ir.sh" "$WORK"

info "6/8 shimx 回帰: winstubs 層 (--wrap, 未 init) を挟んでも shimx 単体テストが ST/MT で ALL PASS"
for m in ST MT; do
    $B link $m "$WORK/shimxtest_$m.cjs" wrap -I"$HERE/../../shimx/src" -I"$HERE/../../shimx/pathreg/include" "$HERE/../../shimx/pathreg/src/pathmap.c" $(ls "$HERE"/../../shimx/test/*.c)
    node "$WORK/shimxtest_$m.cjs" > "$WORK/shimxtest_$m.out" 2> "$WORK/shimxtest_$m.err" || { tail -5 "$WORK/shimxtest_$m.err"; echo "[winstubs] FAIL: shimx 回帰 $m"; exit 1; }
    grep -q "ALL PASS" "$WORK/shimxtest_$m.out" || { echo "[winstubs] FAIL: shimx 回帰 $m: ALL PASS が無い"; exit 1; }
    info "    $m: $(grep 'ALL PASS' "$WORK/shimxtest_$m.out")"
done

info "7/8 tools/gui (CAB-8) との共存: weak 定義は gui の強定義に負ける"
bash "$HERE/scripts/coexist_gui.sh" "$WORK"

info "8/8 完了: 全 PASS"
