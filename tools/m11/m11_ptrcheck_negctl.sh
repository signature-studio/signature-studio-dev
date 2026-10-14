#!/usr/bin/env bash
# m11_ptrcheck.mjs のネガティブコントロール (#1004 / #403 受入 3, #2778 ゲート, #3113 分類 B ゲート).
#  (a) クリーン実行と M11_PTRCHECK_INJECT=<offset> 実行 (既知の未 remap 値 0x400000 を 1 語書く) の
#      image_va_words_new の差が +1 になること。
#  (b) ゲート (M11_PTRCHECK_MAX_NEW=<基準>): 基準 = クリーンの実測値なら exit 0, 注入すると exit 1 かつ FAIL 行。
#      ゲート未設定は注入でも exit 0 (情報出力のみ)。非整数の基準は exit 1 (fail-closed)。
#  (c) 分類 B (未 remap の疑い) の注入: M11_PTRCHECK_INJECT_VALUE=<IR のデータ領域 VA 定数で image のコピーでないもの (既定 0x153fb68)> を
#      同じ offset に書くと unremap_cand が +1 になること。
#  (d) 分類 B の基準 (M11_PTRCHECK_UNREMAP_MAX): 基準 = クリーンの unremap_cand なら exit 0, 注入すると exit 1 かつ FAIL 行。
#  (e) 分類ファイル欠落 (M11_PTRCLASS=<無いパス>) と基準付き → exit 1 (fail-closed)。
# 検出器の欠落・実行失敗・上の期待と違う結果は非 0 で終わる。
# 既定 offset は REPORT_N1004.md の実測で使った 22519877 (検出側が >>>2 で word 化する)。
# 分類の定数集合 work/ptrclass/classes.json は m11_ptrclass.py で作る (無ければ (c)(d) は FAIL)。
set -u
cd "$(dirname "$0")"
OFF="${1:-22519877}"
BV="${2:-0x153fb68}"
command -v node >/dev/null || { echo "NEGCTL FAIL: node が無い"; exit 1; }
[ -f work/m11_boot.cjs.wasm ] && [ -f work/m11_image.bin ] || { echo "NEGCTL FAIL: work/ に wasm/image が無い (素材 work-m11 未展開)"; exit 1; }
[ -f work/ptrclass/classes.json ] || { echo "NEGCTL FAIL: work/ptrclass/classes.json が無い (m11_ptrclass.py を先に実行)"; exit 1; }
OUT=$(mktemp); ERR=$(mktemp)
trap 'rm -f "$OUT" "$ERR"' EXIT
fail() { echo "NEGCTL FAIL: $*"; exit 1; }

# run <env 指定...>: m11_run.mjs を実行し, NEW (image_va_words_new)・BC (unremap_cand)・RC (終了コード) を設定する。stderr は $ERR
run() {
  env "$@" timeout 120 node m11_run.mjs > "$OUT" 2> "$ERR"; RC=$?
  read -r NEW BC <<< "$(sed -n 's/^M11_RESULT //p' "$OUT" | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{const r=JSON.parse(s);process.stdout.write(String(r.ptrcheck.image_va_words_new)+" "+String(r.ptrcheck.unremap.unremap_cand))})' 2>/dev/null)"
  [ -n "$NEW" ] && [ -n "$BC" ]
}

run M11_PTRCHECK_INJECT= || fail "クリーン実行が失敗"
clean=$NEW
cleanB=$BC
[ "$cleanB" != "null" ] || fail "分類ファイルを読めない (unremap_cand=null)"
run M11_PTRCHECK_INJECT= M11_PTRCHECK_MAX_NEW="$clean" || fail "クリーン実行 (基準付き) が失敗"
[ "$RC" -eq 0 ] || fail "基準 = クリーン実測値 で不合格になった (rc=$RC)"
run M11_PTRCHECK_INJECT="$OFF" || fail "注入実行が失敗"
[ "$RC" -eq 0 ] || fail "ゲート未設定の注入で非 0 になった (情報出力のみのはず, rc=$RC)"
inj=$NEW
run M11_PTRCHECK_INJECT="$OFF" M11_PTRCHECK_MAX_NEW="$clean" || fail "注入実行 (基準付き) が失敗"
[ "$RC" -eq 1 ] || fail "注入 + 基準 で exit 1 にならない (rc=$RC)"
grep -qF 'FAIL: ptrcheck image_va_words_new=' "$ERR" || fail "FAIL 行が stderr に無い"
run M11_PTRCHECK_INJECT= M11_PTRCHECK_MAX_NEW=abc || fail "非整数基準の実行が失敗"
[ "$RC" -eq 1 ] || fail "非整数の基準が不合格にならない (rc=$RC)"
diff=$(( inj - clean ))
echo "clean=$clean injected(offset=$OFF)=$inj diff=$diff"
[ "$diff" -eq 1 ] || fail "差が +1 ではない (diff=$diff)"

# (c)(d) 分類 B: 注入値 BV は IR のデータ領域 VA 定数 (クリーン実行の B 件数が +1 になる)
run M11_PTRCHECK_INJECT= || fail "クリーン実行 (分類 B) が失敗"
run M11_PTRCHECK_INJECT="$OFF" M11_PTRCHECK_INJECT_VALUE="$BV" || fail "B 注入実行が失敗"
bclean=$cleanB
binj=$BC
echo "unremap_cand clean=$bclean injected(value=$BV)=$binj"
[ "$(( binj - bclean ))" -eq 1 ] || fail "分類 B が +1 にならない (注入値 $BV がデータ領域 VA 定数でない可能性)"
run M11_PTRCHECK_INJECT= M11_PTRCHECK_UNREMAP_MAX="$bclean" || fail "クリーン実行 (分類 B 基準付き) が失敗"
[ "$RC" -eq 0 ] || fail "分類 B の基準 = クリーン実測値 で不合格になった (rc=$RC)"
run M11_PTRCHECK_INJECT="$OFF" M11_PTRCHECK_INJECT_VALUE="$BV" M11_PTRCHECK_UNREMAP_MAX="$bclean" || fail "B 注入 + 基準の実行が失敗"
[ "$RC" -eq 1 ] || fail "分類 B 注入 + 基準で exit 1 にならない (rc=$RC)"
grep -qF 'FAIL: ptrcheck unremap_cand=' "$ERR" || fail "分類 B の FAIL 行が stderr に無い"

# (e) 分類ファイル欠落は基準付きなら不合格 (fail-closed)
run M11_PTRCHECK_INJECT= M11_PTRCLASS=/nonexistent/classes.json M11_PTRCHECK_UNREMAP_MAX="$bclean" || fail "分類ファイル欠落の実行が失敗"
[ "$RC" -eq 1 ] || fail "分類ファイル欠落 + 基準で exit 1 にならない (rc=$RC)"
grep -qF 'available=false' "$ERR" || fail "分類ファイル欠落の FAIL 行が無い"
echo "NEGCTL OK: 注入で image_va_words_new が +1、基準 = クリーン実測で exit 0、注入で exit 1 + FAIL 行、未設定は exit 0、非整数は exit 1。分類 B: 注入で unremap_cand +1、基準 = クリーンで exit 0、注入で exit 1 + FAIL 行、分類ファイル欠落は exit 1"
