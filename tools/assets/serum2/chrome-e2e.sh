#!/usr/bin/env bash
# Serum 2 コンテンツの実 Chrome e2e (#70)。pass 1 本 + ネガコン 1 本。不合格は exit 1。
#   先に serum2/e2e.sh の prep (inventory + pack) を済ませた $SERUM2_WORK/{inv,pkg} を使う。
#   SERUM2_WORK=<dir> bash tools/assets/serum2/chrome-e2e.sh
# pass : browser-test (cold / warm / xhr-cold, Chrome 実機) が exit 0 かつ ALL PASS
# neg  : 全 sha を反転した inventory を与えると browser-test は exit 1 かつ FAILED > 0 でなければならない
set -euo pipefail
cd "$(dirname "$0")/.."
BASE="${SERUM2_WORK:-$(pwd)/serum2/work/run}"
INV="$BASE/inv/inv.jsonl"; PKG="$BASE/pkg"
[[ -f "$INV" && -f "$PKG/latest.json" ]] || { echo "[chrome-e2e] $INV / $PKG が無い。先に serum2/e2e.sh の prep を実行"; exit 2; }
export TMPDIR="${TMPDIR:-${RUNNER_TEMP:-$BASE}}"
OUT="$BASE/chrome"; mkdir -p "$OUT"

run() { # inv out -> exit code
  local rc=0
  timeout 900 node test/browser-test.ts --pkg "$PKG" --inv "$1" --sample 150 --out "$2" >"$2.log" 2>&1 || rc=$?
  echo "$rc"
}
failed() { node -e "console.log(JSON.parse(require('fs').readFileSync('$1','utf8')).failed)" 2>/dev/null || echo NA; }

t=$(date +%s); rc=$(run "$INV" "$OUT/pass.json"); dt=$(( $(date +%s) - t ))
got=$(failed "$OUT/pass.json")
okp=$([[ $rc == 0 && $got == 0 ]] && echo 1 || echo 0)
echo "[pass] exit=$rc failed=$got ${dt}s load $(cut -d' ' -f1-3 /proc/loadavg) => $([[ $okp == 1 ]] && echo OK || echo NG)"

NEG="$OUT/neg-inv.jsonl"
node -e "
const fs=require('fs');
const L=fs.readFileSync('$INV','utf8').trim().split('\n').map(l=>{const e=JSON.parse(l);e.sha='0'.repeat(64);return JSON.stringify(e)});
fs.writeFileSync('$NEG',L.join('\n')+'\n');"
t=$(date +%s); rc=$(run "$NEG" "$OUT/neg.json"); dt=$(( $(date +%s) - t ))
got=$(failed "$OUT/neg.json")
okn=$([[ $rc == 1 && $got =~ ^[0-9]+$ && $got -gt 0 ]] && echo 1 || echo 0)
echo "[neg-sha] exit=$rc failed=$got ${dt}s => $([[ $okn == 1 ]] && echo OK || echo NG)"

[[ $okp == 1 && $okn == 1 ]] && echo "SERUM2 CHROME E2E OK" || { echo "SERUM2 CHROME E2E NG"; tail -15 "$OUT/pass.json.log"; exit 1; }
