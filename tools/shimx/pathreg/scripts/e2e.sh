#!/usr/bin/env bash
# pathreg 1 コマンド検収 (CAB-168): C 単体 (ST/MT) → JS 単体 → e2e (モック永続化層)。
#   bash tools/shimx/pathreg/scripts/e2e.sh
# 成功基準: exit 0 (全 PASS 表示付き)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"
set +u; . /opt/emsdk/emsdk_env.sh >/dev/null 2>&1 || true; set -u
command -v node >/dev/null || { echo "[pathreg] FAIL: node が見つかりません (emsdk 環境)" >&2; exit 1; }

echo "[pathreg] 1/3 ビルド + C 単体テスト (ST/MT)"
bash "$HERE/scripts/build.sh" test

echo "[pathreg] 2/3 module ビルド (module-a: vreg_* フック export + probe 同梱 / module-b: フック非 export)"
bash "$HERE/scripts/build.sh" module-a >/dev/null
bash "$HERE/scripts/build.sh" module-b >/dev/null

echo "[pathreg] 3/3 JS 単体 + e2e"
LOG="$HERE/build/jsunit.log"
node --test "$HERE/test/pathmap.test.mjs" > "$LOG" 2>&1 || { tail -30 "$LOG"; exit 1; }
grep -E "^ℹ (pass|fail)" "$LOG" | sed 's/^/    /'
node "$HERE/test/e2e.mjs"

echo "[pathreg] ALL PASS (e2e.sh exit 0)"
