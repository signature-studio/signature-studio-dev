#!/usr/bin/env bash
# M4 shim core 単体テスト (node 上で完結, exit 0 が成功基準)。
#
# 検証内容 (strategy.md M4 検証条件に対応):
#   1. Shim API (timer/file/sync/heap) を wasm (node + pthread) 上で
#      unit test 実行 → ALL PASS (exit 0)
#   2. 未対応 API は fail-fast (即 abort + stderr 関数名) を確認
#   3. シングルスレッドビルドも smoke (timer/file/heap/event/cs-recur/tls)
#
# 使い方:  bash tools/shim/test.sh
set -euo pipefail

HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
BUILD="$HERE/build"
SRC="$HERE/src"
TEST="$HERE/test"

info()  { echo "[M4-shim] $*"; }
die()   { echo "[M4-shim] FAIL: $*" >&2; exit 1; }
trap 'rc=$?; echo "[M4-shim] FAILED: 実行中断 (exit=$rc)" >&2' ERR

# ---------------------------------------------------------------
# 0/5 環境確認と emsdk 有効化
# ---------------------------------------------------------------
info "0/5 環境確認"
EMSDK="${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}"
if [ -f "$EMSDK" ]; then
    set +u
    # shellcheck disable=SC1090
    . "$EMSDK" >/dev/null 2>&1 || true
    set -u
fi
command -v emcc >/dev/null || die "emcc が見つかりません (emsdk env を再確認)"
command -v node >/dev/null || die "node が見つかりません"

mkdir -p "$BUILD"
SHIM_DIR="$HERE"
# 注意: 本リポジトリは package.json "type":"module" のため emcc glue (CommonJS)
# の node 実行には .cjs 拡張子が必要 (m1 と同対策)。

# ---------------------------------------------------------------
# 1/5 exports list 準備 (= exports.txt + _main)
#   (リンケージが exports.txt 内の typo / 未定義義務を自動検出する)
# ---------------------------------------------------------------
info "1/5 run exports (exports.txt + _main) 生成"
# 注意: emcc 6 の EXPORTED_FUNCTIONS は `_` 付きシンボル名を要求
# (wasm 側 export 名は `_` 無しで生成される)。exports.txt は値無し ID で
# 管理し、ここで `_` を付けてリンカに渡す。
awk '{ if ($0 != "" && substr($0,1,1) != "#") print "_" $0 }' "$HERE/exports.txt" > "$BUILD/run_exports.txt"
echo "_main" >> "$BUILD/run_exports.txt"

EXPORT_COUNT="$(grep -cv '^#' "$HERE/exports.txt" || true)"
EXPORT_COUNT="${EXPORT_COUNT//[!0-9]/}"
RUN_COUNT="$(wc -l < "$BUILD/run_exports.txt")"
[ "$RUN_COUNT" -eq $((EXPORT_COUNT + 1)) ] || die "run_exports 生成の行数整合が取れない"

# 定型フラグ読み込み (flags.sh が SHIM_RUN_EXPORTS を参照するため後)
export SHIM_RUN_EXPORTS="$BUILD/run_exports.txt"
source "$HERE/flags.sh"

# バージョン記録 (m1 の流儀)
EMCC_VER="$(emcc --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
NODE_VER="$(node --version)"
{
    echo "emcc  : $EMCC_VER"
    echo "node  : $NODE_VER"
    echo "date  : $(date -Is)"
} > "$BUILD/versions.txt"

# ---------------------------------------------------------------
# 2/5 MT (pthread) ビルド + unit test 実行
# ---------------------------------------------------------------
info "2/5 MT (pthread) ビルド + node 実行"
emcc "${SHIM_CLANG_FLAGS[@]}" "${SHIM_EMCC_MT[@]}" \
    "$SRC"/*.c "$TEST/test_main.c" \
    -o "$BUILD/shim_test_mt.js" \
    || die "emcc MT ビルドに失敗"
mv "$BUILD/shim_test_mt.js" "$BUILD/shim_test_mt.cjs"
[ -f "$BUILD/shim_test_mt.wasm" ] || die "MT wasm が生成されていません"

node "$BUILD/shim_test_mt.cjs" > "$BUILD/shim_test_mt.out" 2> "$BUILD/shim_test_mt.err" \
    || die "MT unit test 失敗 (build/shim_test_mt.err 参照)"
grep -q "ALL PASS" "$BUILD/shim_test_mt.out" \
    || die "MT 実行は通ったが ALL PASS が出力されていない"
info "2/5 MT unit test PASS"

# ---------------------------------------------------------------
# 3/5 ST (シングルスレッド) smoke
# ---------------------------------------------------------------
info "3/5 ST (シングルスレッド) smoke ビルド + node 実行"
emcc "${SHIM_CLANG_FLAGS[@]}" "${SHIM_EMCC_ST[@]}" \
    "$SRC"/*.c "$TEST/test_main.c" \
    -o "$BUILD/shim_test_st.js" \
    || die "emcc ST ビルドに失敗"
mv "$BUILD/shim_test_st.js" "$BUILD/shim_test_st.cjs"

node "$BUILD/shim_test_st.cjs" > "$BUILD/shim_test_st.out" 2> "$BUILD/shim_test_st.err" \
    || die "ST smoke test 失敗 (build/shim_test_st.err 参照)"
grep -q "ALL PASS" "$BUILD/shim_test_st.out" \
    || die "ST 実行は通ったが ALL PASS が出力されていない"
grep -q "pthread tests skipped" "$BUILD/shim_test_st.out" \
    || die "ST ビルドなのに pthread tests が skip されていない (マクロ不整合)"
info "3/5 ST smoke PASS"

# ---------------------------------------------------------------
# 4/5 fail-fast: 未対応 API は即 abort + 関数名を stderr に出す
# ---------------------------------------------------------------
info "4/5 fail-fast 確認 (未対応 API → abort + 関数名)"
emcc "${SHIM_CLANG_FLAGS[@]}" "${SHIM_EMCC_ST[@]}" \
    "$SRC"/*.c "$TEST/test_failraise.c" \
    -o "$BUILD/shim_failraise.js" \
    || die "emcc fail-fast ビルドに失敗"
mv "$BUILD/shim_failraise.js" "$BUILD/shim_failraise.cjs"

rc=0
# shellcheck disable=SC2015
node "$BUILD/shim_failraise.cjs" > "$BUILD/shim_failraise.out" 2> "$BUILD/shim_failraise.err" || rc=$?
[ "$rc" -ne 0 ] || die "fail-fast が abort しなかった (exit 0 で正常終了した)"
grep -q "FAIL-FAST: unimplemented Win32 API: DestroyWindow_NonImplemented_Example" \
    "$BUILD/shim_failraise.err" \
    || die "fail-fast に関数名が出力されていない (build/shim_failraise.err 参照)"
info "4/5 fail-fast PASS (exit=$rc, stderr に関数名)"

# ---------------------------------------------------------------
# 5/5 まとめ
# ---------------------------------------------------------------
N_API="$(grep -c -v '^#' "$HERE/exports.txt" || true)"
info "5/5 完了: shim $N_API API × MT/ST ビルド × node 実行 全 PASS"
info "成果物: $BUILD (gitignored)"
exit 0
