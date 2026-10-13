#!/usr/bin/env bash
# 1 コマンド E2E: 入力配置 → CPython wasm ビルド → FL API/MCP 解析 → flpy リンク → 検証 (node + headless Chrome)
#   bash tools/python/run_all.sh        (初回 ~4 分: native + wasm ビルド。再実行は incremental)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
command -v node >/dev/null || export PATH="$HOME/.local/share/pnpm/bin:$PATH"
FL_MAC="/home/ubuntu/work/analysis/mac/pkg_extract/payload_out/Applications/FL Studio 2026.app/Contents/Libs/FLEngine_x64.dylib"
FL_WIN="/home/ubuntu/work/analysis/win64/extracted/block00031_PE.bin"
# shellcheck disable=SC1091
source "$HERE/../shared/env.sh"   # FL_WIN64_DIR 等 (環境変数があればそれを優先)
step() { printf '\n== %s\n' "$*"; }
PY312="$HERE/work/build-native/install/bin/python3.12"

step "1. inputs";               bash fetch_inputs.sh
step "2. CPython 3.12.1 wasm";  bash build_cpython_wasm.sh | tail -4
step "3. MCPTools.pyc 解析 (3.12 dis/marshal)"; "$PY312" analysis/mcp_extract.py > analysis/mcp/mcp_tools.json
python3 -c "import json;d=json.load(open('analysis/mcp/mcp_tools.json'));print('tools:',d['tool_count'],'imports:',len(d['imports']))"
step "3b. FL 同梱スクリプト 65 本の import 実測"; "$PY312" analysis/scripts_inventory.py > analysis/scripts_inventory.json
python3 -c "import json;d=json.load(open('analysis/scripts_inventory.json'));print('files:',sum(d['counts'].values()),'stdlib:',len(d['stdlib_modules_used']),'fl modules:',len(d['fl_modules_used']))"
step "4. flapi 抽出 (mac x86_64/arm64 + win)"
python3 analysis/flapi_extract.py "$FL_MAC" --arch x86_64 > analysis/flapi/raw_mac_x86_64.json
python3 analysis/flapi_extract.py "$FL_MAC" --arch arm64  > analysis/flapi/raw_mac_arm64.json
python3 analysis/flapi_extract.py "$FL_WIN"               > analysis/flapi/raw_win64.json
python3 analysis/flapi_table.py
step "5. flpy link";           bash build_flpy.sh | tail -4
step "6. smoke (print(1+1) + stdlib)"; node tests/smoke_direct.mjs
step "7. builtin 一覧 / FL 同梱 Python 差分"; node tests/dump_builtins.mjs; python3 analysis/py_inventory.py > analysis/python_inventory.json
step "8. PoC: MCPTools.pyc on wasm Python + flapi mock (Worker/SAB RPC)"; node tests/poc_mcp.mjs | grep -E '"(tools|init_ms|host_calls|roundtrip_us_per_flapi_call)"|POC'
step "9. 48 tools 全実行"; node tests/all_tools.mjs
step "9b. C provider (fl_api_call) 版 flprov.wasm + 48 tools"; bash provider/build.sh | tail -2; node tests/provider_check.mjs; FL_ENGINE=wasm node tests/all_tools.mjs
python3 analysis/mcp_classify.py
step "9c. .pyscript ローダ + flpianoroll 回帰 (同梱 Piano roll 5 / Remote 5 / Audio 12 調査)"; node tests/pyscript_e2e.mjs | grep -E '^\{"total"'
step "10. headless Chrome (module Worker + SAB)"; node tests/browser_check.mjs
step "11. MCP JSON-RPC を アプリ UI / devtools に公開 (Vite + headless Chrome, PY-4 #77)"; (cd "$HERE/../.." && node tools/python/tests/mcp_ui_check.mjs 2>&1 | grep -v shim_port | cut -c1-300)
step "ALL OK"
