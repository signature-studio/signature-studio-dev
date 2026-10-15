// 区分の継承 (#3973): 自身に prio の明示が無い issue は、本文の『親: #N』の親 (open) が prio:critical なら critical。
// 規則: 自身の明示 > 親の明示 (critical だけ継承) > 親に明示が無いときの祖父母の明示 (critical だけ)。closed・無い・自己参照・循環は継承しない。
import { test } from "node:test";
import assert from "node:assert/strict";
import { countRunsByPrio } from "../src/active.ts";
import { effectivePrioMap, noPrCooldownMs, planLaunch, sortReady, type PrioIssue, type ReadyIssue } from "../src/launch.ts";
import type { RunState } from "../src/webhook.ts";
import { configuredApp, issuePayload, markFresh, send } from "./helpers.ts";

const I = (number: number, labels: string[] = [], body = "", state: "open" | "closed" = "open"): PrioIssue => ({ number, state, labels, body });
const child = (number: number, parent: number, labels: string[] = []): PrioIssue => I(number, labels, `親: #${parent}`);

test("規則 1: 親 (open) が prio:critical なら、明示の無い子は critical。親が無印なら normal", () => {
  const m = effectivePrioMap([I(10, ["prio:critical"]), child(11, 10), I(20), child(21, 20)]);
  assert.equal(m.get(10), "critical");
  assert.equal(m.get(11), "critical");
  assert.equal(m.get(21), "normal");
});

test("規則 2: 子の明示が優先する。親が critical でも子が prio:low なら low、親が low でも子が prio:critical なら critical", () => {
  const m = effectivePrioMap([I(10, ["prio:critical"]), child(11, 10, ["prio:low"]), I(20, ["prio:low"]), child(21, 20, ["prio:critical"]), child(22, 20)]);
  assert.equal(m.get(11), "low");
  assert.equal(m.get(21), "critical");
  assert.equal(m.get(22), "normal", "親が low の子は継承しない (low は継承しない)");
});

test("規則 3: 親に明示が無ければ祖父母 (open) の prio:critical を継承する。曾祖父母は継承しない", () => {
  const m = effectivePrioMap([I(1, ["prio:critical"]), child(2, 1), child(3, 2), child(4, 3)]);
  assert.equal(m.get(2), "critical", "親の明示 critical");
  assert.equal(m.get(3), "critical", "親は無印・祖父母が critical");
  assert.equal(m.get(4), "normal", "曾祖父母 (1) は見ない。親 3 は無印で、祖父母 2 は無印 (1 の継承は引き継がない)");
});

test("規則 4: 親が closed・無い・自己参照・循環なら継承しない (normal)。祖父母が closed でも継承しない", () => {
  assert.equal(effectivePrioMap([I(1, ["prio:critical"], "", "closed"), child(2, 1)]).get(2), "normal", "親が closed");
  assert.equal(effectivePrioMap([I(1, ["prio:critical"], "", "closed"), child(2, 1), child(3, 2)]).get(3), "normal", "祖父母が closed");
  assert.equal(effectivePrioMap([child(2, 99)]).get(2), "normal", "親が無い");
  assert.equal(effectivePrioMap([I(5, [], "親: #5")]).get(5), "normal", "自己参照");
  const cyc = effectivePrioMap([I(1, [], "親: #2"), I(2, [], "親: #1"), I(3, ["prio:critical"]), child(4, 3)]);
  assert.equal(cyc.get(1), "normal");
  assert.equal(cyc.get(2), "normal");
  assert.equal(cyc.get(4), "critical", "循環の外の継承は従来どおり");
  assert.equal(effectivePrioMap([I(1, ["prio:low"]), child(2, 1)]).get(2), "normal", "親が low なら継承しない");
  assert.equal(effectivePrioMap([I(1, ["prio:critical"]), I(2, ["prio:low"], "親: #1"), child(3, 2)]).get(3), "normal", "親 (2) が明示 low なら、祖父母 (1) が critical でも継承しない");
});

test("回帰 (#3748 の形): 親 #3478 (critical・open) の子 #3748 は、ラベル無しでも先頭に並ぶ。labels だけの読みでは番号順に埋もれる", () => {
  const prio = effectivePrioMap([I(3478, ["prio:critical"]), child(3748, 3478), I(3500), I(3501), I(3502)]);
  const ready: ReadyIssue[] = [3500, 3501, 3502, 3748].map((n) => ({ n, title: `[X-${n}] t`, blocksCount: 0, prio: prio.get(n) }));
  assert.deepEqual(sortReady(ready).map((r) => r.n), [3748, 3500, 3501, 3502]);
  assert.deepEqual(planLaunch({ ready, relaunch: [], active: 0, target: 50, batch: 25 }).picks, [3748, 3500, 3501, 3502]);
  // 対照 (継承を見ない読み): labels だけなら 3748 は最後。
  assert.deepEqual(sortReady(ready.map((r) => ({ n: r.n, title: r.title, blocksCount: 0 }))).map((r) => r.n), [3500, 3501, 3502, 3748]);
});

test("countRunsByPrio: 継承で critical になった子の run は critical に数える", () => {
  const prio = effectivePrioMap([I(10, ["prio:critical"]), child(11, 10), I(12)]);
  const issues = [11, 12].map((n) => ({ title: `[X-${n}] t`, prio: prio.get(n) ?? "normal" }));
  const run = (id: number, title: string) => ({ id, event: "issue_comment", title, status: "in_progress", conclusion: null, updatedAt: "2026-10-14T11:00:00Z" }) as RunState;
  assert.deepEqual(countRunsByPrio([run(1, "[X-11] t"), run(2, "[X-12] t")], issues), { critical: 1, normal: 1, low: 0 });
});

test("cooldown: 継承で critical になった子の oc:no-pr は半分の間隔 (区分の値で決まる)", () => {
  const prio = effectivePrioMap([I(10, ["prio:critical"]), child(11, 10)]);
  assert.equal(noPrCooldownMs(prio.get(11) ?? "normal", 6), 3 * 3_600_000);
});

test("engine (#3973): 親 #3478 (critical) の子 #3748 はラベル無しでも先頭で launch 対象になり、/status の ready_by_prio に critical として数える", async () => {
  const ctx = await configuredApp();
  const seed = async (n: number, o: Parameters<typeof issuePayload>[1] = {}) => assert.equal((await send(ctx.app, "issues", issuePayload(n, o))).status, 202);
  await seed(3478, { labels: ["prio:critical"], title: "[WIN-26] 親" });
  await seed(3748, { title: "[WIN-39] 子", body: "親: #3478\n" });
  for (const n of [3500, 3501, 3502]) await seed(n);
  await markFresh(ctx);
  assert.deepEqual(ctx.app.engine.plan().picks.map((p) => p.n), [3748, 3500, 3501, 3502]);
  assert.deepEqual((ctx.app.engine.status() as any).ready_by_prio, { critical: 1, normal: 3, low: 0 });
});
