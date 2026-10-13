#!/usr/bin/env bash
# #549 ネガティブコントロール: ソースを 1 箇所壊した複製で test/nonascii.test.ts を実行し、FAIL (= 検出) することを確認する。
#   使い方: bash analysis/neg_nonascii.sh   (h10_e2e.sh から呼ばれる。emcc 必須: shimx 既定 ACP の変異で probe を再ビルドする)
#   終了コード: 全変異を検出 = 0 / 検出漏れ・変異が当たらない (sed が無変更) = 1
set -euo pipefail
cd "$(dirname "$0")/.."
H10="$PWD"
TOOLS="$(cd ../.. && pwd)"
NEG="$H10/work/neg"
set +u; . /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; set -u
command -v emcc >/dev/null || { echo "FAIL: emcc not found (toolchain-emsdk)"; exit 1; }
# shellcheck disable=SC1091
source "$TOOLS/shimx/flags.sh"

fresh() {  # 作業複製 (tools/ と同じ相対構造: テストの相対 import がそのまま通る)
  rm -rf "$NEG"; mkdir -p "$NEG/tools/hostbridge/h10" "$NEG/tools/hostbridge/nfo" "$NEG/tools/flp" "$NEG/tools/shimx"
  cp -r "$H10/src" "$H10/test" "$H10/analysis" "$NEG/tools/hostbridge/h10/"
  cp -r "$TOOLS/hostbridge/nfo/src" "$NEG/tools/hostbridge/nfo/"
  cp -r "$TOOLS/flp/src" "$NEG/tools/flp/"
  cp -r "$TOOLS/shimx/src" "$TOOLS/shimx/flags.sh" "$NEG/tools/shimx/"
  mkdir -p "$NEG/tools/hostbridge/h10/work"
}
probe_build() {  # $1 = 出力 .cjs
  ( cd "$NEG/tools/hostbridge/h10"
    emcc "${SHIMX_CLANG_FLAGS[@]}" "${SHIMX_EMCC_ST[@]}" ../../shimx/src/*.c analysis/shimx_acp_probe.c -o work/p.js
    mv work/p.js work/shimx_acp_probe.cjs )
}
fail=0
mutate() {  # $1 = 名前  $2 = 対象 (NEG からの相対)  $3 = sed 式  $4 = 期待: 失敗するはずのテスト名の部分文字列
  local name="$1" file="$NEG/$2" expr="$3" want="$4"
  fresh
  cp "$file" "$file.orig"; sed -i "$expr" "$file"
  if cmp -s "$file" "$file.orig"; then echo "FAIL  $name: sed が当たっていない (変異なし)"; fail=1; return; fi
  rm -f "$file.orig"
  probe_build
  local out; out="$(cd "$NEG/tools/hostbridge/h10" && node --test test/nonascii.test.ts 2>&1 || true)"
  if echo "$out" | grep -q "^not ok .*$want"; then
    echo "detected  $name  (failed: $(echo "$out" | grep -c '^not ok') test(s), expected '$want' among them)"
  else
    echo "NOT DETECTED  $name"; fail=1
  fi
}
# 対照: 無変異の複製は PASS すること (複製自体が正しいことの確認 = 「何を壊しても FAIL」を防ぐ)
fresh; probe_build
if (cd "$NEG/tools/hostbridge/h10" && node --test test/nonascii.test.ts >/dev/null 2>&1); then echo "control   unmutated copy: PASS"; else echo "FAIL  control: unmutated copy does not pass"; fail=1; fi

mutate gen-ascii-guard-removed   tools/hostbridge/nfo/src/fst.ts        's/if (version < 9 \&\& /if (false \&\& /'  'version 8 generator'
mutate gen-version-range-open    tools/hostbridge/nfo/src/fst.ts        's/version > MAX_GEN_VERSION/version > 99/' 'generator rejects versions'
mutate gen-utf8-as-latin1        tools/hostbridge/nfo/src/fst.ts        's/return te.encode(s);\r\?$/return Uint8Array.from(s, (c) => c.charCodeAt(0) \& 255);/' 'version 9..12 generator'
mutate reader-v9-not-utf8        tools/hostbridge/h10/src/wrapper_reader.ts 's/version > 8 ? .utf8. : .ansi./version > 12 ? '"'utf8'"' : '"'ansi'"'/' 'version 9..12 generator'
mutate reader-ignores-acp        tools/hostbridge/h10/src/wrapper_reader.ts "s/enc === 'utf8' ? 'utf-8' : acp/enc === 'utf8' ? 'utf-8' : 'windows-1252'/" 'version 8 + CP932'
mutate shimx-default-acp-932     tools/shimx/src/str.c                   's/static UINT g_acp = 1252;/static UINT g_acp = 932;/' 'shimx CP_ACP default'
mutate shimx-cp932-not-applied   tools/shimx/src/str.c                   's/^void shimx_set_acp(UINT cp) { g_acp = cp; }/void shimx_set_acp(UINT cp) { (void)cp; }/' 'shimx CP_ACP default'

rm -rf "$NEG"
[ "$fail" = 0 ] && echo "neg_nonascii: 7/7 detected + control PASS" || echo "neg_nonascii: FAILED"
exit "$fail"
