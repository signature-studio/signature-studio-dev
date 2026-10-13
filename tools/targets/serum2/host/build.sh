#!/usr/bin/env bash
# CAB-68 host build (mingw-w64 x86_64 → wine で駆動)
# 前提: g++-mingw-w64-x86-64 / vst3sdk ヘッダ (host/setup_sdk.sh で work/vst3sdk へ取得)
set -euo pipefail
cd "$(dirname "$0")"

SDK=../work/vst3sdk
if [ ! -d "$SDK/pluginterfaces/vst" ]; then
  echo "vst3sdk 無し → setup_sdk.sh を実行します"
  bash setup_sdk.sh
fi

mkdir -p work/build
x86_64-w64-mingw32-g++ -std=c++17 -O2 \
  -I"$SDK" \
  -static -static-libgcc -static-libstdc++ \
  vst3host.cpp -o work/build/vst3host.exe \
  -lole32 -luuid
echo "build ok: work/build/vst3host.exe"
