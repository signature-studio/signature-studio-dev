#!/usr/bin/env bash
# m11_ptrcheck.mjs のネガティブコントロール (#1004 / #403 受入 3, #2778 ゲート).
#  (a) クリーン実行と M11_PTRCHECK_INJECT=<offset> 実行 (既知の未 remap 値 0x400000 を 1 語書く) の
#      image_va_words_new の差が +1 になること。
#  (b) ゲート (M11_PTRCHECK_MAX_NEW=<基準>): 基準 = クリーンの実測値なら exit 0, 注入すると exit 1 かつ FAIL 行。
#      ゲート未設定は注入でも exit 0 (情報出力のみ)。非整数の基準は exit 1 (fail-closed)。
# 検出器の欠落・実行失敗・上の期待と違う結果は非 0 で終わる。
# 既定 offset は REPORT_N1004.md の実測で使った 22519877 (検出側が >>>2 で word 化する)。
# --survey: 同じ検査を survey (m11_survey.mjs, 基準 M11_PTRCHECK_SURVEY_MAX_NEW) に対して行う (1 回約 16 s)。
set -u
cd "$(dirname "$0")"
SCRIPT=m11_run.mjs; TAG=M11_RESULT; MAXVAR=M11_PTRCHECK_MAX_NEW
if [ "${1:-}" = --survey ]; then SCRIPT=m11_survey.mjs; TAG=M11_SURVEY; MAXVAR=M11_PTRCHECK_SURVEY_MAX_NEW; shift; fi
OFF="${1:-22519877}"
command -v node >/dev/null || { echo "NEGCTL FAIL: node が無い"; exit 1; }
[ -f work/m11_boot.cjs.wasm ] && [ -f work/m11_image.bin ] || { echo "NEGCTL FAIL: work/ に wasm/image が無い (素材 work-m11 未展開)"; exit 1; }
OUT=$(mktemp); ERR=$(mktemp)
trap 'rm -f "$OUT" "$ERR"' EXIT
fail() { echo "NEGCTL FAIL: $*"; exit 1; }

# run <env 指定...>: $SCRIPT を実行し, NEW (image_va_words_new)・RC (終了コード) を設定する。stderr は $ERR
run() {
  env "$@" timeout 120 node "$SCRIPT" > "$OUT" 2> "$ERR"; RC=$?
  NEW=$(sed -n "s/^$TAG //p" "$OUT" | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{const r=JSON.parse(s);process.stdout.write(String(r.ptrcheck.image_va_words_new))})' 2>/dev/null)
  [ -n "$NEW" ]
}

run M11_PTRCHECK_INJECT= || fail "クリーン実行が失敗"
clean=$NEW
run M11_PTRCHECK_INJECT= "$MAXVAR=$clean" || fail "クリーン実行 (基準付き) が失敗"
[ "$RC" -eq 0 ] || fail "基準 = クリーン実測値 で不合格になった (rc=$RC)"
run M11_PTRCHECK_INJECT="$OFF" || fail "注入実行が失敗"
[ "$RC" -eq 0 ] || fail "ゲート未設定の注入で非 0 になった (情報出力のみのはず, rc=$RC)"
inj=$NEW
run M11_PTRCHECK_INJECT="$OFF" "$MAXVAR=$clean" || fail "注入実行 (基準付き) が失敗"
[ "$RC" -eq 1 ] || fail "注入 + 基準 で exit 1 にならない (rc=$RC)"
grep -qE 'FAIL: (survey )?ptrcheck image_va_words_new=' "$ERR" || fail "FAIL 行が stderr に無い"
run M11_PTRCHECK_INJECT= "$MAXVAR=abc" || fail "非整数基準の実行が失敗"
[ "$RC" -eq 1 ] || fail "非整数の基準が不合格にならない (rc=$RC)"
diff=$(( inj - clean ))
echo "clean=$clean injected(offset=$OFF)=$inj diff=$diff"
[ "$diff" -eq 1 ] || fail "差が +1 ではない (diff=$diff)"
echo "NEGCTL OK: 注入で image_va_words_new が +1、基準 = クリーン実測で exit 0、注入で exit 1 + FAIL 行、未設定は exit 0、非整数は exit 1"
