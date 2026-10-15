// remote (url) の edge-policy: /index.html の 307 -> / 判定の単体テスト: node --test tools/e2e/edge_policy.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { assertIndexHtmlRedirect } from "./suite/checks.mjs";

const base = "https://signature-studio.example.workers.dev";
const res = (status, location) => new Response(null, { status, headers: location === undefined ? {} : { location } });

test("Static Assets の /index.html 307 -> / を PASS (相対・絶対の Location)", () => {
  assert.doesNotThrow(() => assertIndexHtmlRedirect(res(307, "/"), base));
  assert.doesNotThrow(() => assertIndexHtmlRedirect(res(307, `${base}/`), base));
});

test("Access ログインの 302 は FAIL (3xx を正常扱いしない)", () => {
  assert.throws(() => assertIndexHtmlRedirect(res(302, "https://team.cloudflareaccess.com/cdn-cgi/access/login"), base), /期待 307/);
});

test("307 でも Location が / 以外なら FAIL", () => {
  assert.throws(() => assertIndexHtmlRedirect(res(307, "/index"), base), /Location/);
});

test("307 で Location が無ければ FAIL", () => {
  assert.throws(() => assertIndexHtmlRedirect(res(307), base), /Location/);
});
