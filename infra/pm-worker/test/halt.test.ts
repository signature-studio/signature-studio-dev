import { test } from "node:test";
import assert from "node:assert/strict";
import { loadConfig } from "../src/config.ts";
import { HALT_NOTIFY_MS, HALT_OVERDUE_MS, haltNotifyDue, haltOverdue, haltReasons, nextHalt, type Halt } from "../src/halt.ts";

// launch を止める条件 (#2795)。純関数の規則を固定する。mutation.mjs が、これらの規則を壊すと落ちることを確かめる。
const MIN = 60_000;
const T = "2026-10-14T12:00:00.000Z";
const at = (min: number) => Date.parse(T) + min * MIN;
const iso = (min: number) => new Date(at(min)).toISOString();
const NONE = { noImport: false, reviewOnly: false, stale: false };

test("既定値: IMPORT_REQUIRED は未設定のとき取り込みを求めない (#2795)。\"1\" のときだけ求める", () => {
  assert.equal(loadConfig({}, {}).importRequired, false);
  assert.equal(loadConfig({ IMPORT_REQUIRED: "0" }, {}).importRequired, false);
  assert.equal(loadConfig({ IMPORT_REQUIRED: "1" }, {}).importRequired, true);
});

test("haltReasons: 止めている条件を優先順に出す。何も止めていなければ空", () => {
  assert.deepEqual(haltReasons(NONE), []);
  assert.deepEqual(haltReasons({ ...NONE, noImport: true }), ["no-import"]);
  assert.deepEqual(haltReasons({ ...NONE, stop: "stuck-ceiling" }), ["stuck-ceiling"]);
  assert.deepEqual(haltReasons({ ...NONE, stop: "rate-guard", reviewOnly: true }), ["rate-guard", "review-only"]);
  assert.deepEqual(haltReasons({ noImport: true, stop: "rate-guard", reviewOnly: true, stale: true }), ["no-import", "rate-guard", "review-only", "stale"]);
});

test("nextHalt: 止まり始めた時刻を起点に残す。止まり続けている間は理由だけ更新する", () => {
  const first = nextHalt(undefined, ["review-only"], T) as Halt;
  assert.deepEqual(first, { since: T, reasons: ["review-only"] });
  const later = nextHalt({ ...first, notifiedAt: iso(30) }, ["stale"], iso(10)) as Halt;
  assert.equal(later.since, T, "起点は動かさない");
  assert.deepEqual(later.reasons, ["stale"]);
  assert.equal(later.notifiedAt, iso(30), "通知済みの印は残す");
});

test("nextHalt: 条件が 0 になったら区間を消す。次の停止の起点に使い回さない", () => {
  const prev = { since: T, reasons: ["review-only"] };
  assert.equal(nextHalt(prev, [], iso(40)), undefined);
  const again = nextHalt(undefined, ["review-only"], iso(50)) as Halt;
  assert.equal(again.since, iso(50));
  assert.equal(again.notifiedAt, undefined);
});

test("haltOverdue: 15 分ちょうどから true。ready と room が両方あるときだけ", () => {
  assert.equal(HALT_OVERDUE_MS, 15 * MIN);
  assert.equal(haltOverdue(T, at(15) - 1, 3, 5), false, "15 分未満は false");
  assert.equal(haltOverdue(T, at(15), 3, 5), true, "15 分ちょうどで true");
  assert.equal(haltOverdue(T, at(60), 0, 5), false, "着手待ちが無ければ false");
  assert.equal(haltOverdue(T, at(60), 3, 0), false, "空き枠が無ければ false");
  assert.equal(haltOverdue(undefined, at(60), 3, 5), false, "停止していなければ false");
});

test("haltNotifyDue: 30 分ちょうどで 1 回。同じ停止区間では、通知済みなら送らない", () => {
  assert.equal(HALT_NOTIFY_MS, 30 * MIN);
  const h = { since: T, reasons: ["no-import"] };
  assert.equal(haltNotifyDue(h, at(30) - 1), false, "30 分未満は送らない");
  assert.equal(haltNotifyDue(h, at(30)), true, "30 分ちょうどで送る");
  assert.equal(haltNotifyDue({ ...h, notifiedAt: new Date(at(30)).toISOString() }, at(90)), false, "通知済みなら、何分たっても送らない");
  assert.equal(haltNotifyDue(undefined, at(90)), false, "停止していなければ送らない");
});
