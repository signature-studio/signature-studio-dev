import { test } from "node:test";
import assert from "node:assert/strict";
import { signBody, verifySignature } from "../src/hmac.ts";

const SECRET = "test-secret";
const BODY = '{"action":"opened","issue":{"number":1}}';

test("正例: 正しい署名は通る", () => {
  assert.equal(verifySignature(SECRET, BODY, signBody(SECRET, BODY)), true);
});

test("負例: 署名ヘッダが無い (null / undefined / 空) は false", () => {
  assert.equal(verifySignature(SECRET, BODY, null), false);
  assert.equal(verifySignature(SECRET, BODY, undefined), false);
  assert.equal(verifySignature(SECRET, BODY, ""), false);
});

test("負例: sha256= 接頭辞が無い形式は false", () => {
  const hex = signBody(SECRET, BODY).slice("sha256=".length);
  assert.equal(verifySignature(SECRET, BODY, hex), false);
  assert.equal(verifySignature(SECRET, BODY, "sha1=" + hex), false);
});

test("負例: 秘密鍵が違う署名は false", () => {
  assert.equal(verifySignature(SECRET, BODY, signBody("other-secret", BODY)), false);
});

test("負例: 長さの違う署名は false (比較前に弾く)", () => {
  const good = signBody(SECRET, BODY);
  assert.equal(verifySignature(SECRET, BODY, good.slice(0, -2)), false);
  assert.equal(verifySignature(SECRET, BODY, good + "00"), false);
});

test("負例: 改ざんされた本文は false", () => {
  const sig = signBody(SECRET, BODY);
  assert.equal(verifySignature(SECRET, BODY.replace("opened", "closed"), sig), false);
  assert.equal(verifySignature(SECRET, BODY + " ", sig), false);
});

test("秘密鍵が空なら、どの署名も通さない", () => {
  assert.equal(verifySignature("", BODY, signBody("", BODY)), false);
});
