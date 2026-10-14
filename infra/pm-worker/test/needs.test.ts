import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { needsHits, needsPmDecision, splitLines } from "../src/needs.ts";

const here = fileURLToPath(new URL(".", import.meta.url));
const fixturePath = `${here}fixtures/needs.input.json`;
const crosscheck = `${here}needs_crosscheck.py`;

test("Python 版 (tools/pm/pm_needs.py の KEY) と同じ判定: 固定 JSON の全ケースで一致行数が一致する", () => {
  const fx = JSON.parse(readFileSync(fixturePath, "utf8"));
  const py = JSON.parse(execFileSync("python3", [crosscheck, fixturePath], { encoding: "utf8" }));
  assert.ok(fx.cases.length >= 20, "ケース数");
  const ts = fx.cases.map((c: { body: string }) => ({ hits: needsHits(c.body), matches: needsPmDecision(c.body) }));
  assert.deepEqual(ts, py);
  // 両側が自明に全部 false / 全部 true ではない
  assert.ok(py.some((r: { matches: boolean }) => r.matches) && py.some((r: { matches: boolean }) => !r.matches));
});

test("行分割は Python の splitlines と同じ (\\v \\f \\x85 \\u2028 は行の区切り。末尾の区切りは空行を作らない)", () => {
  assert.deepEqual(splitLines("a\r\nb\vc\fd\x85e\u2028f\rg\n"), ["a", "b", "c", "d", "e", "f", "g"]);
  assert.deepEqual(splitLines(""), []);
  assert.equal(needsPmDecision(null), false);
  assert.equal(needsPmDecision(undefined), false);
});
