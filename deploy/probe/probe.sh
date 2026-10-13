#!/usr/bin/env bash
# 一時 probe: stage -> create(closed) -> Access(worker 型) -> open -> 実エッジ検証 -> cleanup を再現する (CAB-35 本番と同じ手順を別名で通す)。
#   bash deploy/probe/probe.sh                  # 完了後に必ず probe-cleanup.sh (失敗/中断時も trap で実行)
#   KEEP=1 bash deploy/probe/probe.sh           # cleanup しない (手動: bash deploy/probe/probe-cleanup.sh)
#   PROBE_APP=0 ...  アプリ dist (vite build) を載せない / PROBE_BIG_WASM=<path> 大物 wasm (既定 tools/perf/work/huge/k100.wasm 314MB、無ければ 60MB 合成)
#   PROBE_E2E=1 ...  tools/e2e/run.sh --url (puppeteer driver) も実行 (tools/e2e/work/results/url-puppeteer.json を書く)
# 作成物は全て signature-studio-deploy-probe-<suffix> (PROBE_SUFFIX, 既定 a)。本番名 signature-studio には触れない。
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/../scripts/lib.sh"
SUF="${PROBE_SUFFIX:-a}"
NAME="signature-studio-deploy-probe-$SUF"
[[ "$NAME" =~ ^signature-studio-deploy-probe-[a-z0-9]+$ ]] || { echo "REFUSE: $NAME"; exit 3; }
export WORKER_NAME="$NAME" APPLY=1
W="$DEPLOY_DIR/work"; mkdir -p "$W/probe-$SUF"
LOG="$W/probe-$SUF/run.log"; : > "$LOG"
EMAIL="${ACCESS_ALLOW_EMAILS:-$(cf auth whoami | node -e 'console.log(JSON.parse(require("fs").readFileSync(0,"utf8")).email)')}"; export ACCESS_ALLOW_EMAILS="$EMAIL"
SUB="${WORKERS_SUBDOMAIN:-pycabbage}"
T0=$SECONDS; lap() { printf '%-34s %4ss\n' "$1" "$((SECONDS-T0))" | tee -a "$LOG"; T0=$SECONDS; }
cleanup() {
  [[ "${KEEP:-0}" == 1 ]] && { echo "KEEP=1: 残置 (cleanup: bash deploy/probe/probe-cleanup.sh)"; return; }
  bash "$HERE/probe-cleanup.sh" "$W/probe-baseline.json" 2>&1 | tee -a "$LOG"; lap "cleanup"
}
trap cleanup EXIT

bash "$HERE/snapshot.sh" "$W/probe-baseline.json" | tee -a "$LOG"

# --- 配備物: アプリ dist (任意) + probe ページ + 大物 wasm
SRC="$W/probe-$SUF/src"; rm -rf "$SRC"; mkdir -p "$SRC/__probe__/ce" "$SRC/wasm"
if [[ "${PROBE_APP:-1}" == 1 ]]; then
  APP="$W/app-dist"
  if [[ ! -d "$APP" || "${PROBE_REBUILD:-0}" == 1 ]]; then
    (cd "$REPO_ROOT" && node_modules/.bin/vite build --outDir "$APP" --emptyOutDir 2>&1 | tail -3) | tee -a "$LOG"
    mkdir -p "$APP/__e2e__" && cp "$REPO_ROOT/tools/e2e/fixtures/add.wasm" "$APP/__e2e__/add.wasm"
  fi
  cp -r "$APP"/. "$SRC"/
else
  echo '<!doctype html><title>probe</title>' > "$SRC/index.html"
fi
cp "$HERE"/site/* "$SRC/__probe__/"; cp "$DEPLOY_DIR/client/chunked.mjs" "$SRC/__probe__/"
node -e 'require("fs").writeFileSync(process.argv[1], require("zlib").brotliCompressSync(Buffer.from("hello from static assets\n")))' "$SRC/__probe__/ce/hello.br"
BIG="${PROBE_BIG_WASM:-$REPO_ROOT/tools/perf/work/huge/k100.wasm}"
[[ -f "$BIG" ]] || { BIG="$W/probe-$SUF/synth-60MB.wasm"; node "$HERE/make-wasm.mjs" 60 "$BIG"; }
h8() { sha256sum "$1" | cut -c1-8; }
cp "$REPO_ROOT/tools/e2e/fixtures/add.wasm" "$W/probe-$SUF/small.wasm"
node -e '
const [out, big, small, h1, h2] = process.argv.slice(1);
require("fs").writeFileSync(out, JSON.stringify({ version: 1, files: [
  { path: `wasm/probe-big.${h1}.wasm`, src: big },
  { path: `wasm/probe-small.${h2}.wasm`, src: small },
] }));' "$W/probe-$SUF/manifest.json" "$BIG" "$W/probe-$SUF/small.wasm" "$(h8 "$BIG")" "$(h8 "$W/probe-$SUF/small.wasm")"
echo "big wasm: $BIG ($(stat -c %s "$BIG") B)" | tee -a "$LOG"

step "stage"
node "$DEPLOY_DIR/scripts/05-stage.mjs" --src "$SRC" --manifest "$W/probe-$SUF/manifest.json" --skip-notices-gate 2>&1 | tee -a "$LOG" | tail -22
mkdir -p "$W/site/__probe__/ct"; echo '<!doctype html>' > "$W/site/__probe__/ct/a.html"; echo 'export {}' > "$W/site/__probe__/ct/a.js"; echo 'x' > "$W/site/__probe__/ct/a.css"
# probe only: _headers で Content-Encoding / Content-Type を上書き・付与できるか (edge-facts.sh が採取)
printf '\n/__probe__/ce/*\n  Content-Encoding: br\n\n/__probe__/ct/a.html\n  Content-Type: text/html; charset=utf-8\n\n/__probe__/ct/a.js\n  Content-Type: text/javascript; charset=utf-8\n\n/__probe__/ct/*.css\n  Content-Type: text/css; charset=utf-8\n' >> "$W/site/_headers"
lap "stage"

step "deploy closed (placeholder, workers.dev 無し)"
node "$DEPLOY_DIR/scripts/20-worker.mjs" --phase closed 2>&1 | tee -a "$LOG" | grep -E "Deployed|Uploaded|Current Version|rror" ; [[ ${PIPESTATUS[0]} == 0 ]] || { echo "deploy closed 失敗"; exit 1; }
lap "deploy closed"
echo "closed 状態の URL 応答 (期待: 404 等で到達不可): $(curl -s -o /dev/null -w '%{http_code}' "https://$NAME.$SUB.workers.dev/")" | tee -a "$LOG"

step "Access (worker 型 + service token)"
node "$DEPLOY_DIR/scripts/40-access.mjs" --apply 2>&1 | tee -a "$LOG"; [[ ${PIPESTATUS[0]} == 0 ]] || { echo "access 失敗"; exit 1; }
lap "access"

step "deploy open (placeholder で workers.dev 有効化 -> 無認証 302 待ち)"
node "$DEPLOY_DIR/scripts/20-worker.mjs" --phase open 2>&1 | tee -a "$LOG" | grep -E "Deployed|URL:|公開直後|rror"; [[ ${PIPESTATUS[0]} == 0 ]] || { echo "deploy open 失敗"; exit 1; }
URL="$(cat "$W/$NAME.url")"
lap "open"

step "deploy release (本物の asset)"
node "$DEPLOY_DIR/scripts/20-worker.mjs" --phase release 2>&1 | tee -a "$LOG" | grep -E "Uploaded|Success|Deployed|URL:|rror"; [[ ${PIPESTATUS[0]} == 0 ]] || { echo "deploy release 失敗"; exit 1; }
lap "release"

step "verify (302 / ヘッダ)"
bash "$DEPLOY_DIR/scripts/90-verify.sh" --no-e2e 2>&1 | tee -a "$LOG"; [[ ${PIPESTATUS[0]} == 0 ]] || { echo "verify 失敗"; exit 1; }
lap "verify"

TOK="$W/secrets/$NAME-e2e.json"
step "edge facts"
bash "$HERE/edge-facts.sh" "$URL" "$TOK" 2>&1 | tee "$W/probe-$SUF/edge-facts.txt" | tee -a "$LOG"

step "policy 突合 (e2e edge-policy 相当, /index.html は 307 許容)"
node "$HERE/policy-check.mjs" "$URL" "$TOK" 2>&1 | tee "$W/probe-$SUF/policy-check.txt" | tee -a "$LOG"

step "browser probe (isolation / SAB / Worker / AudioWorklet / 連結 wasm compileStreaming)"
node "$HERE/run.mjs" "$URL/__probe__/" --token "$TOK" --out "$W/probe-$SUF/browser.json" 2>&1 | tee -a "$LOG" | tail -70
RC=${PIPESTATUS[0]}
lap "browser"

if [[ "${PROBE_E2E:-0}" == 1 ]]; then
  step "tools/e2e (--url, agent-browser + puppeteer)"
  # tools/e2e/work は他担当の検収と共有。url-* の既存成果物を退避し、実行後に復元・自分の成果物は deploy/work/ へ移す
  ER="$REPO_ROOT/tools/e2e/work"; BK="$W/probe-$SUF/e2e-backup"; OUTD="$W/probe-$SUF/e2e-results"; mkdir -p "$BK" "$OUTD"
  cp -p "$ER"/results/url-* "$ER"/shots/url-* "$BK"/ 2>/dev/null
  E2E_ACCESS_CLIENT_ID="$(node -e 'console.log(JSON.parse(require("fs").readFileSync(process.argv[1])).client_id)' "$TOK")" \
  E2E_ACCESS_CLIENT_SECRET="$(node -e 'console.log(JSON.parse(require("fs").readFileSync(process.argv[1])).client_secret)' "$TOK")" \
    bash "$REPO_ROOT/tools/e2e/run.sh" --url "$URL" --driver both 2>&1 | tee -a "$LOG" | tail -40
  cp -p "$ER"/results/url-* "$ER"/shots/url-* "$OUTD"/ 2>/dev/null
  rm -f "$ER"/results/url-* "$ER"/shots/url-*
  for f in "$BK"/url-*; do [[ -f "$f" ]] || continue; case "$f" in *.json) cp -p "$f" "$ER/results/";; *) cp -p "$f" "$ER/shots/";; esac; done
  lap "e2e"
fi
exit "$RC"
