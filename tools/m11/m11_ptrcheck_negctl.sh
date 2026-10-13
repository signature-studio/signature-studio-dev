#!/usr/bin/env bash
# m11_ptrcheck.mjs のネガティブコントロール (#1004 / #403 受入 3).
# クリーン実行と M11_PTRCHECK_INJECT=<offset> 実行 (既知の未 remap 値 0x400000 を 1 語書く) の
# image_va_words_new の差が +1 になることを確認する。検出器の欠落・実行失敗・差が +1 以外は非 0 で終わる。
# 既定 offset は REPORT_N1004.md の実測で使った 22519877 (検出側が >>>2 で word 化する)。
set -u
cd "$(dirname "$0")"
OFF="${1:-22519877}"
command -v node >/dev/null || { echo "NEGCTL FAIL: node が無い"; exit 1; }
[ -f work/m11_boot.cjs.wasm ] && [ -f work/m11_image.bin ] || { echo "NEGCTL FAIL: work/ に wasm/image が無い (素材 work-m11 未展開)"; exit 1; }

get() {
  env "$@" timeout 120 node m11_run.mjs 2>/dev/null | sed -n 's/^M11_RESULT //p' \
    | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{const r=JSON.parse(s);process.stdout.write(String(r.ptrcheck.image_va_words_new))})'
}

clean=$(get M11_PTRCHECK_INJECT=) || { echo "NEGCTL FAIL: クリーン実行が失敗"; exit 1; }
inj=$(get M11_PTRCHECK_INJECT="$OFF") || { echo "NEGCTL FAIL: 注入実行が失敗"; exit 1; }
diff=$(( inj - clean ))
echo "clean=$clean injected(offset=$OFF)=$inj diff=$diff"
if [ "$diff" -ne 1 ]; then
  echo "NEGCTL FAIL: 差が +1 ではない (diff=$diff)"
  exit 1
fi
echo "NEGCTL OK: 注入で image_va_words_new が +1"
