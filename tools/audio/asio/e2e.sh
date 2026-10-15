#!/usr/bin/env bash
# 1 コマンド検収 (CAB-97 / CAB-270): node check (COM 面静的検証) → headless Chrome で FLEngine 呼出を模した実行。
# 使い方: bash tools/audio/asio/e2e.sh [--quick] [--soak <秒>]    終了コード 0 = 全 PASS
#   --quick   : Chrome シナリオを各 3 秒に短縮 (既定 5 秒)。soak シナリオは実行しない (親 e2e 規約)
#   --soak <秒> : soak シナリオ (com_soak<秒>_b256) の秒数 (既定 120 = CAB-97 完了条件)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
QUICK=0; SOAK=""
for a in "$@"; do
  case "$a" in
    --quick) QUICK=1 ;;
    --soak=*) SOAK="${a#--soak=}" ;;
    *) echo "unknown option: $a (see --help)" >&2; exit 2 ;;
  esac
done
export PATH="$HOME/.local/share/pnpm/bin:$PATH"
command -v node >/dev/null || { echo "node not found" >&2; exit 1; }

echo "[iasio] 1/2 node check (COM 面)"
bash "$HERE/build.sh" >/dev/null
node "$HERE/work/node/com_check.cjs" > "$HERE/work/node_check.json"
node -e '
const r = require(process.argv[1]);
const bad = r.checks.filter((c) => !c.ok);
console.log(`[iasio] node check: ${r.n - r.fail}/${r.n} PASS -> ${process.argv[1]}`);
if (bad.length) { for (const c of bad) console.error(`  FAIL ${c.name}: got=${c.got} want=${c.want}`); process.exit(1); }
' "$HERE/work/node_check.json"

echo "[iasio] 2/2 headless Chrome (FLEngine 呼出を模した全経路)"
SOAK_ARGS=(); [ -n "$SOAK" ] && SOAK_ARGS=(--soak "$SOAK")
node "$HERE/harness/run_com.mjs" $([ "$QUICK" = 1 ] && echo --quick) "${SOAK_ARGS[@]}" --out "$HERE/work/results_com.json"
