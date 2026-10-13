#!/usr/bin/env bash
# helpviewer 1 コマンド検証 (ST-T8 / #118):
#   bash tools/startup/helpviewer/e2e.sh
# 前提: FL_WIN64_DIR (= fl-win64 素材の展開先。直下に extracted/)。node (>=22.18: TS 型除去) / python3 / Chrome (CHROME_BIN, 既定 google-chrome) / pnpm install 済み。
# 手順: [1] FLEngine の静的根拠を機械照合 (verify_engine.py) + ネガコン
#       [2] 純ロジックの単体テスト (node --test)
#       [3] 実 Help 全 HTML への適用 (inspect_help.mjs。ピン 56 件の sha256 一致 + 安全性検査 + ネガコン)
#       [4] 実アプリ /?help=1 の headless Chrome e2e (e2e_browser.mjs。CSP/sandbox ネガコン込み)
#       [5] typecheck
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$HERE/env.sh"
REPO="$(cd "$HERE/../../.." && pwd)"
WORK="$HERE/work"; mkdir -p "$WORK"
export RUNTIME_TMP="${RUNTIME_TMP:-${RUNNER_TEMP:-/tmp}/rt}"; mkdir -p "$RUNTIME_TMP"
DLL="$FL_WIN64_DIR/extracted/block00031_PE.bin"
T0=$(date +%s.%N)
echo "[helpviewer] load average (開始): $(cut -d' ' -f1-3 /proc/loadavg) / node $(node --version)"

echo "[1/5] verify_engine.py"
python3 "$HERE/verify_engine.py" "$DLL"
python3 - "$HERE/engine_claims.json" "$WORK/claims_nc.json" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
c['strings']['0x10be5c0'][1] = '/htmlX/%s'                 # 存在しない文字列
c['calls'].append(['0x10bdaf0', '0x10bdbe0'])               # 存在しない呼出辺
c['bytes'][0]['hex'] = c['bytes'][0]['hex'].replace('c744242805', 'c744242806', 1)  # SW_SHOW=5 → 6 に壊す
json.dump(c, open(sys.argv[2], 'w'))
PY
if python3 "$HERE/verify_engine.py" "$DLL" "$WORK/claims_nc.json" > "$WORK/nc.log"; then echo "FAIL: ネガコンが通った" >&2; exit 1; fi
NC=$(grep -c '^FAIL' "$WORK/nc.log")
echo "  NC (文字列 1 + 呼出辺 1 + 機械語 1 を壊す): ${NC} 件検出 (期待 3)"
[ "$NC" = 3 ]

echo "[2/5] node --test"
node --test "$HERE/test/help_viewer.test.mjs" 2>&1 | grep -E '^# (tests|pass|fail)'
node --test "$HERE/test/help_viewer.test.mjs" > /dev/null

echo "[3/5] inspect_help.mjs"
node "$HERE/inspect_help.mjs" --json "$WORK/inspect.json"

echo "[4/5] e2e_browser.mjs"
node "$HERE/e2e_browser.mjs" --json "$WORK/browser.json" 2>&1 | grep -v 'shim_port.not_implemented_yet'

echo "[5/5] typecheck"
(cd "$REPO" && pnpm -s typecheck)

T1=$(date +%s.%N)
echo "[helpviewer] PASS / 所要 $(printf '%.1f' "$(echo "$T1 - $T0" | bc)") 秒 / load average (終了): $(cut -d' ' -f1-3 /proc/loadavg)"
