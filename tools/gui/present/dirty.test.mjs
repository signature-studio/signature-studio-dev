// dirty.test.mjs — gui_dirty.ts (mergeRects) の単体テスト。node --test tools/gui/present/dirty.test.mjs (要: tsc 済み build/js)
import test from "node:test";
import assert from "node:assert/strict";
import { mergeRects, rectArea } from "../build/js/gui_dirty.js";

const R = (id, l, t, r, b) => ({ id, l, t, r, b });

test("重なる矩形は 1 つに併合", () => {
  assert.deepEqual(mergeRects([R(0, 0, 0, 10, 10), R(0, 5, 5, 20, 20)]), [R(0, 0, 0, 20, 20)]);
});
test("辺で接する矩形は併合", () => {
  assert.deepEqual(mergeRects([R(0, 0, 0, 10, 10), R(0, 10, 0, 20, 10)]), [R(0, 0, 0, 20, 10)]);
});
test("離れた小矩形は併合しない (外接すると面積が大きく増える)", () => {
  const out = mergeRects([R(0, 0, 0, 10, 10), R(0, 100, 100, 110, 110)]);
  assert.equal(out.length, 2);
  assert.equal(rectArea(out), 200);
});
test("面積増加が slack 以内なら併合", () => {
  const out = mergeRects([R(0, 0, 0, 10, 10), R(0, 11, 0, 21, 10)]);   // 隙間 1px: union 210 <= 200*1.25
  assert.deepEqual(out, [R(0, 0, 0, 21, 10)]);
});
test("surface が違う矩形は併合しない / 空矩形は捨てる", () => {
  const out = mergeRects([R(0, 0, 0, 10, 10), R(1, 0, 0, 10, 10), R(2, 5, 5, 5, 9), R(2, 3, 3, 2, 2)]);
  assert.deepEqual(out.map((q) => q.id), [0, 1]);
});
test("surface あたり maxPerSurf を超えない", () => {
  const rs = Array.from({ length: 40 }, (_, i) => R(0, i * 50, (i % 7) * 40, i * 50 + 4, (i % 7) * 40 + 4));
  assert.ok(mergeRects(rs, 8).length <= 8);
  assert.ok(mergeRects(rs, 3).length <= 3);
});
test("性質: 入力の全画素が出力のいずれかに含まれる / 出力の個数上限 (ビットマップによる別算法検算)", () => {
  let seed = 12345;
  const rnd = (n) => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed % n; };
  for (let c = 0; c < 400; c++) {
    const n = 1 + rnd(14), rs = [];
    for (let i = 0; i < n; i++) { const l = rnd(60), t = rnd(40); rs.push(R(rnd(3), l, t, l + 1 + rnd(25), t + 1 + rnd(25))); }
    const out = mergeRects(rs);
    const bmp = new Map();
    for (const q of out) for (let y = q.t; y < q.b; y++) for (let x = q.l; x < q.r; x++) bmp.set(`${q.id},${x},${y}`, 1);
    for (const q of rs) for (let y = q.t; y < q.b; y++) for (let x = q.l; x < q.r; x++) assert.ok(bmp.has(`${q.id},${x},${y}`), `case ${c}: 画素 (${q.id},${x},${y}) が欠落`);
    for (let id = 0; id < 3; id++) assert.ok(out.filter((q) => q.id === id).length <= 8);
  }
});
