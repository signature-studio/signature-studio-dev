// window.__webstudio 契約の状態遷移 単体テスト: node --test tools/e2e/webstudio_state.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { createWebstudioController, installWebstudioContract } from "../../src/runtime/webstudio_state.ts";

test("初期は booting / frames 0 / error なし", () => {
  const { contract } = createWebstudioController();
  assert.deepEqual(contract, { state: "booting", frames: 0 });
});

test("フレーム 1 枚で running、frames は単調増加", () => {
  const c = createWebstudioController();
  c.reportFrame();
  assert.equal(c.contract.state, "running");
  assert.equal(c.contract.frames, 1);
  c.setFrames(10);
  assert.equal(c.contract.frames, 10);
  c.setFrames(3);
  assert.equal(c.contract.frames, 10);
  c.setFrames(Number.NaN);
  assert.equal(c.contract.frames, 10);
});

test("frames 0 のままでは running にならない", () => {
  const c = createWebstudioController();
  c.setFrames(0);
  c.reportFrame(0);
  assert.equal(c.contract.state, "booting");
});

test("guest は setGuest まで契約に現れず、設定後は種別を保持する (test は fl-boot の PASS 条件を満たさない)", () => {
  const c = createWebstudioController();
  assert.equal("guest" in c.contract, false);
  c.setGuest("test");
  assert.equal(c.contract.guest, "test");
  c.setFrames(2);
  assert.equal(c.contract.state, "running");
  assert.equal(c.contract.guest, "test");
});

test("error は終端: 以後 running へ戻らず frames も動かない。最初の error を保持", () => {
  const c = createWebstudioController();
  c.fail(new Error("boom"));
  c.fail("second");
  c.reportFrame(5);
  assert.deepEqual(c.contract, { state: "error", frames: 0, error: "boom" });
});

test("running 後の error でも frames は保持される", () => {
  const c = createWebstudioController();
  c.reportFrame(2);
  c.fail("x");
  assert.deepEqual(c.contract, { state: "error", frames: 2, error: "x" });
});

test("install は target.__webstudio に同一オブジェクトを公開し error イベントを購読する", () => {
  const handlers = {};
  const target = { addEventListener: (n, h) => { handlers[n] = h; } };
  const c = installWebstudioContract(target);
  assert.equal(target.__webstudio, c.contract);
  assert.equal(target.__webstudio.state, "booting");
  handlers.error({ error: new Error("uncaught") });
  assert.equal(target.__webstudio.state, "error");
  assert.equal(target.__webstudio.error, "uncaught");
});
