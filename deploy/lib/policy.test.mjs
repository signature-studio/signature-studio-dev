// node --test deploy/lib/policy.test.mjs
import assert from "node:assert/strict";
import test from "node:test";
import {
  applyRequestRewrite,
  applyResponseHeaders,
  buildCacheRules,
  buildCompressionRules,
  buildRewriteRules,
  buildTransformRules,
  contentTypeFor,
  expression,
  loadPolicy,
  refPrefix,
} from "./policy.mjs";

const policy = loadPolicy();
const H = "studio.example.com";

test("isolation ヘッダは全パス/全ステータスに付く", () => {
  for (const [p, status] of [["/", 200], ["/x/y.wasm", 200], ["/nope", 404]]) {
    const h = applyResponseHeaders(policy, { path: p, status }, {});
    assert.equal(h["Cross-Origin-Opener-Policy"], "same-origin");
    assert.equal(h["Cross-Origin-Embedder-Policy"], "require-corp");
    assert.equal(h["Cross-Origin-Resource-Policy"], "same-origin");
  }
});

test("Cache-Control: immutable / document / 既定 / 404 は付けない", () => {
  const cc = (p, s = 200) => applyResponseHeaders(policy, { path: p, status: s }, {})["Cache-Control"];
  assert.equal(cc("/assets/index-AbCd1234.js"), "public, max-age=31536000, immutable");
  assert.equal(cc("/wasm/fl.0123abcd.wasm"), "public, max-age=31536000, immutable");
  assert.equal(cc("/index.html"), "no-cache");
  assert.equal(cc("/wasm/manifest.json"), "no-cache", "ブート manifest は /wasm/ 配下でも可変");
  assert.equal(cc("/"), "no-cache");
  assert.equal(cc("/worklets/a.js"), "public, max-age=300, must-revalidate");
  assert.equal(cc("/assets/x.js", 404), undefined);
});

test("cache rule: document は immutable prefix より後勝ちでエッジ TTL 短縮", () => {
  const rules = buildCacheRules(policy, H);
  assert.deepEqual(rules.map((r) => r.ref.split("_cache_")[1]), ["cache_default", "cache_immutable", "cache_document"]);
  assert.equal(rules[2].action_parameters.edge_ttl.default, 60);
});

test("directory index rewrite", () => {
  assert.equal(applyRequestRewrite(policy, "/"), "/index.html");
  assert.equal(applyRequestRewrite(policy, "/a/"), "/a/index.html");
  assert.equal(applyRequestRewrite(policy, "/a.js"), "/a.js");
});

test("content-type: wasm は application/wasm", () => {
  assert.equal(contentTypeFor(policy, "wasm/x.wasm"), "application/wasm");
  assert.equal(contentTypeFor(policy, "unknown.xyz"), "application/octet-stream");
});

test("expression 生成と全 rule の ref/host スコープ", () => {
  assert.equal(
    expression({ path: ["/", "/index.html"] }, H),
    '(http.host eq "studio.example.com") and (http.request.uri.path in {"/" "/index.html"})',
  );
  const all = [
    ...buildRewriteRules(policy, H),
    ...buildTransformRules(policy, H),
    ...buildCacheRules(policy, H),
    ...buildCompressionRules(policy, H),
  ];
  const refs = new Set();
  for (const r of all) {
    assert.ok(r.expression.startsWith(`(http.host eq "${H}")`), r.ref);
    assert.ok(r.ref.startsWith(refPrefix(H)), r.ref);
    refs.add(r.ref);
  }
  assert.equal(refs.size, all.length, "ref は一意");
});
