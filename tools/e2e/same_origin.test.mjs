// gui=wasm の同一オリジン検査の単体テスト: node --test tools/e2e/same_origin.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { resolveSameOriginUrl } from "../../src/runtime/same_origin.ts";

const base = "https://studio.example/?gui=wasm&glue=x";

test("同一オリジンの相対 URL / 絶対 URL は絶対 URL にして返す", () => {
  assert.equal(resolveSameOriginUrl("/__e2e__/gui-guest/app.js", base), "https://studio.example/__e2e__/gui-guest/app.js");
  assert.equal(resolveSameOriginUrl("https://studio.example/a/app.js", base), "https://studio.example/a/app.js");
});

test("別オリジン・data:・//host・javascript: は読まずに throw する (ネガコン)", () => {
  for (const raw of [
    "https://evil.example/x.js",
    "http://studio.example/x.js",
    "https://studio.example:8443/x.js",
    "//evil.example/x.js",
    "data:text/javascript,window.__pwned=1",
    "javascript:window.__pwned=1",
  ]) {
    assert.throws(() => resolveSameOriginUrl(raw, base), /同一オリジンの URL だけ読めます/, raw);
  }
});
