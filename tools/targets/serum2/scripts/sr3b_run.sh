#!/bin/bash
# SR-3b one-command e2e: Serum 2 OSS 版同定 (zlib / muParser / zstd / PFFFT / libsfz の定数・文字列突合)。
# usage: bash scripts/sr3b_run.sh   (work/Serum2_win64.vst3 が無ければ sr3_run.sh が展開する)
# env  : PY (pefile 不要・標準 python3 で可), DL (インストーラ dir), UPSTREAM 取得は curl。
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"; cd "$HERE"
PY="${PY:-python3}"; W=work; O=out
mkdir -p $W/upstream/mp
[ -f $W/Serum2_win64.vst3 ] || { echo "missing $W/Serum2_win64.vst3 (run scripts/sr3_run.sh first)"; exit 2; }
for t in v2.1.0 v2.2.0 v2.2.4 v2.2.5 v2.2.6 v2.3.0 v2.3.1 v2.3.2 v2.3.3 v2.3.4; do
  f=$W/upstream/mp/muParserError_$t.cpp
  [ -s $f ] || curl -sL -m 60 -o $f https://raw.githubusercontent.com/beltoforion/muparser/$t/src/muParserError.cpp
done
[ -s $W/upstream/mp/zutil.c ] || curl -sL -m 60 -o $W/upstream/mp/zutil.c https://raw.githubusercontent.com/madler/zlib/v1.3.1/zutil.c
echo "sha256 $(sha256sum $W/Serum2_win64.vst3 | cut -d' ' -f1)"
$PY scripts/sr3b_version.py $W/Serum2_win64.vst3 $W/upstream/mp | tee $O/sr3b_version.txt
echo "sr3b_run OK"
