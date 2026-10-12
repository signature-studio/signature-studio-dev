#!/usr/bin/env bash
# env.sh / paths.py / paths.mjs が同じ値を返すことの検査 (1 コマンド再現)。
# 使い方: bash tools/shared/test_paths.sh
# ケース: (1) 全変数未設定 (既定値) (2) ANALYSIS_DIR のみ設定 (3) 個別変数を設定
# 各ケースで 3 言語の出力を比較し、さらに期待値と照合する。ネガティブコントロールとして
# 1 言語の出力を壊した場合に FAIL することも確認する。
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(git -C "$here" rev-parse --show-toplevel)"
vars=(REPO_ROOT ANALYSIS_DIR FL_WIN64_DIR FL_MAC_DIR PLUGINS_DIR)

dump_sh() { bash -c 'source "$1"; for v in REPO_ROOT ANALYSIS_DIR FL_WIN64_DIR FL_MAC_DIR PLUGINS_DIR; do echo "$v=${!v}"; done' _ "$here/env.sh"; }
dump_py() { python3 "$here/paths.py"; }
dump_mjs() { node "$here/paths.mjs"; }

fail=0
check() { # name expected_file
  local name="$1" exp="$2" sh py mjs
  sh="$(dump_sh)"; py="$(dump_py)"; mjs="$(dump_mjs)"
  if [ "$sh" = "$py" ] && [ "$py" = "$mjs" ] && [ "$sh" = "$(cat "$exp")" ]; then
    echo "PASS $name"
  else
    echo "FAIL $name"; diff <(echo "$sh") <(echo "$py") || true; diff <(echo "$py") <(echo "$mjs") || true
    diff <(echo "$sh") "$exp" || true
    return 1
  fi
}

tmp="$(mktemp)"; trap 'rm -f "$tmp"' EXIT

# (1) 既定値
unset REPO_ROOT ANALYSIS_DIR FL_WIN64_DIR FL_MAC_DIR PLUGINS_DIR
cat >"$tmp" <<EOF
REPO_ROOT=$root
ANALYSIS_DIR=/home/ubuntu/work/analysis
FL_WIN64_DIR=/home/ubuntu/work/analysis/win64
FL_MAC_DIR=/home/ubuntu/work/analysis/mac
PLUGINS_DIR=/home/ubuntu/work/analysis/plugins
EOF
check default "$tmp" || fail=1

# (2) ANALYSIS_DIR のみ
export ANALYSIS_DIR=/x/an
cat >"$tmp" <<EOF
REPO_ROOT=$root
ANALYSIS_DIR=/x/an
FL_WIN64_DIR=/x/an/win64
FL_MAC_DIR=/x/an/mac
PLUGINS_DIR=/x/an/plugins
EOF
check analysis_dir_only "$tmp" || fail=1

# (3) 個別指定
export FL_WIN64_DIR=/w FL_MAC_DIR=/m PLUGINS_DIR=/p REPO_ROOT=/r
cat >"$tmp" <<EOF
REPO_ROOT=/r
ANALYSIS_DIR=/x/an
FL_WIN64_DIR=/w
FL_MAC_DIR=/m
PLUGINS_DIR=/p
EOF
check individual_override "$tmp" || fail=1

# ネガティブコントロール: 期待値を 1 行壊すと FAIL になること
sed -i 's|^FL_MAC_DIR=.*|FL_MAC_DIR=/broken|' "$tmp"
if (check negctl "$tmp" >/dev/null 2>&1); then echo "FAIL negctl (broken expectation passed)"; fail=1; else echo "PASS negctl (broken expectation detected)"; fi

exit $fail
