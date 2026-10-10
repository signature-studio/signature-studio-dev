#!/usr/bin/env bash
# pol-test.sh — edge-policy.json -> _headers (headers-from-policy.mjs) を使い捨て Worker にデプロイし、実エッジの応答ヘッダを policy 評価結果と突合する
set -euo pipefail
export PATH="$HOME/.local/share/pnpm/bin:$HOME/.bun/bin:$PATH"
cd "$(dirname "$0")/.."
D=work/dist-pol; rm -rf $D; mkdir -p $D/wasm $D/assets $D/data/c/ab $D/worklets
echo '<!doctype html>pol' > $D/index.html; echo '{}' > $D/release.json; echo '{}' > $D/wasm/manifest.json
printf '\0asm\1\0\0\0' > $D/wasm/a.wasm; echo 'x' > $D/assets/app.js; echo x > $D/data/c/ab/abcdef.raw; echo x > $D/worklets/w.js; echo x > $D/other.txt
node headers-from-policy.mjs --check --out $D/_headers 2>work/pol-check.json || { cat work/pol-check.json; exit 1; }
URL=$(cd probe/worker-pol && bunx wrangler deploy 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | grep -o 'https://signature-studio-hosting-probe-pol\.[a-z0-9-]*\.workers\.dev' | head -1)
echo "$URL"
for i in $(seq 1 60); do curl -sI "$URL/worklets/w.js" | grep -qi 'max-age=0' && curl -sI "$URL/" | grep -qi 'no-cache' && break; sleep 3; done   # _headers 反映待ち (30〜60 秒かかることがある)
node - "$URL" <<'J'
const base = process.argv[2];
const policy = JSON.parse((await import('node:fs')).readFileSync('../../deploy/config/edge-policy.json', 'utf8'));
const { matches } = await import('../../deploy/lib/policy.mjs');
const equivalent = (k, got, want) => got === want || (k === 'cache-control' && ((want === 'no-cache' && /(^|,\s*)no-cache/.test(got ?? '')) || (want === 'public, max-age=300, must-revalidate' && got === 'public, max-age=0, must-revalidate')));
const paths = ['/', '/release.json', '/wasm/manifest.json', '/wasm/a.wasm', '/assets/app.js', '/data/c/ab/abcdef.raw', '/worklets/w.js', '/other.txt'];
let bad = 0;
for (const p of paths) {
  const r = await fetch(base + p, { redirect: 'manual' });
  const exp = {};
  for (const x of policy.responseHeaders) if (matches({ ...x.match, status: undefined }, { path: p, status: 200 })) for (const [k, v] of Object.entries(x.set)) exp[k.toLowerCase()] = v;
  const got = Object.fromEntries(Object.keys(exp).map((k) => [k, r.headers.get(k)]));
  const diff = Object.keys(exp).filter((k) => !equivalent(k, got[k], exp[k]));
  if (diff.length) bad++;
  console.log(diff.length ? 'NG' : 'ok', r.status, p, r.headers.get('cache-control'), diff.map((k) => `${k}: got=${JSON.stringify(got[k])} want=${JSON.stringify(exp[k])}`).join(' | '));
}
process.exit(bad ? 1 : 0);
J
