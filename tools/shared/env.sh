#!/usr/bin/env bash
# 外部資産パスの共通定義 (bash)。`source tools/shared/env.sh` で使う。
# 既に設定済みの変数は上書きしない。未設定時のみ従来 (作業用 VM) の既定値を使う。
# python / node 版: tools/shared/paths.py / tools/shared/paths.mjs (既定値は 3 つで同一)。
# 変数と docs/REFERENCES.md のエントリ ID の対応は docs/REFERENCES.md §4。

_ss_env_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

: "${REPO_ROOT:=$(git -C "$_ss_env_dir" rev-parse --show-toplevel 2>/dev/null || (cd "$_ss_env_dir/../.." && pwd))}"
: "${ANALYSIS_DIR:=/home/ubuntu/work/analysis}"
: "${FL_WIN64_DIR:=$ANALYSIS_DIR/win64}"
: "${FL_MAC_DIR:=$ANALYSIS_DIR/mac}"
: "${PLUGINS_DIR:=$ANALYSIS_DIR/plugins}"

export REPO_ROOT ANALYSIS_DIR FL_WIN64_DIR FL_MAC_DIR PLUGINS_DIR
unset _ss_env_dir
