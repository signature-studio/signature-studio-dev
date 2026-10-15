#!/usr/bin/env bash
# functions_dll.csv (FLEngine の関数表 = Ghidra 12.1.4 headless + DumpFunctions.java の出力) を作る (#3172)。
# m11_bounds.py / m11_tail.py の入力で、素材 (R2) には含まれない。PE の sha256 が sidecar (functions_dll.csv.pe_sha256) と一致する時だけ再利用する (#3231)。
# 不一致・sidecar 無しは旧 CSV を functions_dll.csv.stale に退避して作り直す (PE が変わると関数表だけ古くなるため)。
# Ghidra は GHIDRA_HOME (docs/REFERENCES.md の [GHIDRA] の install 先) で指定できる。未指定なら公式 release を取得して sha256 を検査する (fail-closed)。
# JDK は JAVA_HOME_21 (既定は docs/REFERENCES.md の [JDK21])。PE は M11_PE / FL_WIN64_DIR で指定する。
# 使い方: bash tools/m11/m11_ghidra_dll.sh
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$HERE"
source ../shared/env.sh
GHIDRA_VER=12.1.4
GHIDRA_ZIP=ghidra_12.1.4_PUBLIC_20260921.zip
GHIDRA_SHA256=ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db
GHIDRA_URL="https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_${GHIDRA_VER}_build/${GHIDRA_ZIP}"
GPROJ=ghproj_dll
OUT_DIR="$HERE/../m2/work/ghidra_dll"
mkdir -p "$OUT_DIR"
OUT_DIR="$(cd -- "$OUT_DIR" && pwd)"
OUT="$OUT_DIR/functions_dll.csv"
SIDE="$OUT.pe_sha256"
PE="${M11_PE:-${PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}}"
[ -f "$PE" ] || { echo "[ghidra_dll] PE 無し: $PE (fail-closed)" >&2; exit 1; }
PE_SHA="$(sha256sum "$PE" | cut -d' ' -f1)"
if [ -s "$OUT" ] && [ "$(cat "$SIDE" 2>/dev/null)" = "$PE_SHA" ]; then echo "[ghidra_dll] 既存 (PE 指紋一致): $OUT ($(wc -l < "$OUT") 行)"; exit 0; fi
if [ -e "$OUT" ]; then mv -f "$OUT" "$OUT.stale"; echo "[ghidra_dll] PE 指紋が sidecar と不一致 (または無し): 旧 CSV を $OUT.stale に退避して作り直す"; fi
rm -f "$SIDE"
CACHE="${GHIDRA_CACHE:-${RUNNER_TEMP:-$HERE/work/tmp}/ghidra}"
JDK="${JAVA_HOME_21:-/usr/lib/jvm/temurin-21-jdk-amd64}"
[ -x "$JDK/bin/java" ] && "$JDK/bin/java" -version 2>&1 | grep -q 'version "21' \
  || { echo "[ghidra_dll] JDK 21 無し: $JDK (JAVA_HOME_21 で指定; fail-closed)" >&2; exit 1; }
export JAVA_HOME="$JDK" PATH="$JDK/bin:$PATH" MAXMEM="${MAXMEM:-8G}"
GH="${GHIDRA_HOME:-}"
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
SCRIPTS="$(cd -- "$HERE/../m2/ghidra_scripts" && pwd)"
rm -rf "$OUT_DIR/$GPROJ.gpr" "$OUT_DIR/$GPROJ.rep" "$OUT.tmp"
LOG="$OUT_DIR/ghidra_dll.log"
rc=0
"$GH/support/analyzeHeadless" "$OUT_DIR" "$GPROJ" -import "$PE" \
  -scriptPath "$SCRIPTS" \
  -postScript DumpFunctions.java "$OUT.tmp" \
  -analysisTimeoutPerFile 5400 > "$LOG" 2>&1 || rc=$?
rm -rf "$OUT_DIR/$GPROJ.gpr" "$OUT_DIR/$GPROJ.rep"
if [ "$rc" != 0 ] || [ ! -s "$OUT.tmp" ] || [ "$(wc -l < "$OUT.tmp")" -lt 1000 ]; then
  echo "[ghidra_dll] 失敗: rc=$rc ($LOG 末尾)" >&2; tail -15 "$LOG" >&2; rm -f "$OUT.tmp"; exit 1
fi
mv "$OUT.tmp" "$OUT"
echo "$PE_SHA" > "$SIDE"
echo "[ghidra_dll] 作成: $OUT ($(wc -l < "$OUT") 行, sha256 $(sha256sum "$OUT" | cut -d' ' -f1), PE $PE_SHA)"
