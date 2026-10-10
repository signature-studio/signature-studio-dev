#!/usr/bin/env bash
# keyfix_e2e.sh — CAB-213 の 1 コマンド検収。
#   1) seed 再生成 (vreg build_seed.py — 読取専用スクリプトの実行) + key 上書き適用 (apply_keys.py)
#   2) vreg e2e (C 単体 / shimx 結合 / symcheck / wasm モジュール / node テスト / Chrome IndexedDB)
#   3) pathreg e2e (C↔JS 写像 + vreg 双方向ミラー)
#   4) seed/マウント表整合チェック (verify_consistency.py)
# usage: bash tools/startup/keyfix/keyfix_e2e.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
WS="$(cd "$HERE/../../.." && pwd)"
VREG="$WS/tools/startup/vreg"
PATHREG="$WS/tools/shimx/pathreg"
export TMPDIR="$HERE/work/tmp"
mkdir -p "$TMPDIR"
step() { echo "[keyfix] $*"; }

step "1/5 seed 再生成 + key 上書き"
(cd "$VREG" && python3 scripts/build_seed.py)
python3 "$HERE/apply_keys.py"

step "2/5 vreg e2e (C 単体 / shimx 結合 / symcheck / module / node / Chrome)"
set +u; . /opt/emsdk/emsdk_env.sh >/dev/null 2>&1 || true; set -u
(cd "$VREG" && bash build.sh test | tail -1)
(cd "$VREG" && bash build.sh shimx | grep -E "ALL PASS")
(cd "$VREG" && bash build.sh symcheck)
(cd "$VREG" && bash build.sh module | tail -1)
(cd "$VREG" && node --test test/*.test.mjs 2>&1 | grep -E "^(✔|✖|ℹ (tests|pass|fail))" | sed 's/ ([0-9.]*ms)//')
(cd "$VREG" && node test/e2e_chrome.mjs)

step "3/5 pathreg e2e"
bash "$PATHREG/scripts/e2e.sh"

step "4/5 seed / マウント表整合チェック"
python3 "$HERE/verify_consistency.py"

step "5/5 低頻度 lingering 確認 (git 差分は担当範囲のみ)"
cd "$WS"
git status --short -- tools/startup/vreg tools/shimx/pathreg tools/startup/keyfix | sed 's/^/  /'
step "ALL OK"
