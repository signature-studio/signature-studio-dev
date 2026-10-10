#!/usr/bin/env bash
# 1 コマンド E2E: ビルド -> ローカルサーバ起動 -> headless chrome (agent-browser) で検証 -> スクリーンショット保存
#
#   bash tools/e2e/run.sh                      # preview + edge-sim を agent-browser で
#   bash tools/e2e/run.sh --driver both        # agent-browser + puppeteer-core(フォールバック) 両方
#   bash tools/e2e/run.sh --targets preview,edge-sim,dev
#   bash tools/e2e/run.sh --url https://studio.example.com   # デプロイ済み URL を検証 (ビルド/ローカルサーバ無し)
#       Access 保護時: E2E_ACCESS_CLIENT_ID / E2E_ACCESS_CLIENT_SECRET (service token)
#   E2E_SKIP_BUILD=1  ビルド省略 / E2E_REQUIRE_FL=1  fl-boot チェックを必須化
#
# 成果物: tools/e2e/work/{dist,shots,results,logs}  (gitignore 済み)
set -euo pipefail

E2E="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$E2E/../.." && pwd)"
cd "$E2E"

RUN_ARGS=()
REMOTE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --url) REMOTE="$2"; shift 2 ;;
    *) RUN_ARGS+=("$1"); shift ;;
  esac
done

step() { printf '\n## %s\n' "$*"; }

step "依存 (tools/e2e ローカル: agent-browser + puppeteer-core)"
if [[ ! -x node_modules/.bin/agent-browser ]]; then
  # agent-browser の native binary は npm パッケージ同梱 (postinstall 不要)
  npm ci --no-audit --no-fund --ignore-scripts 2>&1 | tail -3
fi
echo "agent-browser $(node_modules/.bin/agent-browser --version | awk '{print $2}')"
[[ -x /usr/bin/google-chrome || -n "${E2E_CHROME:-}" ]] || { echo "google-chrome が無い (E2E_CHROME で指定)"; exit 2; }

if [[ -n "$REMOTE" ]]; then
  step "リモート検証: $REMOTE"
  E2E_URL="$REMOTE" exec node suite/run.mjs --targets url "${RUN_ARGS[@]}"
fi

if [[ "${E2E_SKIP_BUILD:-0}" != "1" ]]; then
  step "ビルド (リポジトリ root の vite を使用。root package.json は不変)"
  if [[ ! -x "$ROOT/node_modules/.bin/vite" ]]; then
    (cd "$ROOT" && pnpm install --frozen-lockfile)
  fi
  (cd "$ROOT" && node_modules/.bin/tsc --noEmit)
  (cd "$ROOT" && node_modules/.bin/vite build --outDir tools/e2e/work/dist --emptyOutDir) 2>&1 | tail -6
  mkdir -p work/dist/__e2e__
  cp fixtures/add.wasm work/dist/__e2e__/add.wasm
fi

step "既存 Node ローダ smoke (tools/misc/loader_smoke.mjs)"
if [[ -f "$ROOT/tools/m1/build/wasm_elf.wasm" ]]; then
  (cd "$ROOT" && node tools/misc/loader_smoke.mjs) 2>&1 | tail -3
else
  echo "SKIP: tools/m1/build/wasm_elf.wasm 無し (tools/m1/m1.sh 未実行)"
fi

step "ブラウザ E2E"
exec node suite/run.mjs "${RUN_ARGS[@]}"
