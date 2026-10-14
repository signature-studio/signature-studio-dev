import { test } from "node:test";
import assert from "node:assert/strict";
import {
  ALLOW_ARTS,
  buildLaunchBody,
  inferArtifacts,
  planLaunch,
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

test("allowlist は infer が返す全素材名を含む", () => {
  assert.ok(ALLOW_ARTS.includes("work-m6-ott"));
});
