#!/usr/bin/env bash
# 1 コマンド E2E: 入力配置 → CPython wasm ビルド → FL API/MCP 解析 → flpy リンク → 検証 (node + headless Chrome)
#   bash tools/python/run_all.sh        (初回 ~4 分: native + wasm ビルド。再実行は incremental)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
command -v node >/dev/null || export PATH="$HOME/.local/share/pnpm/bin:$PATH"
# shellcheck disable=SC1091
source "$HERE/../shared/env.sh"   # FL_WIN64_DIR / FL_MAC_DIR 等 (環境変数があればそれを優先)
FL_MAC_APP="$FL_MAC_DIR/pkg_extract/payload_out/Applications/FL Studio 2026.app"
FL_MAC="$FL_MAC_APP/Contents/Libs/FLEngine_x64.dylib"
FL_WIN="$FL_WIN64_DIR/extracted/block00031_PE.bin"
[ -s "$FL_WIN" ] || { echo "ERROR: 前提不足で停止: $FL_WIN が無い (oc_artifacts: fl-win64 / FL_WIN64_DIR)" >&2; exit 2; }
# mac pkg (pkg_extract) は win64 素材だけの環境には無い (analysis-mac-shared は Shared/ のみ / #630)。
# mac pkg を読む step (3b・4 の mac 版・7) は pkg があるときだけ実行し、無いときは追跡済みの出力を使う (#2649)
MAC_PKG=0
[ -f "$FL_MAC" ] && [ -f "$FL_MAC_APP/Contents/Resources/FL/System/Tools/MCP/MCPTools.pyc" ] && MAC_PKG=1
step() { printf '\n== %s\n' "$*"; }
PY312="$HERE/work/build-native/install/bin/python3.12"

step "1. inputs";               bash fetch_inputs.sh
step "2. CPython 3.12.1 wasm";  bash build_cpython_wasm.sh | tail -4
step "3. MCPTools.pyc 解析 (3.12 dis/marshal)"; "$PY312" analysis/mcp_extract.py > analysis/mcp/mcp_tools.json
python3 -c "import json;d=json.load(open('analysis/mcp/mcp_tools.json'));print('tools:',d['tool_count'],'imports:',len(d['imports']))"
step "3b. FL 同梱スクリプト 65 本の import 実測"
if [ "$MAC_PKG" = 1 ]; then "$PY312" analysis/scripts_inventory.py > analysis/scripts_inventory.json; else echo "SKIP: mac pkg なし ($FL_MAC_APP)。追跡済み analysis/scripts_inventory.json を使う (#2649)"; fi
python3 -c "import json;d=json.load(open('analysis/scripts_inventory.json'));print('files:',sum(d['counts'].values()),'stdlib:',len(d['stdlib_modules_used']),'fl modules:',len(d['fl_modules_used']))"
step "4. flapi 抽出 (mac x86_64/arm64 + win)"
if [ "$MAC_PKG" = 1 ]; then
  python3 analysis/flapi_extract.py "$FL_MAC" --arch x86_64 > analysis/flapi/raw_mac_x86_64.json
  python3 analysis/flapi_extract.py "$FL_MAC" --arch arm64  > analysis/flapi/raw_mac_arm64.json
else
  echo "SKIP: mac 版 (x86_64/arm64) は mac pkg なし。追跡済み analysis/flapi/raw_mac_*.json を使う (#2649)"
fi
python3 analysis/flapi_extract.py "$FL_WIN"               > analysis/flapi/raw_win64.json
python3 analysis/flapi_table.py
step "5. flpy link";           bash build_flpy.sh | tail -4
step "6. smoke (print(1+1) + stdlib)"; node tests/smoke_direct.mjs
step "7. builtin 一覧 / FL 同梱 Python 差分"; node tests/dump_builtins.mjs
if [ "$MAC_PKG" = 1 ]; then python3 analysis/py_inventory.py > analysis/python_inventory.json; else echo "SKIP: mac pkg なし。追跡済み analysis/python_inventory.json を使う (#2649)"; fi
step "8. PoC: MCPTools.pyc on wasm Python + flapi mock (Worker/SAB RPC)"; node tests/poc_mcp.mjs | grep -E '"(tools|init_ms|host_calls|roundtrip_us_per_flapi_call)"|POC'
step "8b. kwargs 省略引数の誤束縛 0 検証 (PY-15 #653, wasm 不要)"; python3 tests/kwsig_bind_check.py
step "9. 48 tools 全実行"; node tests/all_tools.mjs
step "9b. C provider (fl_api_call) 版 flprov.wasm + 48 tools"; bash provider/build.sh | tail -2; node tests/provider_check.mjs; FL_ENGINE=wasm node tests/all_tools.mjs
step "9c. PY-2 (#83): Py_* 動的束縛の対応表 + CPython/provider 同一 wasm 静的リンク + 48 tools"
source ../shared/env.sh
python3 analysis/pybind_extract.py --pe "$FL_WIN64_DIR/extracted/block00031_PE.bin" --lib work/build-wasm/libpython3.12.a --out analysis/pybind --expect 110 --check
bash build_flpy_static.sh | tail -1; node tests/static_check.mjs
step "9c. ilmcp 9 関数 e2e (状態検査 + ネガティブ)"; node tests/ilmcp_e2e.mjs
python3 analysis/mcp_classify.py
step "9c. .pyscript ローダ + flpianoroll 回帰 (同梱 Piano roll 5 / Remote 5 / Audio 12 調査)"; node tests/pyscript_e2e.mjs | grep -E '^\{"total"'
step "9c'. flpianoroll loadScoreFromFile / DialogParams (MOCK) + 64 メンバ再計算 (PY-19 #792)"; node tests/flpianoroll_dialog_load_e2e.mjs | grep -E '^\{"total"'; python3 analysis/flpianoroll_members.py
step "9d. 同梱 Piano roll 5 本を Chrome (agent-browser) 上の wasm CPython で実行 + node 出力との一致 (PY-11 #466)"
node tests/pyscript_e2e.mjs --dump work/pyscript_node.json --export-scripts work/pyscripts.json | grep -E '^\{"total"'
(cd ../e2e && [ -x node_modules/.bin/agent-browser ] || npm ci --no-audit --no-fund --ignore-scripts >/dev/null)
node tests/pyscript_browser.mjs --dump work/pyscript_chrome.json | grep -E '^\{"env"'
python3 tests/pyscript_compare.py work/pyscript_node.json work/pyscript_chrome.json
python3 tests/pyscript_compare.py work/pyscript_node.json work/pyscript_chrome.json --neg >/dev/null && { echo "NEG が不一致を検出しなかった"; exit 1; } || true   # ネガコン: exit 1 で検出できたとき正常
step "10. headless Chrome (module Worker + SAB)"; node tests/browser_check.mjs
step "11. MCP JSON-RPC を アプリ UI / devtools に公開 (Vite + headless Chrome, PY-4 #77)"; (cd "$HERE/../.." && node tools/python/tests/mcp_ui_check.mjs 2>&1 | grep -v shim_port | cut -c1-300)
step "12. MIDI scripting ホスト (PY-6 #76): device script ローダ・27 callback・Web MIDI 結線 (合成 fixture) + 同梱 device script"
node tests/midi_script.mjs | cut -c1-300
node tests/midi_script.mjs --neg | cut -c1-120 || [ $? -eq 1 ]   # ネガコン: 検出できたとき exit 1
node tests/midi_bundled_device.mjs                              # 入力が無ければ exit 3 (NOT VERIFIED) で run_all を止める
step "13. サブインタプリタ検証 (flpy.wasm: Py_NewInterpreterFromConfig)"
node tests/subinterp_probe.mjs | cut -c1-300
node tests/subinterp_probe.mjs --neg | cut -c1-120 || [ $? -eq 1 ]
bash tests/subinterp_negcontrol_old.sh | tail -2                     # ネガコン: 修正前 flpy.c (PY-12 #587) で probe が FAIL すること
step "14. MIDI scripting を アプリ UI / devtools に公開 (Vite + headless Chrome, PY-6 #76)"; (cd "$HERE/../.." && node tools/python/tests/midi_ui_check.mjs 2>&1 | grep -v shim_port | cut -c1-300)
step "15. Chord progression 41 本 (pyc 39 + pyscript 2) の import / 実行 (PY-7 #78, mock 条件つき)"
[ -d work/fl_extract ] || FL_WIN64_DIR="$FL_WIN64_DIR/extracted" python3 analysis/extract_pyc_blocks.py work/fl_extract
if [ -s work/fl_extract/drum_patterns.json ] && [ -s work/fl_extract/pyscript/cpt.pyscript ] && [ -s work/fl_extract/pyscript/stack.pyscript ]; then
  node tests/chord_progression_e2e.mjs | tail -1
else
  echo "SKIP: work/fl_extract に drum_patterns.json・pyscript/{cpt,stack}.pyscript が無い。analysis/extract_pyc_blocks.py は pyc と manifest.json だけを出力する (#2663)"
fi
step "ALL OK"
