#!/usr/bin/env bash
# SHX-T12 (#789): 構造化 file trace の単体テスト。node 上で完結し exit 0 が成功基準。
#   1. ST ビルド (src/*.c + test/ftrace/ftrace_main.c)
#   2. shimx_set_trace_file で有効化して操作 → トレース行を抽出 → scripts/ftrace_summary.py で集計 → 期待値と照合
#   3. ネガコン: トレース無効の同一操作は JSON 行を出力しない
#   4. 既存の stderr トレース (shimx_set_trace(1), CreateFile open(...) failed) が残り JSON が混ざらない
#   5. 環境変数 SHIMX_TRACE_FILE の経路 (NODERAWFS ビルドのみ guest から見える)
#   6. 集計スクリプトの単体テスト (不正 JSON は exit 2)
# 使い方: bash tools/shimx/test/ftrace/ftrace_test.sh
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
BUILD="$HERE/build"
mkdir -p "$BUILD"
source "$HERE/flags.sh"
set +u; . /opt/emsdk/emsdk_env.sh >/dev/null 2>&1 || true; set -u

info() { echo "[ftrace] $*"; }
die()  { echo "[ftrace] FAIL: $*" >&2; exit 1; }

info "1/6 ST ビルド"
emcc "${SHIMX_CLANG_FLAGS[@]}" "${SHIMX_EMCC_ST[@]}" -I"$HERE/src" "$HERE"/src/*.c "$HERE/test/ftrace/ftrace_main.c" \
    -o "$BUILD/ftrace_st.js" || die "emcc ビルド失敗"
mv "$BUILD/ftrace_st.js" "$BUILD/ftrace_st.cjs"

info "2/6 実行 + 集計 (期待値照合)"
rc=0
node "$BUILD/ftrace_st.cjs" traced > "$BUILD/ftrace.out" 2> "$BUILD/ftrace.err" || rc=$?
[ "$rc" -eq 0 ] || { tail -5 "$BUILD/ftrace.err" >&2; die "traced 実行失敗 (exit=$rc)"; }
grep -q "^ops ok$" "$BUILD/ftrace.out" || die "ops ok が出力されていない"
sed -n '/^--TRACE-BEGIN--$/,/^--TRACE-END--$/p' "$BUILD/ftrace.out" | sed '1d;$d' > "$BUILD/ftrace.jsonl"
python3 "$HERE/scripts/ftrace_summary.py" "$BUILD/ftrace.jsonl" --json "$BUILD/ftrace_summary.json" > "$BUILD/ftrace_summary.txt" \
    || die "集計失敗"
python3 - "$BUILD/ftrace_summary.json" <<'PYEOF' || die "期待値と不一致 (ftrace_summary.json)"
import json, sys
s = json.load(open(sys.argv[1]))
exp_api = {"CreateFileW": 2, "CreateFileA": 1, "GetFileAttributesW": 2,
           "FindFirstFileW": 2, "FindNextFileW": 2, "ReadFile": 1}
for k, v in exp_api.items():
    got = s["by_api"].get(k, 0)
    assert got == v, f"{k}: expected {v}, got {got} ({s['by_api']})"
assert s["events"] == 10, f"events: expected 10, got {s['events']}"
assert s["fail"] == 4, f"fail: expected 4, got {s['fail']}"
assert s["fail_err"] == {"2": 3, "18": 1}, f"fail_err: {s['fail_err']}"
assert s["write"] == 1, f"write: expected 1 (CREATE_ALWAYS), got {s['write']}"
assert s["distinct_posix_opened"] == 2, f"opened paths: {s['distinct_posix_opened']}"
print("expect ok:", s["events"], "events")
PYEOF
info "    $(cat "$BUILD/ftrace_summary.txt" | tr -d '\n' | head -c 300)"

info "3/6 ネガコン (SHIMX_TRACE_FILE 無し → 出力が空)"
node "$BUILD/ftrace_st.cjs" untraced > "$BUILD/ftrace_neg.out" 2>/dev/null
if grep -q -- "--TRACE-BEGIN--" "$BUILD/ftrace_neg.out"; then die "ネガコン: トレース未指定なのに出力された"; fi
grep -q "^ops ok$" "$BUILD/ftrace_neg.out" || die "ネガコン: ops が実行されていない"
info "    ✓ トレース無効時は JSON 行なし"

info "4/6 既存 stderr トレース (shimx_set_trace(1)) が残り、JSON 行は混ざらない"
node "$BUILD/ftrace_st.cjs" stderr > /dev/null 2> "$BUILD/ftrace_stderr.err" || die "stderr モード実行失敗"
grep -q "CreateFile open(" "$BUILD/ftrace_stderr.err" || die "既存 SHX_TRACE の stderr 出力が消えた"
if grep -q '^{"seq"' "$BUILD/ftrace_stderr.err"; then die "stderr に JSON 行が混入した"; fi
info "    ✓ 既存 stderr 出力あり / JSON 混入なし"

info "5/6 環境変数 SHIMX_TRACE_FILE の経路 (NODERAWFS ビルド: guest getenv が host env を見る版のみ)"
emcc "${SHIMX_CLANG_FLAGS[@]}" "${SHIMX_EMCC_ST[@]}" -sNODERAWFS=1 -I"$HERE/src" "$HERE"/src/*.c "$HERE/test/ftrace/ftrace_main.c" \
    -o "$BUILD/ftrace_raw.js" || die "NODERAWFS ビルド失敗"
mv "$BUILD/ftrace_raw.js" "$BUILD/ftrace_raw.cjs"
ENVF="$BUILD/ftr_env_trace.jsonl"; rm -f "$ENVF"
(cd "$BUILD" && SHIMX_TRACE_FILE="$ENVF" node ftrace_raw.cjs env > env_on.out 2>&1) || die "env 実行失敗 (有効)"
[ -s "$ENVF" ] || die "SHIMX_TRACE_FILE 指定時にトレースファイルが生成されない"
grep -q '"api":"CreateFileW"' "$ENVF" || die "env 経路: CreateFileW の行が無い"
rm -f "$ENVF"
(cd "$BUILD" && node ftrace_raw.cjs env > env_off.out 2>&1) || die "env 実行失敗 (無効)"
[ ! -e "$ENVF" ] || die "ネガコン: 環境変数無しでトレースファイルが生成された"
info "    ✓ env 指定あり → JSON 行 1 件以上 / 指定なし → ファイル無し"

info "6/6 集計スクリプト単体 (不正 JSON は exit 2, 空行は無視)"
set +e
printf '{"api":"ReadFile","ok":true}\n\n{bad json\n' > "$BUILD/bad.jsonl"
python3 "$HERE/scripts/ftrace_summary.py" "$BUILD/bad.jsonl" > /dev/null 2>&1; brc=$?
set -e
[ "$brc" -eq 2 ] || die "不正 JSON で exit=$brc (期待 2)"
printf '{"api":"ReadFile"}\n' > "$BUILD/nokey.jsonl"
set +e
python3 "$HERE/scripts/ftrace_summary.py" "$BUILD/nokey.jsonl" > /dev/null 2>&1; krc=$?
set -e
[ "$krc" -eq 2 ] || die "必須キー欠落で exit=$krc (期待 2)"
info "    ✓ 不正 JSON → exit 2 / 必須キー欠落 → exit 2"
info "完了: SHX-T12 ftrace 全 PASS"
