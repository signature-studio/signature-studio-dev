#!/usr/bin/env node
// tools/e2e の checks.mjs "edge-policy" と同じ検査 (policy の CORP/Cache-Control/Content-Type と 404) を実 URL に対して行う。
// 違いは /index.html: Static Assets は 307 -> / を返す (実測) ので、リダイレクトを許容して Location を検査する。
//   node deploy/probe/policy-check.mjs <url> [token.json]
import { readFileSync } from "node:fs";
import { applyRequestRewrite, applyResponseHeaders, contentTypeFor, loadPolicy } from "../lib/policy.mjs";

const [base, tokFile] = process.argv.slice(2);
const policy = loadPolicy();
const H = { "Accept-Encoding": "br, zstd, gzip" };
if (tokFile) {
  const t = JSON.parse(readFileSync(tokFile, "utf8"));
  H["CF-Access-Client-Id"] = t.client_id;
  H["CF-Access-Client-Secret"] = t.client_secret;
}
const get = async (p, init = {}) => {
  const r = await fetch(base + p, { headers: H, redirect: "manual", ...init });
  await r.body?.cancel();
  return r;
};
const html = await (await fetch(base + "/", { headers: H })).text();
const jsPath = /src="(\/assets\/[^"]+\.js)"/.exec(html)?.[1];
let bad = 0;
const rep = (ok, msg) => { if (!ok) bad++; console.log(`${ok ? "ok " : "NG "} ${msg}`); };
rep(!!jsPath, `index.html から /assets/*.js を取得: ${jsPath}`);
const idx = await get("/index.html");
rep(idx.status === 307 && new URL(idx.headers.get("location"), base).pathname === "/", `/index.html -> ${idx.status} Location=${idx.headers.get("location")} (e2e 側は 307 を許容して / に統一する必要あり)`);
for (const p of ["/", jsPath, "/worklets/dummy-worklet.js", "/__e2e__/add.wasm"]) {
  const r = await get(p);
  if (r.status !== 200) { rep(false, `${p} status ${r.status}`); continue; }
  const eff = applyRequestRewrite(policy, p);
  const want = applyResponseHeaders(policy, { path: eff, status: 200 }, {});
  const diffs = Object.entries(want).filter(([k, v]) => r.headers.get(k) !== v).map(([k, v]) => `${k}: got=${JSON.stringify(r.headers.get(k))} want=${JSON.stringify(v)}`);
  const wantCt = contentTypeFor(policy, eff);
  if (r.headers.get("content-type") !== wantCt) diffs.push(`content-type: got=${JSON.stringify(r.headers.get("content-type"))} want=${JSON.stringify(wantCt)}`);
  rep(!diffs.length, `${p} ${diffs.join(" | ") || "policy 一致"} (ce=${r.headers.get("content-encoding")})`);
}
const r404 = await get("/__no_such_object__");
rep(r404.status === 404, `/__no_such_object__ -> ${r404.status}`);
process.exit(bad ? 1 : 0);
