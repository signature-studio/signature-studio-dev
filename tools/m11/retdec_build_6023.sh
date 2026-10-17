#!/usr/bin/env bash
# #6023 (M11-38): RetDec v5.0 (53e55b4b) を LLVM fork (avast/llvm 2a1f3d8a) にリンクしてソースビルドする。
# 結果と所要は tools/m11/REPORT_APPENDIX_6023.md。use-list 計装パッチは未適用 (本スクリプトの範囲外)。
# 使い方: RB_WORK=<作業dir> bash tools/m11/retdec_build_6023.sh
# 前提: git / cmake / ninja / gcc 13 / make。RB_WORK は $RUNNER_TEMP 配下 (repo 内に置かない)。
set -euo pipefail
W="${RB_WORK:?RB_WORK を指定 (repo 外の作業 dir)}"
mkdir -p "$W" && cd "$W"
if [ ! -d src ]; then
  git clone --filter=blob:none --no-checkout https://github.com/avast/retdec src
fi
git -C src checkout 53e55b4b
mkdir -p build && cd build
cmake ../src -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DRETDEC_COMPILE_YARA=OFF -DYARA_MAKE_PROGRAM=/usr/bin/make \
  -DCMAKE_CXX_FLAGS="-include cstdint" > cfg.log 2>&1
ninja -j4 retdec-decompiler > make.log 2>&1
# LLVM の取得時 sha256 は CMake の URL_HASH が cmake/deps.cmake の LLVM_ARCHIVE_SHA256 で照合する。
# 取得物の sha を独立に確認する場合: sha256sum external/src/llvm.zip (期待値 96389d21…)
src/retdec-decompiler/retdec-decompiler --version 2>&1 | head -2
