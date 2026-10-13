#!/usr/bin/env bash
# 1 コマンド E2E (#63): 生産側 manifest -> 05-stage (--manifest) -> release.json 突合 -> edge-sim で wasm-load (MIME application/wasm)
#   bash tools/assets/deploy-manifest/e2e.sh
# 入力は合成 wasm (tools/e2e/fixtures/add.wasm + deploy/probe/make-wasm.mjs の 1MiB wasm) のみ。FL/プラグイン由来バイトは使わない。
# deploy.sh 本体は cf 認証 (00-preflight) を要するため CI では呼ばず、同スクリプトが最初に呼ぶ 05-stage を直接実行する。
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
W="$HERE/work"
rm -rf "$W"; mkdir -p "$W/in/wasm" "$W/in/data"
cd "$ROOT"

echo "## unit"
node --test tools/assets/deploy-manifest/make-manifest.test.mjs 2>&1 | grep -E '^# (tests|pass|fail)'

echo "## 入力 (合成)"
cp tools/e2e/fixtures/add.wasm "$W/in/wasm/add.wasm"
node deploy/probe/make-wasm.mjs 1 "$W/in/wasm/big.wasm"
head -c 4096 /dev/urandom > "$W/in/data/blob.bin"
# ブート manifest (runtime 形式): hash 名は make-manifest が付けるため、既にハッシュ名のものを 1 つ用意して突合も通す
cp tools/e2e/fixtures/add.wasm "$W/in/wasm/pre.0123456789ab.wasm"
node -e '
const fs=require("fs"),c=require("crypto"),d=process.argv[1];
const b=fs.readFileSync(d+"/wasm/pre.0123456789ab.wasm");
fs.writeFileSync(d+"/wasm/manifest.json",JSON.stringify({version:1,entries:[{id:"pre",file:"pre.0123456789ab.wasm",sha256:c.createHash("sha256").update(b).digest("hex"),bytes:b.length}]}));
' "$W/in"

echo "## make-manifest"
node tools/assets/deploy-manifest/make-manifest.mjs --out "$W/out" --add "wasm=$W/in/wasm" --add "data=$W/in/data"
cat "$W/out/deploy-manifest.json"

echo "## アプリ dist (vite build) + manifest 資産を 05-stage へ"
node_modules/.bin/vite build --outDir "$W/dist" --emptyOutDir 2>&1 | tail -2
mkdir -p "$W/dist/__e2e__"; cp tools/e2e/fixtures/add.wasm "$W/dist/__e2e__/add.wasm"
node deploy/scripts/05-stage.mjs --src "$W/dist" --manifest "$W/out/deploy-manifest.json" --out "$W/site" --skip-release-guard | tee "$W/stage.json" | head -8

echo "## release.json 突合 (別経路の sha256)"
node tools/assets/deploy-manifest/verify-release.mjs "$W/out/deploy-manifest.json" "$W/site/release.json"

echo "## edge-sim で配信し MIME / 内容を検査 (tools/e2e/suite の policy 準拠サーバ)"
node "$HERE/serve-check.mjs" "$W/site" "$W/out/deploy-manifest.json"

echo "## tools/e2e/run.sh --url (wasm-load: MIME application/wasm) を同じ site に対して実行"
node "$HERE/serve-check.mjs" "$W/site" "$W/out/deploy-manifest.json" --serve > "$W/serve.url" &
SERVE_PID=$!
trap 'kill $SERVE_PID 2>/dev/null || true' EXIT
for _ in $(seq 1 50); do [[ -s "$W/serve.url" ]] && break; sleep 0.1; done
bash tools/e2e/run.sh --url "$(cat "$W/serve.url")" | tee "$W/run-url.log" | grep -E '^(PASS|FAIL|SKIP|SUMMARY)'
grep -q 'FAIL=0' "$W/run-url.log"
grep -q 'PASS wasm-load.*application/wasm' "$W/run-url.log"
echo "E2E OK"
