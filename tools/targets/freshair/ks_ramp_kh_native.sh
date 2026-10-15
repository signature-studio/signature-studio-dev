#!/usr/bin/env bash
# SlateCore の Gain ramp を KH 形 (cur = a + (b-a)*t) に置き換えた複製 native と HeartCore native を、
# 同一入力 (ks_semantic_gain.c) で L・R・実行後 state を比べる (#2736)。
#   usage: SC_CORE=<SlateCore.core_64> KH_CORE=<HeartCore.core_64> bash tools/targets/freshair/ks_ramp_kh_native.sh [N=200] [SEED=7]
# 出力: work/ks_ramp_kh/ (gitignore)。control = 元 SC、patched = 置換 SC。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; FA="$HERE"
if [ -z "${SC_CORE:-}" ] || [ -z "${KH_CORE:-}" ]; then
  echo "usage: SC_CORE=<SlateCore.core_64> KH_CORE=<HeartCore.core_64> bash $0 [N=200] [SEED=7]" >&2
  exit 2
fi
SC_CORE="$(realpath "$SC_CORE")"; KH_CORE="$(realpath "$KH_CORE")"
N="${1:-200}"; SEED="${2:-7}"
W="$FA/work/ks_ramp_kh"; mkdir -p "$W"; cd "$W"
cc -O1 -o ks_semantic_gain "$HERE/ks_semantic_gain.c" -lm
python3 "$HERE/ks_ramp_kh_patch.py" "$SC_CORE" sc_patched.core_64
./ks_semantic_gain sc "$SC_CORE" "$N" "$SEED" > sc_orig.txt 2> sc_orig.err
./ks_semantic_gain sc sc_patched.core_64 "$N" "$SEED" > sc_patched.txt 2> sc_patched.err
./ks_semantic_gain kh "$KH_CORE" "$N" "$SEED" > kh.txt 2> kh.err
python3 "$HERE/ks_semantic_gain_cmp.py" sc_orig.txt kh.txt | tee cmp_orig.json
python3 "$HERE/ks_semantic_gain_cmp.py" sc_patched.txt kh.txt | tee cmp_patched.json
python3 "$HERE/ks_semantic_gain_ulp.py" sc_patched.txt kh.txt | tee ulp_patched.json
