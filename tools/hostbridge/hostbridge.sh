#!/usr/bin/env bash
# hostbridge.sh — 1 コマンド検収: bash tools/hostbridge/hostbridge.sh
#   [1] 解析 evidence の機械検査 (Ghidra 出力の commit 済みスナップショット; 再生成は analysis/reproduce.sh)
#   [2] OTT module (tools/m10 の lift 済み IR + 入口 surrogate) と mini VST2 host を wasm ビルド
#   [3] marshal 規則エンジン単体試験 (FakeGuest)  [4] mini host ⇄ bridge ⇄ OTT wasm の PoC 検収
# 前提: tools/m10/work/ott_m10.ll (無ければ bash tools/m10/m10_e2e.sh)。tools/m6..m10 は読取のみ。
set -euo pipefail
HB="$(cd -- "$(dirname -- "$0")" && pwd)"
export PATH="$HOME/.local/share/pnpm/bin:$PATH"
command -v node >/dev/null || { echo "node が PATH に無い" >&2; exit 1; }
cd "$HB"
echo "== [1] evidence 検査"; python3 analysis/verify_evidence.py
echo "== [2] build"
if [ "${HB_SKIP_BUILD:-0}" != "1" ]; then
  bash poc/build_plugin_ott.sh | tail -2
  bash poc/build_host.sh | tail -1
fi
echo "== [3a] PE スタブ (仮想 FS 用) 生成 + Wrapper 事前検査相当"; node poc/pe_stub.mjs work/OTT_x64.stub.dll VSTPluginMain main && python3 analysis/check_pe_stub.py work/OTT_x64.stub.dll
echo "== [3b] marshal 単体試験"; node poc/test_marshal.mjs
echo "== [3c] Win32 shim 単体試験 + ネガコン (#784)"; node poc/test_shim.mjs
echo "== [4] PoC 検収";        node poc/run_poc.mjs
echo "[hostbridge] ALL PASS"
