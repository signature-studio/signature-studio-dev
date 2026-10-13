#!/usr/bin/env bash
# RT-8: lift 成果物 (LLVM IR) を wasm32 / wasm64(Memory64) の両方に同一ソース・同一フラグでビルドし、
# 同一入力で実行した出力ハッシュが一致することを確認する。不一致・ビルド失敗・is64 取り違えは非 0 終了。
#   bash tools/runtime/ci/wasm64_check.sh [--neg] [target ...]      既定 target: ott
#   target = tools/runtime/ci/targets/<name>.sh (ir_path / build_inputs / driver を定義)
#   --neg : wasm64 側 IR を 1 箇所壊し、検出器が FAIL することを確認する (ネガティブコントロール)
# 環境変数: EMSDK_ENV (既定 /opt/emsdk/emsdk_env.sh) / OUT (既定 tools/runtime/work/ci) / TMPDIR
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/../../shared/env.sh"
OUT="${OUT:-$HERE/../work/ci}"; mkdir -p "$OUT"
EMSDK_ENV_FILE="${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}"
[ -f "$EMSDK_ENV_FILE" ] || { echo "[wasm64_check] emsdk_env.sh not found: $EMSDK_ENV_FILE (EMSDK_ENV で指定)" >&2; exit 2; }
source "$EMSDK_ENV_FILE" >/dev/null 2>&1
export TMPDIR="${TMPDIR:-$OUT/tmp}"; mkdir -p "$TMPDIR"

NEG=0; TARGETS=()
for a in "$@"; do case "$a" in --neg) NEG=1 ;; *) TARGETS+=("$a") ;; esac; done
[ ${#TARGETS[@]} -gt 0 ] || TARGETS=(ott)

P64_DL='target datalayout = "e-m:e-p:64:64-p10:8:8-p20:8:8-i64:64-i128:128-f128:64-n32:64-S128-ni:1:10:20"'
rc=0
for T in "${TARGETS[@]}"; do
  TF="$HERE/targets/$T.sh"
  [ -f "$TF" ] || { echo "[wasm64_check] unknown target: $T" >&2; exit 2; }
  unset -f ir_path build_inputs build_flags 2>/dev/null || true
  # shellcheck disable=SC1090
  source "$TF"
  IR="$(ir_path)"
  [ -f "$IR" ] || { echo "[wasm64_check:$T] input IR not found: $IR" >&2; exit 2; }
  D="$OUT/$T"; mkdir -p "$D"
  sed "s/^target datalayout = .*/$P64_DL/" "$IR" > "$D/${T}_p64.ll"
  grep -q '^target datalayout = ".*-p:64:64-' "$D/${T}_p64.ll" || { echo "[wasm64_check:$T] datalayout rewrite failed" >&2; exit 2; }
  if [ "$NEG" = 1 ]; then
    sed -i 's/fadd float/fsub float/g' "$D/${T}_p64.ll"
    cmp -s "$IR" "$D/${T}_p64.ll" && { echo "[wasm64_check:$T] neg mutation had no effect" >&2; exit 2; }
  fi
  mapfile -t INPUTS < <(build_inputs)
  mapfile -t FLAGS < <(build_flags)
  build() { # $1=name $2=ir $3..=extra flags
    local name=$1 ir=$2; shift 2
    local t0=$SECONDS
    if ! emcc "${INPUTS[@]}" "$ir" -o "$D/$name.js" -w -Wno-error=int-conversion -Wno-implicit-function-declaration \
        -O2 -sALLOW_MEMORY_GROWTH=0 -sINITIAL_MEMORY=$((0x36000000)) -sERROR_ON_UNDEFINED_SYMBOLS=0 --no-entry -Wl,--no-gc-sections \
        "${FLAGS[@]}" "$@" >"$D/$name.build.log" 2>&1; then
      echo "[wasm64_check:$T] BUILD FAIL $name (log: $D/$name.build.log)" >&2; tail -5 "$D/$name.build.log" >&2; return 1
    fi
    echo "[wasm64_check:$T] built $name.wasm $(stat -c %s "$D/$name.wasm") bytes in $((SECONDS - t0)) s"
  }
  t_all=$SECONDS
  ( cd "$TARGET_CWD" && build "${T}32" "$IR" ) & p32=$!
  ( cd "$TARGET_CWD" && build "${T}64" "$D/${T}_p64.ll" -sMEMORY64=1 ) & p64=$!
  b=0; wait $p32 || b=1; wait $p64 || b=1
  [ $b = 0 ] || { rc=1; continue; }
  echo "[wasm64_check:$T] build total $((SECONDS - t_all)) s (load $(cut -d' ' -f1-3 /proc/loadavg))"
  if "${EMSDK_NODE:-node}" "$HERE/wasm64_check.mjs" "$T" "$D/${T}32.wasm" "$D/${T}64.wasm" "$(driver_path)" "${EXPECT_HASHES:-}"; then
    [ "$NEG" = 0 ] || { echo "[wasm64_check:$T] NEG-CONTROL FAIL: 壊した IR でも一致 (検出器が無効)" >&2; rc=1; }
  else
    if [ "$NEG" = 1 ]; then echo "[wasm64_check:$T] NEG-CONTROL OK: 壊した IR で不一致を検出"; else rc=1; fi
  fi
done
exit $rc
