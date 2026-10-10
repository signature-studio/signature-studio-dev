#!/usr/bin/env bash
# VST3 SDK (steinbergmedia/vst3sdk) を tools/targets/serum2/work/vst3sdk へ取得 (gitignore)
# ヘッダのみ使用 (pluginterfaces)。CAB-68 host のビルド前提。
set -euo pipefail
cd "$(dirname "$0")"
SDK=../work/vst3sdk
if [ -d "$SDK/pluginterfaces/vst" ]; then
  echo "vst3sdk 既存: $SDK"
  exit 0
fi
mkdir -p ../work
git clone -q --depth 1 --recurse-submodules --shallow-submodules \
  https://github.com/steinbergmedia/vst3sdk.git "$SDK"
echo "clone ok: $SDK"
ls "$SDK/pluginterfaces/vst" | head -5
