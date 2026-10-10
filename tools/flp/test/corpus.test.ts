// Corpus-level checks; skipped automatically when the FL data tree is not present (set FL_ROOT to override).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { parseFlp, writeFlp, firstDiff } from '../src/flp.ts';
import { typedRoundTrip } from '../src/decode.ts';
import { summarize } from '../src/summary.ts';
import { listFlhdFiles, flRoot } from '../cli/_corpus.ts';

const have = existsSync(flRoot());
const files = have ? listFlhdFiles() : [];

test('every .flp round-trips byte-exactly (level 0) and via typed events (level 1)', { skip: !have }, () => {
  const flps = files.filter((f) => f.ext === 'flp');
  assert.ok(flps.length >= 160, `flp count ${flps.length}`);
  for (const f of flps) {
    const b = readFileSync(f.abs);
    const p = parseFlp(b);
    assert.equal(p.warnings.length, 0, f.rel);
    assert.equal(firstDiff(b, writeFlp(p)), -1, f.rel);
    assert.equal(typedRoundTrip(p).mismatches.length, 0, f.rel);
  }
});

test('sampled fst/fsc round-trip', { skip: !have }, () => {
  const others = files.filter((f) => f.ext !== 'flp').filter((_, i) => i % 40 === 0);
  assert.ok(others.length > 100);
  for (const f of others) {
    const b = readFileSync(f.abs);
    const p = parseFlp(b);
    assert.equal(firstDiff(b, writeFlp(p)), -1, f.rel);
    assert.equal(typedRoundTrip(p).mismatches.length, 0, f.rel);
  }
});

test('known anchors: NewStuff.flp', { skip: !have }, () => {
  const f = files.find((x) => x.rel.endsWith('Demo projects/NewStuff.flp'));
  assert.ok(f);
  const p = parseFlp(readFileSync(f.abs));
  const s = summarize(p);
  assert.equal(s.version, '25.2.3.5164');
  assert.equal(s.tempo, 150);
  assert.equal(s.channels, 45);
  assert.equal(p.events.length, 4403);
  assert.ok(p.events.some((e) => e.ext && e.id === 0xc0000101));
});
