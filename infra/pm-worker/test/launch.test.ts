import { test } from "node:test";
import assert from "node:assert/strict";
import {
  ALLOW_ARTS,
  bodyArtLine,
  buildLaunchBody,
  defaultArtLine,
  inferArtifacts,
  noPrCooldownMs,
  planLaunch,
  prioOf,
  sortReady,
  validateArtLine,
} from "../src/launch.ts";

test("素材行: allowlist 内の名前だけ通す", () => {
  assert.equal(validateArtLine("oc_artifacts: fl-win64 toolchain-retdec"), true);
  assert.equal(validateArtLine("oc_artifacts: fl-win64 evil-thing"), false);
  assert.equal(validateArtLine("oc_artifacts: fl-win64 ../../etc"), false);
  assert.equal(validateArtLine("fl-win64"), false);
  assert.equal(validateArtLine("oc_artifacts:"), false);
});

test("infer は必ず allowlist 内の素材だけを返す", () => {
  const titles = [
    "[CI-1] plain",
    "[SR-3] Serum2 plugin",
    "[MX-2] MassiveX",
    "[KH-1] kilohearts",
    "[FA-1] fresh air",
    "[M11-4] boot survey",
    "[LIFT-2] liftlib icall",
    "[GUI-1] shim",
    "[PLG-9] ott",
    "[T-SH-13] mac dylib",
  ];
  for (const t of titles) {
    const line = inferArtifacts(t, []);
    assert.equal(validateArtLine(line), true, `${t} -> ${line}`);
  }
});

test("テンプレート: 固定文 + 検証済みの素材行のみ。不正な素材行は例外", () => {
  const body = buildLaunchBody("oc_artifacts: fl-win64 toolchain-emsdk");
  assert.ok(body.startsWith("/oc oc_actions_allow_write\noc_artifacts: fl-win64 toolchain-emsdk\n"));
  assert.ok(body.endsWith("\n"));
  assert.ok(body.includes("1 issue = 1 run"));
  assert.throws(() => buildLaunchBody("oc_artifacts: fl-win64 `rm -rf /`"));
  assert.throws(() => buildLaunchBody("oc_artifacts: nope"));
});

test("並び順: 被ブロック数の多い順、次に『任意』でない順、次に番号順", () => {
  const sorted = sortReady([
    { n: 5, title: "[A-1] 任意 x", blocksCount: 0 },
    { n: 9, title: "[A-2] y", blocksCount: 0 },
    { n: 3, title: "[A-3] z", blocksCount: 0 },
    { n: 7, title: "[A-4] w", blocksCount: 2 },
  ]);
  assert.deepEqual(sorted.map((r) => r.n), [7, 3, 9, 5]);
});

test("区分: prio:critical > prio:low、どちらも無ければ normal。両方付いたら critical", () => {
  assert.equal(prioOf(["prio:critical"]), "critical");
  assert.equal(prioOf(["prio:low"]), "low");
  assert.equal(prioOf(["oc:no-pr"]), "normal");
  assert.equal(prioOf([]), "normal");
  assert.equal(prioOf(["prio:low", "prio:critical"]), "critical");
});

test("並び順 (区分): critical を先頭、low を末尾にし、同じ区分の中は被ブロック数・『任意』・番号の順", () => {
  const sorted = sortReady([
    { n: 1, title: "[A-1] low", blocksCount: 9, labels: ["prio:low"] },
    { n: 2, title: "[A-2] 任意 normal", blocksCount: 0, labels: [] },
    { n: 3, title: "[A-3] normal", blocksCount: 0 },
    { n: 4, title: "[A-4] critical", blocksCount: 0, labels: ["prio:critical"] },
    { n: 5, title: "[A-5] critical blocked", blocksCount: 3, labels: ["prio:critical"] },
    { n: 6, title: "[A-6] normal blocked", blocksCount: 2 },
    { n: 7, title: "[A-7] 任意 blocked", blocksCount: 2, labels: ["oc:no-pr"] },
    { n: 8, title: "[A-8] low 任意", blocksCount: 5, labels: ["prio:low"] },
  ]);
  assert.deepEqual(sorted.map((r) => r.n), [5, 4, 6, 7, 3, 2, 1, 8]);
});

test("選定 (区分): room が限られても、prio:critical の ready を先に入れ、low は後に回す", () => {
  const ready = [
    { n: 100, title: "t", blocksCount: 0 },
    { n: 101, title: "t", blocksCount: 0 },
    { n: 102, title: "t", blocksCount: 0, labels: ["prio:critical"] },
    { n: 103, title: "t", blocksCount: 0, labels: ["prio:low"] },
  ];
  const p = planLaunch({ ready, relaunch: [], active: 47, target: 50, batch: 25 });
  assert.equal(p.room, 3);
  assert.deepEqual(p.picks, [102, 100, 101]);
});

test("選定 (区分): critical が無ければ他を遊ばせない (low も枠に余裕があれば出す)", () => {
  const ready = [
    { n: 100, title: "t", blocksCount: 0 },
    { n: 101, title: "t", blocksCount: 0, labels: ["prio:low"] },
    { n: 102, title: "t", blocksCount: 0 },
  ];
  const p = planLaunch({ ready, relaunch: [], active: 0, target: 50, batch: 25 });
  assert.deepEqual(p.picks, [100, 102, 101]);
});

test("選定 (区分): relaunch は従来どおり枠の先頭に全件入り、残りの枠を critical の ready が使う", () => {
  const ready = [
    { n: 100, title: "t", blocksCount: 0 },
    { n: 101, title: "t", blocksCount: 0, labels: ["prio:critical"] },
  ];
  const p = planLaunch({ ready, relaunch: [7, 8], active: 47, target: 50, batch: 25 });
  assert.equal(p.room, 3);
  assert.deepEqual(p.picks, [7, 8, 101]);
});

test("cooldown (区分): prio:critical の oc:no-pr は半分 (3 時間)、他は設定どおり (6 時間)", () => {
  assert.equal(noPrCooldownMs([], 6), 6 * 3_600_000);
  assert.equal(noPrCooldownMs(["oc:no-pr"], 6), 6 * 3_600_000);
  assert.equal(noPrCooldownMs(["oc:no-pr", "prio:critical"], 6), 3 * 3_600_000);
  assert.equal(noPrCooldownMs(["prio:low"], 6), 6 * 3_600_000);
});

test("選定: room = TARGET - active, n = min(room, BATCH, ready)", () => {
  const ready = Array.from({ length: 40 }, (_, i) => ({ n: 100 + i, title: "t", blocksCount: 0 }));
  // 既定 TARGET=50, BATCH=25, active=10 -> room=40, n=min(40,25,40)=25
  const p = planLaunch({ ready, relaunch: [], active: 10 });
  assert.equal(p.room, 40);
  assert.equal(p.picks.length, 25);
  assert.deepEqual(p.picks.slice(0, 2), [100, 101]);
});

test("選定: active が TARGET 以上なら新規は 0。ただし relaunch は入る", () => {
  const ready = [{ n: 1, title: "t", blocksCount: 0 }];
  const p = planLaunch({ ready, relaunch: [42], active: 60 });
  assert.equal(p.room, 0);
  assert.deepEqual(p.picks, [42]);
});

test("選定: ready が空なら relaunch だけ", () => {
  const p = planLaunch({ ready: [], relaunch: [7, 8], active: 0 });
  assert.deepEqual(p.picks, [7, 8]);
});

test("選定: 明示の TARGET / BATCH を尊重", () => {
  const ready = Array.from({ length: 10 }, (_, i) => ({ n: i + 1, title: "t", blocksCount: 0 }));
  const p = planLaunch({ ready, relaunch: [], active: 3, target: 5, batch: 4 });
  assert.equal(p.room, 2);
  assert.deepEqual(p.picks, [1, 2]);
});

test("選定: relaunch 2 件 + ready 5 件 (枠に余裕あり) は、relaunch 2 件と ready 5 件を全件出す", () => {
  const ready = Array.from({ length: 5 }, (_, i) => ({ n: 100 + i, title: "t", blocksCount: 0 }));
  const p = planLaunch({ ready, relaunch: [7, 8], active: 0, target: 1000, batch: 1000 });
  assert.deepEqual(p.picks, [7, 8, 100, 101, 102, 103, 104]);
});

test("選定: relaunch 2 件 + ready 40 件 (BATCH で頭打ち) は、枠 25 件に relaunch が先頭で入る", () => {
  const ready = Array.from({ length: 40 }, (_, i) => ({ n: 100 + i, title: "t", blocksCount: 0 }));
  const p = planLaunch({ ready, relaunch: [7, 8], active: 0 });
  assert.equal(p.picks.length, 25);
  assert.deepEqual(p.picks.slice(0, 3), [7, 8, 100]);
  assert.equal(p.picks[24], 122);
});

test("選定: relaunch 2 件 + ready 1 件 (ready が少ない) は、ready を落とさない", () => {
  const ready = [{ n: 100, title: "t", blocksCount: 0 }];
  const p = planLaunch({ ready, relaunch: [7, 8], active: 0 });
  assert.deepEqual(p.picks, [7, 8, 100]);
});

test("選定: relaunch は room を使う。room を超える relaunch も全件出し、新規は出さない", () => {
  const ready = Array.from({ length: 10 }, (_, i) => ({ n: 100 + i, title: "t", blocksCount: 0 }));
  const inRoom = planLaunch({ ready, relaunch: [1, 2], active: 48 });
  assert.equal(inRoom.room, 2);
  assert.deepEqual(inRoom.picks, [1, 2]);
  const over = planLaunch({ ready, relaunch: [1, 2, 3], active: 48 });
  assert.deepEqual(over.picks, [1, 2, 3]);
});

test("allowlist は infer が返す全素材名を含む", () => {
  assert.ok(ALLOW_ARTS.includes("work-m6-ott"));
});

test("本文の素材行 (#2758): 検証済みの 1 行にする。allowlist 外の名前は落とす", () => {
  assert.equal(bodyArtLine("説明\noc_artifacts: fl-win64 evil-thing work-m11\n"), "oc_artifacts: fl-win64 work-m11");
  assert.equal(bodyArtLine("説明\noc_artifacts: evil\n"), null);
});

test("本文の素材行 (#2758): 最後の行を使い、前の行には戻らない", () => {
  assert.equal(bodyArtLine("oc_artifacts: fl-win64\noc_artifacts: work-m11\n"), "oc_artifacts: work-m11");
  assert.equal(bodyArtLine("oc_artifacts: fl-win64\noc_artifacts: evil\n"), null);
});

test("本文の素材行 (#2758): none は単独の行のときだけ有効。混在は none を落とす", () => {
  assert.equal(bodyArtLine("oc_artifacts: none\n"), "oc_artifacts: none");
  assert.equal(bodyArtLine("oc_artifacts: none fl-win64\n"), "oc_artifacts: fl-win64");
});

test("本文の素材行 (#2758): 先頭 4000 字の外の行は見ない", () => {
  assert.equal(bodyArtLine("x".repeat(4000) + "\noc_artifacts: fl-win64\n"), null);
  assert.equal(bodyArtLine("x".repeat(3900) + "\noc_artifacts: fl-win64\n"), "oc_artifacts: fl-win64");
});

test("本文の素材行 (#2758): バッククォートで囲んだ行と CRLF の本文を読む", () => {
  assert.equal(bodyArtLine("`oc_artifacts: fl-win64 work-m11`"), "oc_artifacts: fl-win64 work-m11");
  assert.equal(bodyArtLine("a\r\noc_artifacts: fl-win64\r\n"), "oc_artifacts: fl-win64");
});

test("本文の素材行 (#2758): 行の途中に出る語や自然文は素材行にしない", () => {
  assert.equal(bodyArtLine("必要なし (実機採取のため ...)"), null);
  assert.equal(bodyArtLine("素材は oc_artifacts: fl-win64 を参照"), null);
  assert.equal(bodyArtLine(""), null);
});

test("素材行の既定 (#2758): PM の行 → 本文の行 → 推定の順。無効な行は飛ばす", () => {
  assert.equal(defaultArtLine("oc_artifacts: fl-win64 plugins-ott", "oc_artifacts: fl-win64 work-m11", "[CI-1] t", []), "oc_artifacts: fl-win64 plugins-ott");
  assert.equal(defaultArtLine("oc_artifacts: evil", "oc_artifacts: fl-win64 work-m11", "[CI-1] t", []), "oc_artifacts: fl-win64 work-m11");
  assert.equal(defaultArtLine(null, "oc_artifacts: none", "[CI-1] t", []), "oc_artifacts: none");
  assert.equal(defaultArtLine(undefined, null, "[SR-1] serum", []), inferArtifacts("[SR-1] serum", []));
});
