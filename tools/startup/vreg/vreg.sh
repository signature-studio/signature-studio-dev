#!/usr/bin/env bash
# vreg の 1 コマンド e2e。 usage: bash tools/startup/vreg/vreg.sh [--no-chrome] [--no-shimx]
#   1) seed 再生成 (REGISTRY.csv → data/seed.json, keys.json)   2) C 単体テスト   3) shimx 既存テスト一式 × probe.c 同梱
#   4) wasm モジュール (SINGLE_FILE) ビルド   5) node テスト (unit/結合/IDB/CLI)   6) headless Chrome × 実 IndexedDB e2e (+ .reg 取込入口 6b)
set -euo pipefail
cd "$(dirname "$0")"
set +u; . /opt/emsdk/emsdk_env.sh >/dev/null 2>&1 || true; set -u
NOCHROME=0; NOSHIMX=0
for a in "$@"; do case $a in --no-chrome) NOCHROME=1;; --no-shimx) NOSHIMX=1;; esac; done
step() { echo "[vreg] $*"; }
step "1/6 seed 生成";            python3 scripts/build_seed.py
step "2/6 C 単体テスト";         bash build.sh test | tail -1
if [ $NOSHIMX = 0 ]; then step "3/6 shimx 既存テスト × shimx reg.c (+probe.c)"; bash build.sh shimx | grep -E "ALL PASS"; else step "3/6 (skip)"; fi
step "3b/6 symcheck";             bash build.sh symcheck
step "4/6 wasm モジュール";       bash build.sh module | tail -1
step "5/6 node テスト";          node --test --test-reporter=spec test/*.test.mjs 2>&1 | grep -E "^(✔|✖|ℹ (tests|pass|fail))" | sed 's/ ([0-9.]*ms)//'
if [ $NOCHROME = 0 ]; then step "6/6 Chrome × 実 IndexedDB"; node test/e2e_chrome.mjs; step "6b/6 .reg 取込入口 × Chrome"; node test/e2e_import_ui.mjs; else step "6/6 (skip)"; fi
step "ALL OK"
