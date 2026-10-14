#!/usr/bin/env bash
# functions_dll.csv (FLEngine の関数表 = Ghidra 12.1.4 headless + DumpFunctions.java の出力) を作る (#3172)。
# m11_bounds.py / m11_tail.py の入力で、素材 (R2) には含まれない。既に有れば何もしない。
# Ghidra は GHIDRA_HOME → /opt/ghidra の順に探し、無ければ公式 release を取得して sha256 を検査する (fail-closed)。
# JDK は JAVA_HOME_21 (既定 /usr/lib/jvm/temurin-21-jdk-amd64)。PE は M11_PE / FL_WIN64_DIR で指定する。
# 使い方: bash tools/m11/m11_ghidra_dll.sh
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$HERE"
source ../shared/env.sh
GHIDRA_VER=12.1.4
GHIDRA_ZIP=ghidra_12.1.4_PUBLIC_20260921.zip
GHIDRA_SHA256=ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db
GHIDRA_URL="https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_${GHIDRA_VER}_build/${GHIDRA_ZIP}"
OUT_DIR="$HERE/../m2/work/ghidra_dll"
OUT="$OUT_DIR/functions_dll.csv"
if [ -s "$OUT" ]; then echo "[ghidra_dll] 既存: $OUT ($(wc -l < "$OUT") 行)"; exit 0; fi
PE="${M11_PE:-${PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}}"
[ -f "$PE" ] || { echo "[ghidra_dll] PE 無し: $PE (fail-closed)" >&2; exit 1; }
CACHE="${GHIDRA_CACHE:-${RUNNER_TEMP:-$HERE/work/tmp}/ghidra}"
JDK="${JAVA_HOME_21:-/usr/lib/jvm/temurin-21-jdk-amd64}"
[ -x "$JDK/bin/java" ] && "$JDK/bin/java" -version 2>&1 | grep -q 'version "21' \
  || { echo "[ghidra_dll] JDK 21 無し: $JDK (JAVA_HOME_21 で指定; fail-closed)" >&2; exit 1; }
export JAVA_HOME="$JDK" PATH="$JDK/bin:$PATH" MAXMEM="${MAXMEM:-8G}"
GH="${GHIDRA_HOME:-}"
if [ -z "$GH" ] && [ -x /opt/ghidra/support/analyzeHeadless ]; then GH=/opt/ghidra; fi
if [ -z "$GH" ]; then
  GH="$CACHE/ghidra_${GHIDRA_VER}_PUBLIC"
  if [ ! -x "$GH/support/analyzeHeadless" ]; then
    mkdir -p "$CACHE"
    ZIP="$CACHE/$GHIDRA_ZIP"
    if [ ! -f "$ZIP" ] || [ "$(sha256sum "$ZIP" | cut -d' ' -f1)" != "$GHIDRA_SHA256" ]; then
      echo "[ghidra_dll] Ghidra ${GHIDRA_VER} を取得: $GHIDRA_URL"
      curl -fL --retry 3 -o "$ZIP.part" "$GHIDRA_URL"
      mv "$ZIP.part" "$ZIP"
    fi
    [ "$(sha256sum "$ZIP" | cut -d' ' -f1)" = "$GHIDRA_SHA256" ] \
      || { echo "[ghidra_dll] sha256 不一致: $ZIP (fail-closed)" >&2; rm -f "$ZIP"; exit 1; }
    unzip -q -o "$ZIP" -d "$CACHE"
  fi
fi
[ -x "$GH/support/analyzeHeadless" ] || { echo "[ghidra_dll] analyzeHeadless 無し: $GH (fail-closed)" >&2; exit 1; }
mkdir -p "$OUT_DIR"
OUT_DIR="$(cd -- "$OUT_DIR" && pwd)"
OUT="$OUT_DIR/functions_dll.csv"
SCRIPTS="$(cd -- "$HERE/../m2/ghidra_scripts" && pwd)"
rm -rf "$OUT_DIR/ghproj" "$OUT.tmp"
LOG="$OUT_DIR/ghidra_dll.log"
rc=0
"$GH/support/analyzeHeadless" "$OUT_DIR" ghproj_dll -import "$PE" \
  -scriptPath "$SCRIPTS" \
  -postScript DumpFunctions.java "$OUT.tmp" \
  -analysisTimeoutPerFile 5400 > "$LOG" 2>&1 || rc=$?
rm -rf "$OUT_DIR/ghproj"
if [ "$rc" != 0 ] || [ ! -s "$OUT.tmp" ] || [ "$(wc -l < "$OUT.tmp")" -lt 1000 ]; then
  echo "[ghidra_dll] 失敗: rc=$rc ($LOG 末尾)" >&2; tail -15 "$LOG" >&2; rm -f "$OUT.tmp"; exit 1
fi
mv "$OUT.tmp" "$OUT"
echo "[ghidra_dll] 作成: $OUT ($(wc -l < "$OUT") 行, sha256 $(sha256sum "$OUT" | cut -d' ' -f1))"
