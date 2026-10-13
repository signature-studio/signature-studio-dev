#!/usr/bin/env bash
# PY-13 (#588): build_flpy.sh 経由の flapi_table 再生成が環境変数入力だけで再現し、入力欠落では非 0 で止まることの検証。
#   FL_WIN64_DIR=<fl-win64 展開先> bash tools/python/tests/flapi_table_check.sh
# 出力先は一時ディレクトリ (FLAPI_OUT_DIR)。追跡中の analysis/flapi/ は書き換えない。
# 判定: 正常系 (再生成物 3 ファイルが追跡中のものとバイト一致) と、ネガコン 6 本 (全て exit 非 0 + 理由表示) の全てが成立で exit 0。
set -uo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$HERE/../shared/env.sh"
SRC="$HERE/analysis/flapi"
T="$(mktemp -d "${TMPDIR:-/tmp}/flapi_check.XXXXXX")"; trap 'rm -rf "$T"' EXIT
STUBS="${FL_STUBS_DIR:-$HERE/work/fl-stubs}"
PE="${FL_WIN_PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}"
fail=0
ok()  { printf 'PASS  %s\n' "$*"; }
bad() { printf 'FAIL  %s\n' "$*"; fail=$((fail + 1)); }

fresh_out() { rm -rf "$T/out"; mkdir -p "$T/out"; cp "$SRC"/* "$T/out/"; }
run() { FLPY_TABLE_ONLY=1 FLAPI_OUT_DIR="$T/out" "$@" bash "$HERE/build_flpy.sh" >"$T/log" 2>&1; }

# 前提: 実入力があること (無ければ NOT VERIFIED で非 0)
[ -s "$PE" ]                          || { echo "NOT VERIFIED: win PE が無い: $PE (FL_WIN64_DIR / oc_artifacts: fl-win64)"; exit 3; }
[ -f "$STUBS/data/fl_stubs.json" ]    || { echo "NOT VERIFIED: stubs が無い: $STUBS (bash fetch_inputs.sh)"; exit 3; }

# 1. 正常系: 追跡中の 3 ファイルを一時出力先で再生成し、バイト一致
fresh_out; rm -f "$T/out/flapi_table.json" "$T/out/FLAPI.md" "$T/out/flapi_ids.json"
cp "$SRC/flapi_table.json" "$T/out/flapi_table.json"   # mac dylib が無い環境では callbacks_in_binary をここから引き継ぐ
if run env; then
  m=0; for f in flapi_table.json flapi_ids.json FLAPI.md; do cmp -s "$SRC/$f" "$T/out/$f" || { m=$((m + 1)); echo "  差分: $f"; }; done
  [ $m -eq 0 ] && ok "正常系: 再生成 3 ファイルが追跡中と一致 (差分 $m / 3)" || bad "正常系: $m / 3 ファイルが追跡中と不一致"
else bad "正常系: exit 非 0"; sed 's/^/  | /' "$T/log"; fi
n_ok=$(python3 -c "import json;d=json.load(open('$T/out/flapi_table.json'));print(sum(1 for m in d['modules'].values() for e in m.values() if e['win_pair_verified']))")
echo "      win_pair_verified=true: $n_ok 件 (win PE を読めた証拠。PE 無しなら 0)"
[ "$n_ok" -gt 0 ] && ok "win PE が実際に照合に使われた ($n_ok > 0)" || bad "win_pair_verified が 0 件"

# ネガコン: 入力を 1 つ壊すと exit 非 0 + 理由 (stderr) + 出力先を書き換えない
neg() {  # neg <名前> <期待する理由の部分文字列> <env 代入>...
  local name="$1" want="$2"; shift 2
  fresh_out; local before; before="$(cat "$T/out"/* | md5sum)"
  run env "$@"; local rc=$?
  local after; after="$(cat "$T/out"/* | md5sum)"
  if [ $rc -ne 0 ] && grep -q -- "$want" "$T/log" && [ "$before" = "$after" ]; then
    ok "ネガコン[$name]: exit=$rc・理由に '$want'・出力不変"
  else
    bad "ネガコン[$name]: exit=$rc (非 0 が期待)・理由一致=$(grep -c -- "$want" "$T/log")・出力不変=$([ "$before" = "$after" ] && echo y || echo n)"; sed 's/^/  | /' "$T/log"
  fi
}
: > "$T/empty.bin"
neg "win PE 無し"       "win PE が無い"   FL_WIN_PE="$T/nonexistent.bin"
neg "win PE 空ファイル" "win PE が無い"   FL_WIN_PE="$T/empty.bin"
head -c 1000000 /dev/zero | tr '\0' 'x' > "$T/junk.bin"
neg "win PE が別物 (照合 0 件)" "1 件も一致しない" FL_WIN_PE="$T/junk.bin"
neg "stubs 無し"        "stubs が無い"    FL_STUBS_DIR="$T/nonexistent"
neg "emsdk 無し (link 段)" "emsdk が無い" EMSDK_DIR="$T/nonexistent" FLPY_TABLE_ONLY=0
# 引き継ぎ元も dylib も無い → callbacks_in_binary を捏造せず失敗
fresh_out; rm -f "$T/out/flapi_table.json"
run env FL_ENGINE_DYLIB="$T/nonexistent.dylib"; rc=$?
{ [ $rc -ne 0 ] && grep -q "引き継ぎ元" "$T/log" && [ ! -e "$T/out/flapi_table.json" ]; } \
  && ok "ネガコン[dylib も既存 table も無い]: exit=$rc・理由に '引き継ぎ元'・table を作らない" \
  || { bad "ネガコン[dylib も既存 table も無い]: exit=$rc"; sed 's/^/  | /' "$T/log"; }

echo "---- fail=$fail"
[ $fail -eq 0 ]
