#!/usr/bin/env bash
# shimx (Win32/CRT shim 拡張) 単体テスト: node 上で完結し exit 0 が成功基準。
#
# 検証内容:
#   1. 全ソースのビルド (MT) → 生成物更新 (proctable.c / shimx_stubs.h / exports.txt)
#   2. MT(pthread) ビルドで全グループ PASS (core: ハンドル/待機/スレッド/ロック/TLS/FLS/タイマ, sys: 文字列/レジストリ/
#      ファイル/時刻/heap/モジュール/環境/SEH/UI言語, ole/shell: BSTR/VARIANT/SAFEARRAY/IStream/shell32/version,
#      absent: pathreg 写像経由の不在パス属性/検索エラーコード (#658))
#   3. ST(単一スレッド) ビルドで同テストが PASS (スレッド系は skip)
#   4. fail-fast: 未対応 API / 未処理 RaiseException / RtlUnwind / strict GetProcAddress / ST の INFINITE 待ち → 非 0 終了 + 名前出力。
#      ExitProcess(7) → 終了コード 7。strict SysFreeString(管理外 BSTR) / EnterCriticalSection(NULL) も fail-fast
#   5. M4 互換: tools/shim/test/test_main.c (無改変) を shimx 実装に対して MT/ST で実行 → ALL PASS
#   6. カバレッジ: inventory/BACKLOG 再生成。担当範囲の未実装 0 / M4 53 API 継承 53 を検査
#   6b. lift IR (M11 init closure / OTT) の declare を sig_normalize.py で shimx 署名へ正規化 → wasm 署名一致 (signature mismatch 0)
#       + test/sig/sig_test.sh (合成 fixture: 検出・正規化・adapter 実行・未対応型の fail・sigs.json 乖離検出・符号不明の拡張は unresolved/sext 明示で -1 保存)
#   6c. R6 検査: ir_undef.py の構造体展開 + 重複 declare 正規化 (--normalize-dup 産物が emcc 通過) を M11 IR で実測
#   7. OTT undefined 47 種 → shimx リンクで Win/CRT API 24 種が全て解決 (tools/m8 成果物があれば)
#
# 使い方:  bash tools/shimx/test.sh        (--quick で 7 を省略)
set -euo pipefail

HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
BUILD="$HERE/build"
QUICK=0; [ "${1:-}" = "--quick" ] && QUICK=1

info() { echo "[shimx] $*"; }
die()  { echo "[shimx] FAIL: $*" >&2; exit 1; }
trap 'rc=$?; [ $rc -ne 0 ] && echo "[shimx] FAILED: 実行中断 (exit=$rc)" >&2' EXIT

info "0/7 環境確認"
set +u; . /opt/emsdk/emsdk_env.sh >/dev/null 2>&1 || true; set -u
command -v emcc >/dev/null || die "emcc が見つかりません"
command -v node >/dev/null || die "node が見つかりません"
command -v llvm-nm >/dev/null || die "llvm-nm が見つかりません"
mkdir -p "$BUILD" "$HERE/work"
source "$HERE/flags.sh"
PR_INC=(-I"$HERE/src" -I"$HERE/pathreg/include")   # test_absent.c / pathmap.c (VFS 写像 pathreg) 用
{ echo "emcc : $(emcc --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"; echo "node : $(node --version)"; echo "date : $(date -Is)"; } > "$BUILD/versions.txt"

info "1/7 オブジェクトビルド + 生成物更新 (proctable / stub prototypes / exports.txt)"
bash "$HERE/scripts/build_objs.sh" MT >/dev/null
python3 "$HERE/scripts/gen_stub_protos.py" --nm "$HERE/work/nm_MT.txt" >/dev/null
bash "$HERE/scripts/build_objs.sh" MT | tail -1       # 2 周目: 更新済みヘッダで再ビルド (proctable も再生成)
{
    echo "# shimx 公開関数一覧 (自動生成: test.sh)。emcc -sEXPORTED_FUNCTIONS=@exports.txt 用には '_' 前置が必要 (test.sh 参照)"
    llvm-nm --defined-only -g "$HERE/work/obj_MT"/*.o | awk '$2=="T"||$2=="W"{print $3}' | grep -v '^shx_' | sort -u
} > "$HERE/exports.txt"
N_EXPORT="$(grep -vc '^#' "$HERE/exports.txt")"
info "    公開関数 $N_EXPORT 本 (うち shimx_* 運用フック $(grep -c '^shimx_' "$HERE/exports.txt"))"

info "2/7 MT (pthread) ビルド + node 実行"
emcc "${SHIMX_CLANG_FLAGS[@]}" "${SHIMX_EMCC_MT[@]}" "${PR_INC[@]}" "$HERE"/src/*.c "$HERE"/test/*.c "$HERE"/pathreg/src/pathmap.c -o "$BUILD/shimx_test_mt.js" || die "emcc MT ビルド失敗"
mv "$BUILD/shimx_test_mt.js" "$BUILD/shimx_test_mt.cjs"
node "$BUILD/shimx_test_mt.cjs" > "$BUILD/mt.out" 2> "$BUILD/mt.err" || { tail -5 "$BUILD/mt.err" >&2; die "MT テスト失敗 (build/mt.err)"; }
grep -q "ALL PASS (build=mt(pthreads))" "$BUILD/mt.out" || die "MT: ALL PASS が出力されていない"
info "    MT PASS ($(grep -c 'OK' "$BUILD/mt.err") グループ)"

info "3/7 ST (シングルスレッド) ビルド + node 実行"
emcc "${SHIMX_CLANG_FLAGS[@]}" "${SHIMX_EMCC_ST[@]}" "${PR_INC[@]}" "$HERE"/src/*.c "$HERE"/test/*.c "$HERE"/pathreg/src/pathmap.c -o "$BUILD/shimx_test_st.js" || die "emcc ST ビルド失敗"
mv "$BUILD/shimx_test_st.js" "$BUILD/shimx_test_st.cjs"
node "$BUILD/shimx_test_st.cjs" > "$BUILD/st.out" 2> "$BUILD/st.err" || { tail -5 "$BUILD/st.err" >&2; die "ST テスト失敗 (build/st.err)"; }
grep -q "ALL PASS (build=st)" "$BUILD/st.out" || die "ST: ALL PASS が出力されていない"
info "    ST PASS"

info "4/7 fail-fast 確認 (未対応 → 名前を出して非 0 終了)"
expect_fail() {  # $1=mode $2=stderr に含むべき文字列
    local rc=0
    node "$BUILD/shimx_test_st.cjs" "$1" > "$BUILD/ff_$1.out" 2> "$BUILD/ff_$1.err" || rc=$?
    [ "$rc" -ne 0 ] || die "fail-fast($1) が abort しなかった"
    grep -q "FAIL-FAST: unimplemented Win32 API: $2" "$BUILD/ff_$1.err" || die "fail-fast($1) に '$2' が出力されていない"
    info "    $1: exit=$rc ✓ ($2)"
}
expect_fail unimpl "DestroyWindow_NonImplemented_Example"
expect_fail raise "RaiseException (code=0xE06D7363"
expect_fail rtlunwind "RtlUnwind"
expect_fail sehnomatch "RaiseException (code=0xE0000003"
expect_fail sehbadtarget "RtlUnwindEx"
expect_fail strict "GetProcAddress(kernel32.dll!NoSuchKernelApi)"
expect_fail bstrfree "SysFreeString (管理外ポインタ)"
expect_fail csnull "EnterCriticalSection (NULL/misaligned)"
expect_fail dwrite "DWriteCreateFactory (DirectWrite 未対応"
expect_fail shbrowse "SHBrowseForFolder"
expect_fail ifiledialog "CoCreateInstance(FileOpenDialog)"
expect_fail ifilesave "CoCreateInstance(FileSaveDialog)"
expect_fail deadlock "WaitFor\*Object(INFINITE)"
rc=0; node "$BUILD/shimx_test_st.cjs" exit > /dev/null 2> "$BUILD/ff_exit.err" || rc=$?
[ "$rc" -eq 7 ] || die "ExitProcess(7) の終了コードが $rc"
grep -q "exit hook code=7" "$BUILD/ff_exit.err" || die "exit hook が呼ばれていない"
info "    exit: ExitProcess(7) → exit=7 + hook ✓"

info "5/7 M4 互換 (tools/shim/test/test_main.c 無改変 × shimx 実装)"
M4T="$HERE/../shim/test/test_main.c"
[ -f "$M4T" ] || die "M4 テストが見つかりません ($M4T)"
M4_ST_FLAGS=(-sALLOW_MEMORY_GROWTH=1 -sERROR_ON_UNDEFINED_SYMBOLS=1 -sEXIT_RUNTIME=1 -sENVIRONMENT=node)
emcc "${SHIMX_CLANG_FLAGS[@]}" "${M4_ST_FLAGS[@]}" -pthread -sPTHREAD_POOL_SIZE=8 "$HERE"/src/*.c "$M4T" -o "$BUILD/m4compat_mt.js" || die "M4 互換 MT ビルド失敗"
mv "$BUILD/m4compat_mt.js" "$BUILD/m4compat_mt.cjs"
node "$BUILD/m4compat_mt.cjs" > "$BUILD/m4_mt.out" 2> "$BUILD/m4_mt.err" || { tail -3 "$BUILD/m4_mt.err" >&2; die "M4 互換 MT 失敗"; }
grep -q "ALL PASS (build=mt(pthreads))" "$BUILD/m4_mt.out" || die "M4 互換 MT: ALL PASS が無い"
emcc "${SHIMX_CLANG_FLAGS[@]}" "${M4_ST_FLAGS[@]}" "$HERE"/src/*.c "$M4T" -o "$BUILD/m4compat_st.js" || die "M4 互換 ST ビルド失敗"
mv "$BUILD/m4compat_st.js" "$BUILD/m4compat_st.cjs"
node "$BUILD/m4compat_st.cjs" > "$BUILD/m4_st.out" 2> "$BUILD/m4_st.err" || { tail -3 "$BUILD/m4_st.err" >&2; die "M4 互換 ST 失敗"; }
grep -q "ALL PASS" "$BUILD/m4_st.out" || die "M4 互換 ST: ALL PASS が無い"
info "    M4 テスト (MT/ST) PASS"

info "6/7 カバレッジ (inventory.md / BACKLOG.md / data/coverage.json を実測再生成)"
if [ -f "$HERE/../m11/work/boot_final2.ll" ]; then
    python3 "$HERE/scripts/ir_undef.py" "$HERE/../m11/work/boot_final2.ll" --nm "$HERE/work/nm_MT.txt" --json "$HERE/work/ir_m11.json" > "$HERE/work/ir_m11.txt"
fi
if [ -f "$HERE/../m8/work/ott_m8.ll" ]; then
    python3 "$HERE/scripts/ir_undef.py" "$HERE/../m8/work/ott_m8.ll" --nm "$HERE/work/nm_MT.txt" --json "$HERE/work/ir_ott.json" > "$HERE/work/ir_ott.txt"
fi
for pair in "m11:$HERE/../m11/work/boot_final2.ll" "m11_3:$HERE/../m11/work/boot_final3.ll" "ott:$HERE/../m8/work/ott_m8.ll"; do
    tag="${pair%%:*}"; ir="${pair#*:}"
    if [ -f "$ir" ]; then bash "$HERE/scripts/sig_gate.sh" "$ir" "$tag" | sed 's/^/    /' || die "署名不一致 ($tag): sig_normalize.py 後も lift IR の declare と shimx 定義が wasm 署名で食い違う (または未解決型)"; fi
done
# SHX-T7 (#173): 合成 fixture による署名正規化の回帰 (陰性対照・adapter 実行・sigs.json 乖離検出を含む)
bash "$HERE/test/sig/sig_test.sh" | sed 's/^/    /' || die "署名正規化テスト (test/sig/sig_test.sh) 失敗"
# R6: 構造体展開スタブ + 重複 declare 正規化 (M11 IR があれば実測)
if [ -f "$HERE/../m11/work/boot_final3.ll" ]; then
    python3 "$HERE/scripts/ir_undef.py" "$HERE/../m11/work/boot_final3.ll" --nm "$HERE/work/nm_MT.txt" \
        --emit-stubs "$HERE/work/r6_stubs.c" --normalize-dup "$HERE/work/r6_norm.ll" > "$HERE/work/r6_ir.txt" || die "ir_undef 失敗"
    grep -q "void\* WindowFromPoint(int a0, int a1)" "$HERE/work/r6_stubs.c" || die "R6: 構造体 by-value 引数が wasm32 展開されていない (WindowFromPoint)"
    NORM_N=$(grep -c "正規化" "$HERE/work/r6_ir.txt" || true)
    set +u; . /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; set -u
    emcc "$HERE/work/r6_norm.ll" -o "$HERE/work/r6_norm.js" -w -O0 -sALLOW_MEMORY_GROWTH=1 -sENVIRONMENT=node \
        -sERROR_ON_UNDEFINED_SYMBOLS=0 --no-entry -sGLOBAL_BASE=268435456 2> "$HERE/work/r6_norm.log" || { tail -5 "$HERE/work/r6_norm.log"; die "R6: 正規化 IR が emcc を通過しない"; }
    info "    R6: 構造体展開スタブ + 重複 declare 正規化 OK ($(grep -- '--normalize-dup' "$HERE/work/r6_ir.txt" | head -1 | sed 's/^ *//'))"
fi
if [ "$QUICK" -eq 0 ]; then
    bash "$HERE/scripts/verify_ott.sh" | tee "$BUILD/ott.out" | sed 's/^/    /'
    grep -q "API 解決 24 種" "$BUILD/ott.out" || [ ! -f "$HERE/../m8/work/ott_m8.ll" ] || die "OTT: Win/CRT API 24 種が解決されていない"
    grep -q "不一致" "$BUILD/ott.out" && die "OTT: t1 出力が baseline と不一致"
fi
python3 "$HERE/scripts/gen_inventory.py" > "$BUILD/coverage.out"
python3 - <<PYEOF || die "カバレッジ基準未達"
import json, sys
c = json.load(open("$HERE/data/coverage.json"))
print("    FLEngine 738: 実装 %d (機能 %d + スタブ %d) = %.1f%% / 担当範囲 %d に対し %.1f%% / 未実装 %d / 他担当 %d" % (
    c['implemented_functional'] + c['implemented_stub'], c['implemented_functional'], c['implemented_stub'], c['coverage_pct_vs_738'],
    c['in_scope'], c['coverage_pct_in_scope'], c['unimplemented'], c['other_owner']))
ok = c['unimplemented'] == 0 and c['m4_api_inherited'] == c['m4_api'] and c['delay_unimplemented'] == 0
sys.exit(0 if ok else 1)
PYEOF

info "7/7 完了: shimx $N_EXPORT 公開関数 × MT/ST × M4 互換 × fail-fast 全 PASS"
exit 0
