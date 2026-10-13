import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseTrace, analyze, observedTiers, diffTiers } from '../assettrace.mjs';
import { createMapper } from '../../../shimx/pathreg/js/pathmap.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const inv = fs.readFileSync(path.join(here, 'fixtures/inv.jsonl'), 'utf8').trim().split('\n').map((l) => JSON.parse(l));
const trace = fs.readFileSync(path.join(here, 'fixtures/boot.trace.jsonl'), 'utf8');
const events = parseTrace(trace);
const run = (ev = events, o = {}) => analyze(ev, inv, o);
const paths = (r) => r.files.map((f) => f.path).sort();

test('trace 12 行をパースする (JSON 以外の行は無視、壊れた JSON / 未知 op は例外)', () => {
  assert.equal(events.length, 12);
  assert.equal(parseTrace('# comment\n\n').length, 0);
  assert.throws(() => parseTrace('{"op":"open"'), /invalid JSON/);
  assert.throws(() => parseTrace('{"op":"zap","path":"x"}'), /bad op/);
});

test('Win パス (大小混在・/ 区切り・\\\\?\\) と POSIX パスが同じ tree 相対パスに落ちる', () => {
  const r = run();
  assert.ok(paths(r).includes('Artwork/Skins/Default/Title.png'));
  assert.ok(paths(r).includes('System/Config/Chords.map'));
  assert.equal(r.files.find((f) => f.path === 'Artwork/Skins/Default/Title.png').n, 3);
});

test('enum "dir\\*.txt" は inventory のワイルドカード一致を全件展開し、dirs に件数を記録する', () => {
  const r = run();
  const d = r.dirs.find((x) => x.path === 'System/Config/*.txt');
  assert.equal(d.matched, 2);
  assert.ok(paths(r).includes('System/Config/MP3Genres.txt') && paths(r).includes('System/Config/NamePresets_Channel.txt'));
  assert.ok(!paths(r).includes('System/Config/other.bin'));
});

test('/c/home・/c/tmp・未登録 (D:\\) は asset に含めず other に数える', () => {
  const r = run();
  assert.deepEqual(r.other, { persist: 2, tmp: 1, unmapped: 1 });
  assert.ok(!r.files.some((f) => /Settings|tmp/i.test(f.path)));
});

test('ok=false は missing に入り files に入らない / inventory に無い読取は unknown', () => {
  const r = run();
  assert.deepEqual(r.missing.map((m) => m.path), ['Data/System/Nope.fst']);
  assert.deepEqual(r.unknown.map((m) => m.path), ['Data/System/Generated.bin']);
  assert.ok(!paths(r).includes('Data/System/Nope.fst'));
});

test('ディレクトリ自体の stat は unknown にならない', () => {
  const r = run([{ seq: 0, op: 'stat', path: 'C:\\Program Files\\Image-Line\\FL Studio 2026\\Artwork', ok: true, w: false }]);
  assert.equal(r.unknown.length, 0);
  assert.equal(r.files.length, 0);
});

test('観測集合は T0 に固定され、静的推定 tier との差分 (promote / unseenT0) が出る', () => {
  const r = run();
  const t = observedTiers(r, { 'Help/index_offline.html': 'T1' });
  assert.equal(t['Artwork/Skins/Default/Title.png'], 'T0');
  assert.equal(t['Help/index_offline.html'], 'T1');
  const d = diffTiers(r, inv);
  assert.deepEqual(d.promote.map((x) => x.path), ['System/Config/Thumbnails/a.png']);
  assert.equal(d.unseenT0, 1);
});

test('FL への書込み open は roWrites に出る (RO 違反の検出)', () => {
  const r = run([{ seq: 0, op: 'open', path: 'C:\\Program Files\\Image-Line\\FL Studio 2026\\Artwork\\x.png', ok: true, w: true }]);
  assert.equal(r.roWrites.length, 1);
  assert.equal(r.files.length, 0);
});

// ---- ネガティブコントロール: 写像を壊すと検査が FAIL する (空振りでないこと) ----
test('NC1: installDir を別パスに変えた mapper では Win パス経由の asset が全て落ちる (POSIX 直指定の 1 件のみ残る)', () => {
  const bad = createMapper({ paths: { installDir: 'C:\\Elsewhere', vfsInstall: '/fl', userProfile: 'C:\\Users\\webstudio', vfsHome: '/c/home', vfsTmp: '/c/tmp' } });
  const r = run(events, { mapper: bad });
  assert.deepEqual(paths(r), ['System/Config/Thumbnails/a.png']);
  assert.equal(paths(run()).length, 5);
  assert.ok(r.other.persist > run().other.persist);
});

test('NC2: inventory から 1 件消すと unknown が 1 件増え files が 1 件減る', () => {
  const r0 = run();
  const r1 = analyze(events, inv.filter((e) => e.p !== 'Artwork/Skins/Default/Title.png'));
  assert.equal(r1.files.length, r0.files.length - 1);
  assert.equal(r1.unknown.length, r0.unknown.length + 1);
});
